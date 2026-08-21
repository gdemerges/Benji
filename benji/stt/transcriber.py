import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Full, Queue

import numpy as np

from benji.config import STTConfig

log = logging.getLogger(__name__)
from benji.history import TranscriptionHistory
from benji.stats import SessionStats
from benji.stt.backend import build_backend, build_final_backend
from benji.stt.diarization import build_tagger
from benji.stt.postprocessing import is_hallucination, postprocess_text


class Transcriber:
    def __init__(
        self,
        transcribe_queue: Queue,
        display_queue: Queue,
        config: STTConfig = None,
        stats: SessionStats | None = None,
        sample_rate: int = 16000,
    ):
        self.transcribe_queue = transcribe_queue
        self.display_queue = display_queue
        self.config = config or STTConfig()
        self.history = TranscriptionHistory()
        self.stats = stats
        self.sample_rate = sample_rate

        # État de streaming par segment (LocalAgreement-2 sur les passes
        # partielles). On re-décode le tampon **entier** à chaque passe et on
        # fige le préfixe sur lequel deux passes successives sont d'accord.
        #
        # Une version antérieure ne décodait que la queue non confirmée, en
        # réinjectant le préfixe figé via `initial_prompt` : c'était un
        # contournement du coût de Whisper. Parakeet décode 8 s en ~150 ms et
        # n'accepte aucun prompt ; décoder tout est donc à la fois plus simple et
        # plus juste — le modèle voit l'énoncé complet au lieu d'une tranche
        # amputée de son début.
        self._committed_words: list[dict] = []
        self._prev_words_norm: list[str] = []

        # Async LLM correction: raw finals are shown immediately, then corrected
        # off-thread (see _corrector_loop) so the STT loop never blocks on the LLM.
        # Each final carries a monotonic seq so the overlay can replace the right
        # segment (and ignore a correction whose segment is no longer on screen).
        self._segment_seq: int = 0
        self._correction_queue: Queue | None = None
        self._corrector_thread: threading.Thread | None = None

        # Diarisation optionnelle (pitch ou pyannote). Le tagger n'a besoin que
        # de l'audio : on le lance *en parallèle* du décodage final au lieu de
        # l'enchaîner après (cf. _run_segment). Un seul worker — le tagger porte
        # un état de clustering et ne doit jamais tourner sur deux segments à la
        # fois ; le join a lieu avant de rendre la main, donc pas de recouvrement.
        self._diarizer_pool: ThreadPoolExecutor | None = None
        self.tagger = (
            build_tagger(
                self.config.diarization_backend,
                max_speakers=self.config.diarization_max_speakers,
            )
            if self.config.diarization
            else None
        )

        # Deux moteurs, un par type de passe (cf. benji/stt/backend.py) : le
        # direct privilégie la latence, le final la garantie de langue.
        self.backend = build_backend(self.config.model)
        self.final_backend = build_final_backend(
            self.config.final_engine,
            self.config.final_model_size,
            self.config.language,
        ) or self.backend
        log.info(
            "Moteurs prêts — partielles : %s · finale : %s",
            self.backend.name, self.final_backend.name,
        )

    def warmup(self) -> None:
        """Décodage à blanc pour amortir la compilation des noyaux Metal.

        La liaison du modèle au stream MLX, elle, est faite par le backend au
        chargement (`mx.eval` des poids) : ce préchauffage-ci ne sert plus qu'à
        payer la compilation avant la première vraie phrase, pas après.
        """
        silence = np.zeros(self.sample_rate, dtype=np.float32)
        for backend in {id(self.backend): self.backend,
                        id(self.final_backend): self.final_backend}.values():
            try:
                t0 = time.monotonic()
                for _ in backend.transcribe(silence):
                    pass
                log.info("Préchauffage de %s en %.0f ms",
                         backend.name, (time.monotonic() - t0) * 1000)
            except Exception as e:
                log.warning("Préchauffage de %s ignoré : %s", backend.name, e)

    def _reset_partial_state(self) -> None:
        self._committed_words = []
        self._prev_words_norm = []

    @staticmethod
    def _norm(text: str) -> str:
        """Normalize a word for cross-partial agreement comparison.

        Le moteur change parfois une capitale ou recolle une ponctuation d'une
        passe à l'autre ; on les ignore pour que l'accord porte sur le contenu
        lexical et pas sur ces variations.
        """
        return text.strip().lower().strip(".,;:!?\"'«»()[]")

    @staticmethod
    def _common_prefix_len(a: list[str], b: list[str]) -> int:
        n = min(len(a), len(b))
        for i in range(n):
            if a[i] != b[i]:
                return i
        return n

    def _apply_agc(self, audio: np.ndarray) -> np.ndarray:
        """Normalise en crête les tampons faibles pour présenter un niveau constant.

        Boost-only: only quiet segments are scaled up; loud segments pass through.
        Avoids amplifying near-silence (peak < 0.01) which would just amplify noise.
        """
        target = self.config.agc_target_peak
        if target <= 0.0 or audio.size == 0:
            return audio
        peak = float(np.max(np.abs(audio)))
        if peak < 0.01 or peak >= self.config.agc_min_peak:
            return audio
        gain = min(target / peak, 8.0)  # Cap gain at 8x to limit noise blow-up
        return (audio * gain).astype(np.float32, copy=False)

    def _run_partial(self, audio: np.ndarray) -> None:
        """Re-décode le tampon entier et stabilise l'affichage par LocalAgreement-2.

        Le préfixe sur lequel deux passes successives tombent d'accord est
        considéré comme acquis et ne bougera plus à l'écran ; la queue est
        affichée telle quelle, au titre de « meilleure hypothèse du moment ».
        C'est ce qui évite que le texte déjà lu se réécrive sous les yeux.

        Le figeage est **monotone** : on n'annule jamais un mot déjà acquis, même
        si une passe ultérieure change d'avis — reprendre un mot affiché est plus
        déroutant que de laisser une petite erreur que la passe finale corrigera.
        """
        start_t = time.monotonic()
        audio = self._apply_agc(audio)
        if len(audio) < int(0.3 * self.sample_rate):
            return  # trop court pour valoir une passe

        words = list(self.backend.transcribe(audio))
        if not words:
            return

        norm = [self._norm(w["text"]) for w in words]
        agreed = self._common_prefix_len(norm, self._prev_words_norm)
        if agreed > len(self._committed_words):
            self._committed_words = words[:agreed]
        self._prev_words_norm = norm

        # Redessine l'instantané : préfixe acquis, puis meilleure hypothèse.
        self.display_queue.put({"type": "segment_start"})
        for w in self._committed_words + words[len(self._committed_words):]:
            self.display_queue.put({
                "type": "word", "text": w["text"],
                "start": w.get("start"), "end": w.get("end"),
            })

        if self.stats is not None:
            latency_ms = (time.monotonic() - start_t) * 1000
            self.stats.record_segment(
                len(audio) / self.sample_rate, latency_ms, is_final=False
            )

    def _run_segment(self, audio: np.ndarray, is_final: bool):
        if not is_final:
            self._run_partial(audio)
            return

        start_t = time.monotonic()
        audio = self._apply_agc(audio)

        # Diarisation lancée AVANT le décodage : elle ne dépend que de l'audio.
        # Enchaînée après, son coût (embedding pyannote) s'ajoutait tel quel au
        # délai avant affichage du texte final ; en parallèle, il est absorbé par
        # le décodage qui tourne de toute façon.
        speaker_future = None
        if self.tagger is not None:
            speaker_future = self._ensure_diarizer_pool().submit(
                self._label_speaker, audio, self.sample_rate
            )

        self.display_queue.put({"type": "segment_start"})
        words: list[dict] = []
        for word in self.final_backend.transcribe(audio):
            words.append(word)
            self.display_queue.put({
                "type": "word",
                "text": word["text"],
                "start": word.get("start"),
                "end": word.get("end"),
            })

        if not words:
            if speaker_future is not None:
                speaker_future.cancel()
            self._reset_partial_state()
            return

        full_text = postprocess_text(
            " ".join(w["text"] for w in words), language=self.config.language
        )
        if is_hallucination(full_text):
            if speaker_future is not None:
                speaker_future.cancel()
            # Tell the overlay to drop the streamed (hallucinated) words instead
            # of leaving them on screen.
            self.display_queue.put({"type": "final_text", "text": "", "drop": True})
            self._reset_partial_state()
            return

        # Étiquette de locuteur (best-effort). Champ structuré, jamais collé dans
        # le texte, pour que l'UI puisse le colorer par locuteur.
        speaker = self._await_speaker(speaker_future)

        if self.config.llm_correction:
            # Show the raw transcription immediately, then correct it off-thread
            # and emit a replacement once ready — the STT loop never blocks on the
            # LLM. History is written by the corrector (stores the corrected text).
            self._segment_seq += 1
            self._emit_final(full_text, speaker, seq=self._segment_seq)
            self._enqueue_correction(full_text, speaker, self._segment_seq)
        else:
            # Replace the streamed (raw) overlay text with the post-processed one.
            self._emit_final(full_text, speaker)
            # DEBUG et pas INFO : le log est persisté sur disque et joint aux
            # rapports de bug — le contenu transcrit ne doit pas y fuiter.
            log.debug('%s"%s"', f"[{speaker}] " if speaker else "", full_text)
            self.history.add(full_text, speaker=speaker)

        # Stats
        if self.stats is not None:
            latency_ms = (time.monotonic() - start_t) * 1000
            audio_seconds = len(audio) / self.sample_rate
            self.stats.record_segment(audio_seconds, latency_ms)

        # Final closes the segment — partial state resets for the next utterance.
        self._reset_partial_state()

    def _ensure_diarizer_pool(self) -> ThreadPoolExecutor:
        """Pool à un worker, créé au premier segment étiqueté.

        Paresseux : le tagger peut être posé après la construction (tests, bascule
        de backend), et un pool n'a aucune raison d'exister sans diarisation.
        """
        if self._diarizer_pool is None:
            self._diarizer_pool = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="STT-diarizer"
            )
        return self._diarizer_pool

    def _label_speaker(self, audio, sample_rate: int):
        """Étiquette de locuteur, best-effort : jamais fatale pour le segment."""
        try:
            return self.tagger.label(audio, sample_rate)
        except Exception as e:
            log.warning("Diarisation ignorée : %s", e)
            return None

    def _await_speaker(self, future, timeout: float = 5.0):
        """Récupère l'étiquette calculée en parallèle du décodage.

        Le timeout est un garde-fou : un tagger bloqué (modèle qui télécharge,
        backend gelé) ne doit pas figer la boucle STT — on rend le segment sans
        locuteur plutôt que d'arrêter la transcription.
        """
        if future is None:
            return None
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            log.warning("Diarisation abandonnée (%s) — segment sans locuteur", e)
            return None

    def _emit_final(self, text: str, speaker: str | None, *, seq: int | None = None,
                    corrected: bool = False) -> None:
        """Push a final_text message to the overlay.

        `seq` tags the segment so an async correction can be matched back to it;
        `corrected` marks the replacement so the overlay only applies it while the
        same segment is still displayed.
        """
        msg: dict = {"type": "final_text", "text": text}
        if speaker:
            msg["speaker"] = speaker
        if seq is not None:
            msg["seq"] = seq
        if corrected:
            msg["corrected"] = True
        self.display_queue.put(msg)

    def _ensure_corrector(self) -> None:
        if self._corrector_thread is not None and self._corrector_thread.is_alive():
            return
        self._correction_queue = Queue(maxsize=8)
        self._corrector_thread = threading.Thread(
            target=self._corrector_loop, daemon=True, name="STT-corrector"
        )
        self._corrector_thread.start()

    def _enqueue_correction(self, text: str, speaker: str | None, seq: int) -> None:
        self._ensure_corrector()
        try:
            self._correction_queue.put_nowait((seq, text, speaker))
        except Full:
            # Corrector saturated: keep the raw text (already displayed) and
            # persist it now so history has exactly one entry for this segment.
            log.warning("LLM corrector saturated; kept raw text")
            self.history.add(text, speaker=speaker)

    def _corrector_loop(self) -> None:
        """Background worker: correct queued finals and emit replacements.

        Persists the corrected (or unchanged) text to history so there is exactly
        one entry per segment — the STT loop deliberately skips history.add when
        correction is enabled.
        """
        from benji.llm.corrector import correct
        while True:
            item = self._correction_queue.get()
            if item is None:
                break
            seq, text, speaker = item
            try:
                corrected = correct(text, language=self.config.language)
            except Exception as e:
                log.warning("LLM correction skipped: %s", e)
                corrected = text
            self.history.add(corrected, speaker=speaker)
            log.debug('%s"%s"', f"[{speaker}] " if speaker else "", corrected)
            self._emit_final(corrected, speaker, seq=seq, corrected=True)

    def run(self):
        log.info("Transcription started (incremental streaming)")
        while True:
            item = self.transcribe_queue.get()
            if item is None:
                break
            audio = item["audio"]
            is_final = item["is_final"]
            if not is_final and not self.transcribe_queue.empty():
                continue
            try:
                self._run_segment(audio, is_final)
            except Exception:
                # A single bad segment should not kill the STT loop.
                log.exception("STT segment failed (final=%s, %.2fs); skipping",
                              is_final, len(audio) / self.sample_rate)
                if self.stats is not None:
                    self.stats.record_drop("stt_error")
                # Ensure the overlay doesn't keep partial words from a failed segment.
                try:
                    self.display_queue.put({"type": "final_text", "text": "", "drop": True})
                except Exception:
                    pass
                # Reset streaming state so the next segment starts clean.
                self._reset_partial_state()
        if self._diarizer_pool is not None:
            self._diarizer_pool.shutdown(wait=False)
        log.info("Transcription stopped")
