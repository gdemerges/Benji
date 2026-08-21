"""Capture de l'audio système (le son des autres participants en visio) et
mixage avec le micro.

Sans ça, Benji ne transcrit que **toi** : en réunion, la moitié utile de la
conversation manque. On lit l'audio système via un pilote de boucle
(cf. `loopback.py`) exposé comme périphérique d'entrée, puis on additionne les
deux flux avant le VAD.

Le mixage est piloté par l'horloge du **micro** : pour chaque chunk micro de N
échantillons, on consomme N échantillons système. La cadence en sortie est donc
exactement celle du micro — le VAD continue de recevoir ses chunks de 512
échantillons, inchangé. Si le flux système prend du retard on complète avec du
silence ; s'il prend de l'avance on jette le plus ancien. La dérive reste ainsi
bornée par la taille du tampon au lieu de s'accumuler.

Quand la capture système est désactivée, rien de tout ceci n'est instancié :
`AudioCapture` écrit directement dans `audio_queue` comme avant.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from queue import Queue

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

# Tampon système, en secondes. Assez grand pour absorber une hoquet de
# planification, assez petit pour que le décalage reste inaudible s'il sature.
_RING_SECONDS = 2.0

_DROP_LOG_INTERVAL_S = 5.0


class _Ring:
    """Tampon circulaire mono, écrit par un callback temps réel, lu par le mixeur.

    Volontairement minimal : un `deque` de blocs serait plus simple, mais le
    coût par échantillon d'un `np.concatenate` répété devient sensible à 30
    callbacks/seconde. Ici l'écriture et la lecture sont en O(n) sur les
    échantillons réellement déplacés.
    """

    def __init__(self, capacity: int):
        self._buf = np.zeros(capacity, dtype=np.float32)
        self._capacity = capacity
        self._write = 0
        self._available = 0
        self._lock = threading.Lock()
        self.overruns = 0

    def write(self, data: np.ndarray) -> None:
        n = len(data)
        if n == 0:
            return
        if n >= self._capacity:
            # Bloc plus grand que le tampon : ne garder que la fin.
            data = data[-self._capacity :]
            n = len(data)
        with self._lock:
            end = self._write + n
            if end <= self._capacity:
                self._buf[self._write : end] = data
            else:
                split = self._capacity - self._write
                self._buf[self._write :] = data[:split]
                self._buf[: end - self._capacity] = data[split:]
            self._write = end % self._capacity
            new_available = self._available + n
            if new_available > self._capacity:
                # Le lecteur n'a pas suivi : on écrase le plus ancien.
                self.overruns += 1
                new_available = self._capacity
            self._available = new_available

    def read(self, n: int) -> np.ndarray:
        """Lit exactement *n* échantillons, complétés par du silence si besoin."""
        out = np.zeros(n, dtype=np.float32)
        with self._lock:
            take = min(n, self._available)
            if take:
                start = (self._write - self._available) % self._capacity
                end = start + take
                if end <= self._capacity:
                    chunk = self._buf[start:end]
                else:
                    chunk = np.concatenate(
                        (self._buf[start:], self._buf[: end - self._capacity])
                    )
                # Aligné à droite : le silence de rattrapage passe *devant* le
                # son réel, ce qui préserve l'ordre temporel de la parole.
                out[n - take :] = chunk
                self._available -= take
        return out

    @property
    def available(self) -> int:
        with self._lock:
            return self._available


def _resample_linear(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Ré-échantillonnage linéaire mono.

    Suffisant ici : la cible est un VAD et un modèle STT à 16 kHz, pas de l'écoute.
    Éviter scipy garde la dépendance hors du chemin critique.
    """
    if src_rate == dst_rate or len(data) == 0:
        return data.astype(np.float32, copy=False)
    ratio = dst_rate / src_rate
    n_out = int(round(len(data) * ratio))
    if n_out <= 0:
        return np.zeros(0, dtype=np.float32)
    positions = np.linspace(0, len(data) - 1, n_out, dtype=np.float32)
    return np.interp(positions, np.arange(len(data), dtype=np.float32), data).astype(
        np.float32
    )


class SystemAudioCapture:
    """Lit un périphérique de boucle et empile du mono 16 kHz dans un anneau."""

    def __init__(self, device_name: str, sample_rate: int = 16000):
        self.device_name = device_name
        self.sample_rate = sample_rate
        self.stream: sd.InputStream | None = None
        self.ring = _Ring(int(_RING_SECONDS * sample_rate))
        self._device_rate = sample_rate
        self._lock = threading.Lock()

    def _callback(self, indata: np.ndarray, frames: int, time_info, status):
        # Thread temps réel CoreAudio : jamais de blocage, jamais d'exception qui
        # remonte (PortAudio couperait le stream).
        if status:
            log.debug("system audio status: %s", status)
        try:
            mono = indata.mean(axis=1) if indata.ndim > 1 else indata
            if self._device_rate != self.sample_rate:
                mono = _resample_linear(mono, self._device_rate, self.sample_rate)
            self.ring.write(np.asarray(mono, dtype=np.float32))
        except Exception:  # pragma: no cover - garde-fou temps réel
            log.debug("system audio callback failed", exc_info=True)

    def start(self) -> bool:
        """Ouvre le stream. Renvoie False si le périphérique est indisponible.

        L'échec n'est pas fatal : Benji continue en micro seul, avec un log. Un
        pilote de boucle absent ou reconfiguré ne doit jamais empêcher l'app de
        démarrer.
        """
        try:
            index, info = self._resolve_device()
        except Exception as e:
            log.warning("Système audio : périphérique '%s' introuvable (%s)",
                        self.device_name, e)
            return False

        channels = min(int(info.get("max_input_channels", 1)), 2)
        # On tente d'abord 16 kHz natif ; beaucoup de pilotes virtuels sont
        # figés à 44.1/48 kHz, d'où le repli sur le taux du périphérique + un
        # ré-échantillonnage logiciel.
        for rate in (self.sample_rate, int(info.get("default_samplerate", 48000))):
            try:
                stream = sd.InputStream(
                    device=index,
                    samplerate=rate,
                    channels=channels,
                    dtype="float32",
                    callback=self._callback,
                )
                stream.start()
            except Exception as e:
                log.debug("Système audio : %d Hz refusé (%s)", rate, e)
                continue
            self._device_rate = rate
            with self._lock:
                self.stream = stream
            log.info(
                "Audio système capté sur '%s' (%d Hz, %d canaux)",
                info.get("name", self.device_name), rate, channels,
            )
            return True

        log.warning("Système audio : impossible d'ouvrir '%s'", self.device_name)
        return False

    def _resolve_device(self) -> tuple[int, dict]:
        """Retrouve l'index du périphérique par sous-chaîne de nom.

        On résout par nom et non par index : les index CoreAudio bougent quand
        un casque est branché, une préférence persistée par index pointerait
        alors sur le mauvais périphérique.
        """
        wanted = self.device_name.lower()
        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0 and wanted in info.get("name", "").lower():
                return index, info
        raise LookupError(self.device_name)

    def stop(self) -> None:
        with self._lock:
            stream, self.stream = self.stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


class AudioMixer:
    """Additionne le flux micro et le flux système vers `audio_queue`.

    Tourne dans son propre thread : le micro écrit dans `mic_queue` depuis le
    callback CoreAudio, le mixeur consomme et publie le mélange. Le thread Qt
    n'est jamais impliqué.
    """

    def __init__(
        self,
        mic_queue: Queue,
        audio_queue: Queue,
        system: SystemAudioCapture,
        system_gain: float = 1.0,
        stats=None,
    ):
        self.mic_queue = mic_queue
        self.audio_queue = audio_queue
        self.system = system
        self.system_gain = system_gain
        self.stats = stats
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_drop_log = 0.0

    def mix_chunk(self, mic_chunk: np.ndarray) -> np.ndarray:
        """Mélange un chunk micro avec autant d'audio système.

        Le clipping est traité par saturation plutôt que par normalisation :
        normaliser ferait « pomper » le niveau d'un chunk à l'autre, et le VAD
        à seuil adaptatif lirait ces variations comme du bruit de fond.
        """
        sys_chunk = self.system.ring.read(len(mic_chunk))
        mixed = mic_chunk + sys_chunk * self.system_gain
        return np.clip(mixed, -1.0, 1.0, out=mixed)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                mic_chunk = self.mic_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            mixed = self.mix_chunk(np.asarray(mic_chunk, dtype=np.float32))
            try:
                self.audio_queue.put_nowait(mixed)
            except queue.Full:
                if self.stats is not None:
                    self.stats.record_drop("audio_queue_full")
                now = time.monotonic()
                if now - self._last_drop_log >= _DROP_LOG_INTERVAL_S:
                    self._last_drop_log = now
                    log.warning("audio_queue full — dropping mixed chunks")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, daemon=True, name="AudioMixer")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
