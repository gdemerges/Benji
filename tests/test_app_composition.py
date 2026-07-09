"""Composition root : phases non-Qt pilotables + teardown robuste.

On ne lance pas la boucle Qt ni l'audio ici ; on vérifie que le câblage
(configs injectables, injection du token de compte, arrêt idempotent) est
testable en isolation — c'est justement ce que la god-function `main()`
empêchait.
"""

from __future__ import annotations

from benji.app import AppConfigs, BenjiApplication
from benji.config import LLMConfig, STTConfig


def test_configs_are_injectable():
    cfg = AppConfigs(stt=STTConfig(model_size="tiny"), llm=LLMConfig(backend_url="http://x"))
    app = BenjiApplication(cfg)
    assert app.cfg.stt.model_size == "tiny"
    assert app.cfg.llm.backend_url == "http://x"


def test_account_token_injected_into_llm_config(monkeypatch):
    class _FakeSession:
        def access_token(self):
            return "acc_123"

    # build_session est importé dans la méthode ; on patche à la source.
    monkeypatch.setattr("benji.account.build_session", lambda url: _FakeSession())

    app = BenjiApplication()
    app._build_account()
    assert app.session is not None
    assert app.cfg.llm.backend_token == "acc_123"


def test_no_token_leaves_backend_token_untouched(monkeypatch):
    class _AnonSession:
        def access_token(self):
            return None

    monkeypatch.setattr("benji.account.build_session", lambda url: _AnonSession())

    app = BenjiApplication()
    assert app.cfg.llm.backend_token is None
    app._build_account()
    assert app.cfg.llm.backend_token is None


def test_shutdown_is_safe_before_run():
    # Tous les composants sont None sur une instance non démarrée : shutdown()
    # ne doit rien tenter d'invalide (garantit un arrêt propre même si le
    # démarrage a échoué à mi-chemin).
    app = BenjiApplication()
    app.shutdown()  # ne doit pas lever
    assert app.stt_stopping.is_set()
