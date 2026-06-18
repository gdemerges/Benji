"""Abstraction de provider pour le résumé : moteur local (mlx-lm) ou cloud (Claude).

Le `SummaryWorker` ne connaît que l'interface `SummaryProvider` ; le choix
concret vient de `LLMConfig` (cf. `benji/config.py`). Le mode local reste le
défaut — rien ne sort du Mac tant que l'utilisateur n'active pas le cloud.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from benji.llm import summarizer

log = logging.getLogger(__name__)

OnToken = Callable[[str], None]


@runtime_checkable
class SummaryProvider(Protocol):
    name: str

    def summarize(
        self, entries: list[dict], on_token: OnToken | None = None
    ) -> str | None: ...


class LocalSummaryProvider:
    """Résumé via mlx-lm sur Apple Silicon (défaut, 100 % local)."""

    name = "local"

    def summarize(
        self, entries: list[dict], on_token: OnToken | None = None
    ) -> str | None:
        return summarizer.summarize(entries, on_token=on_token)


class CloudSummaryProvider:
    """Résumé via l'API Claude (Anthropic), en streaming.

    La transcription (texte uniquement) quitte le poste — usage opt-in.
    """

    name = "cloud"

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        max_tokens: int = 2048,
    ):
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        self._client = None  # construit paresseusement (1er résumé cloud)

    def _get_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise RuntimeError(
                    "Le résumé cloud nécessite le paquet 'anthropic'. "
                    "Installe-le : uv sync --extra cloud"
                ) from e
            # api_key=None → l'SDK résout ANTHROPIC_API_KEY depuis l'environnement.
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def summarize(
        self, entries: list[dict], on_token: OnToken | None = None
    ) -> str | None:
        transcription_text = summarizer.prepare_transcription(entries)
        if transcription_text is None:
            return None

        client = self._get_client()
        log.info("Génération du résumé via Claude (%s)…", self._model)

        chunks: list[str] = []
        with client.messages.stream(
            model=self._model,
            max_tokens=self._max_tokens,
            system=summarizer.SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": summarizer.build_user_prompt(transcription_text),
                }
            ],
        ) as stream:
            for delta in stream.text_stream:
                if not delta:
                    continue
                chunks.append(delta)
                if on_token is not None:
                    try:
                        on_token(delta)
                    except Exception as e:
                        log.warning("on_token callback failed: %s", e)

        return "".join(chunks).strip() or None


def build_summary_provider(cfg) -> SummaryProvider:
    """Construit le provider de résumé d'après `LLMConfig`."""
    if getattr(cfg, "summary_provider", "local") == "cloud":
        return CloudSummaryProvider(
            model=cfg.cloud_model,
            api_key=cfg.anthropic_api_key,
            max_tokens=cfg.cloud_max_tokens,
        )
    return LocalSummaryProvider()
