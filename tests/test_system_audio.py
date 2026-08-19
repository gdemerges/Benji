"""Capture de l'audio système : détection du périphérique, anneau, mixage.

Aucun matériel ni pilote de boucle n'est requis — la liste de périphériques est
injectée et le mixeur est piloté chunk par chunk.
"""

from queue import Queue

import numpy as np
import pytest

from benji.audio.loopback import (
    LoopbackDevice,
    find_loopback_devices,
    select_loopback,
)
from benji.audio.system_capture import _resample_linear, _Ring


def dev(name, inputs=2):
    return {"name": name, "max_input_channels": inputs, "default_samplerate": 48000}


# --- détection -------------------------------------------------------------


def test_ignores_output_only_devices():
    # BlackHole apparaît en entrée ET en sortie ; seule l'entrée est captable.
    devices = [dev("BlackHole 2ch", inputs=0), dev("MacBook Pro Microphone", inputs=1)]
    assert find_loopback_devices(devices) == []


def test_blackhole_wins_over_weaker_candidates():
    devices = [dev("Soundflower (2ch)"), dev("BlackHole 16ch"), dev("Aggregate Device")]
    best = select_loopback(devices)
    assert best is not None
    assert "BlackHole" in best.name


def test_app_owned_device_is_never_auto_selected():
    """Teams/Zoom exposent un périphérique qui ne capte que leur propre app :
    le choisir tout seul donnerait une capture partielle et silencieuse."""
    devices = [dev("Microsoft Teams Audio"), dev("MacBook Pro Microphone", inputs=1)]
    assert select_loopback(devices) is None

    found = find_loopback_devices(devices)
    assert len(found) == 1
    assert found[0].app_owned is True
    assert found[0].is_reliable is False


def test_explicit_preference_can_select_an_app_owned_device():
    devices = [dev("BlackHole 2ch"), dev("Microsoft Teams Audio")]
    chosen = select_loopback(devices, preferred="teams")
    assert chosen is not None and chosen.name == "Microsoft Teams Audio"


def test_missing_preferred_device_does_not_fall_back_silently():
    """Si le périphérique choisi a disparu, mieux vaut rien que capter autre
    chose à l'insu de l'utilisateur."""
    assert select_loopback([dev("BlackHole 2ch")], preferred="Loopback Audio") is None


def test_no_candidate_at_all():
    assert select_loopback([dev("MacBook Pro Microphone", inputs=1)]) is None


def test_ordering_is_deterministic():
    devices = [dev("BlackHole 16ch"), dev("BlackHole 2ch")]
    names = [d.name for d in find_loopback_devices(devices)]
    assert names == sorted(names)


# --- anneau ----------------------------------------------------------------


def test_ring_roundtrip():
    ring = _Ring(100)
    ring.write(np.arange(10, dtype=np.float32))
    assert np.array_equal(ring.read(10), np.arange(10, dtype=np.float32))


def test_ring_pads_with_silence_when_starved():
    """Lecture plus rapide que l'écriture : on complète, on ne bloque pas."""
    ring = _Ring(100)
    ring.write(np.ones(4, dtype=np.float32))
    out = ring.read(10)
    assert len(out) == 10
    # Le silence de rattrapage passe devant, le son réel garde sa place en fin.
    assert np.array_equal(out[:6], np.zeros(6, dtype=np.float32))
    assert np.array_equal(out[6:], np.ones(4, dtype=np.float32))


def test_ring_drops_oldest_on_overrun():
    ring = _Ring(8)
    ring.write(np.arange(8, dtype=np.float32))
    ring.write(np.arange(100, 104, dtype=np.float32))
    assert ring.overruns == 1
    assert ring.available == 8
    # Les 4 plus anciens ont sauté, les plus récents survivent.
    assert np.array_equal(ring.read(8)[-4:], np.arange(100, 104, dtype=np.float32))


def test_ring_write_larger_than_capacity_keeps_the_tail():
    ring = _Ring(4)
    ring.write(np.arange(10, dtype=np.float32))
    assert np.array_equal(ring.read(4), np.arange(6, 10, dtype=np.float32))


def test_ring_wraps_around():
    ring = _Ring(10)
    ring.write(np.arange(8, dtype=np.float32))
    ring.read(8)
    ring.write(np.arange(50, 56, dtype=np.float32))  # franchit la fin du tampon
    assert np.array_equal(ring.read(6), np.arange(50, 56, dtype=np.float32))


# --- ré-échantillonnage ----------------------------------------------------


def test_resample_is_a_noop_at_equal_rates():
    data = np.arange(5, dtype=np.float32)
    assert _resample_linear(data, 16000, 16000) is data


def test_resample_48k_to_16k_length_and_dtype():
    data = np.sin(np.linspace(0, 10, 4800, dtype=np.float32))
    out = _resample_linear(data, 48000, 16000)
    assert len(out) == 1600
    assert out.dtype == np.float32
    assert abs(float(out.max()) - float(data.max())) < 0.05


def test_resample_empty():
    assert len(_resample_linear(np.zeros(0, dtype=np.float32), 48000, 16000)) == 0


# --- mixage ----------------------------------------------------------------


class FakeSystem:
    """Substitut de SystemAudioCapture : un anneau, sans stream CoreAudio."""

    def __init__(self, capacity=1000):
        self.ring = _Ring(capacity)


def make_mixer(gain=1.0, audio_queue=None, stats=None):
    from benji.audio.system_capture import AudioMixer

    return AudioMixer(
        mic_queue=Queue(),
        audio_queue=audio_queue if audio_queue is not None else Queue(),
        system=FakeSystem(),
        system_gain=gain,
        stats=stats,
    )


def test_mix_sums_both_sources():
    mixer = make_mixer()
    mixer.system.ring.write(np.full(4, 0.25, dtype=np.float32))
    out = mixer.mix_chunk(np.full(4, 0.5, dtype=np.float32))
    assert np.allclose(out, 0.75)


def test_mix_preserves_chunk_length_when_system_is_silent():
    """Le VAD Silero exige des chunks de 512 échantillons : la longueur du
    chunk micro doit sortir intacte, quoi qu'il arrive côté système."""
    mixer = make_mixer()
    out = mixer.mix_chunk(np.full(512, 0.1, dtype=np.float32))
    assert len(out) == 512
    assert np.allclose(out, 0.1)


def test_mix_saturates_instead_of_wrapping():
    mixer = make_mixer()
    mixer.system.ring.write(np.full(4, 0.9, dtype=np.float32))
    out = mixer.mix_chunk(np.full(4, 0.9, dtype=np.float32))
    assert out.max() <= 1.0
    assert np.allclose(out, 1.0)


def test_system_gain_is_applied():
    mixer = make_mixer(gain=0.5)
    mixer.system.ring.write(np.full(4, 0.4, dtype=np.float32))
    out = mixer.mix_chunk(np.zeros(4, dtype=np.float32))
    assert np.allclose(out, 0.2)


def test_mixer_thread_publishes_mixed_chunks():
    audio_queue = Queue()
    mixer = make_mixer(audio_queue=audio_queue)
    mixer.system.ring.write(np.full(512, 0.25, dtype=np.float32))
    mixer.start()
    try:
        mixer.mic_queue.put(np.full(512, 0.25, dtype=np.float32))
        chunk = audio_queue.get(timeout=2.0)
    finally:
        mixer.stop()
    assert len(chunk) == 512
    assert np.allclose(chunk, 0.5)


def test_mixer_records_a_drop_when_the_consumer_stalls():
    class Stats:
        def __init__(self):
            self.drops = []

        def record_drop(self, reason):
            self.drops.append(reason)

    stats = Stats()
    audio_queue = Queue(maxsize=1)
    audio_queue.put(object())  # déjà pleine : le VAD ne suit pas
    mixer = make_mixer(audio_queue=audio_queue, stats=stats)
    mixer.start()
    try:
        mixer.mic_queue.put(np.zeros(512, dtype=np.float32))
        deadline = 2.0
        step = 0.02
        waited = 0.0
        while not stats.drops and waited < deadline:
            import time

            time.sleep(step)
            waited += step
    finally:
        mixer.stop()
    assert stats.drops == ["audio_queue_full"]


# --- configuration ---------------------------------------------------------


def test_system_audio_is_off_by_default():
    """Par défaut, le chemin micro seul reste strictement inchangé."""
    from benji.config import AudioConfig

    cfg = AudioConfig()
    assert cfg.system_audio is False
    assert cfg.system_audio_device is None


@pytest.mark.parametrize("key", ["system_audio", "system_audio_device"])
def test_system_audio_prefs_are_persisted(key):
    from benji.settings import PREFS

    spec = next(p for p in PREFS if p.key == key)
    assert spec.target == "audio"
    assert spec.restart is True


def test_hydrate_applies_system_audio_prefs():
    from benji.config import AudioConfig
    from benji.settings import UserSettings

    class FakeQSettings:
        def __init__(self, values):
            self._v = values

        def value(self, key):
            return self._v.get(key)

        def setValue(self, key, value):
            self._v[key] = value

        def sync(self):
            pass

    settings = UserSettings(
        FakeQSettings({"prefs/system_audio": "true", "prefs/system_audio_device": "BlackHole"})
    )
    audio = AudioConfig()
    settings.hydrate(audio=audio)
    assert audio.system_audio is True
    assert audio.system_audio_device == "BlackHole"


def test_loopback_device_dataclass_is_frozen():
    device = LoopbackDevice(name="BlackHole 2ch", channels=2, score=100)
    with pytest.raises(Exception):
        device.name = "autre"
