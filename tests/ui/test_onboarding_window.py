"""Assistant de premier lancement : navigation et états visibles."""

import pytest

from benji import onboarding


@pytest.fixture
def window(qtbot, tmp_path, monkeypatch):
    # Cache vide : l'écran des modèles doit proposer un téléchargement.
    monkeypatch.setattr(onboarding, "hf_cache_root", lambda: tmp_path / "hf")
    monkeypatch.setattr(onboarding, "microphone_status", lambda: onboarding.UNDETERMINED)
    from benji.ui.onboarding_window import OnboardingWindow

    w = OnboardingWindow()
    qtbot.addWidget(w)
    return w


def test_trois_etapes_dans_l_ordre(window):
    assert window.pages.count() == 3
    assert window.pages.currentIndex() == 0
    assert window.next_btn.text() == "Commencer"
    assert window.back_btn.isHidden()

    window._next()
    assert window.pages.currentIndex() == 1
    assert window.next_btn.text() == "Continuer"

    window._next()
    assert window.next_btn.text() == "Terminer"


def test_l_ecran_des_modeles_annonce_la_taille(window):
    text = window.models_body.text()

    assert "4,1 Go" in text
    assert not window.download_btn.isHidden()


def test_les_modeles_deja_presents_ne_proposent_rien(qtbot, monkeypatch, tmp_path):
    monkeypatch.setattr(onboarding, "missing_models", lambda *a: [])
    from benji.ui.onboarding_window import OnboardingWindow

    w = OnboardingWindow()
    qtbot.addWidget(w)

    assert "déjà sur votre Mac" in w.models_body.text()
    assert w.download_btn.isHidden()


def test_un_refus_du_micro_explique_la_reparation(window):
    """macOS ne redemande jamais après un refus : sans ce message, l'app reste
    muette et l'utilisateur ne sait pas pourquoi."""
    window._on_mic_result(False)

    assert "Réglages Système" in window.mic_status.text()
    assert window.mic_btn.text() == "Ouvrir les Réglages Système"
    assert window.mic_btn.isEnabled()


def test_un_accord_ferme_l_etape(window):
    window._on_mic_result(True)

    assert window.mic_status.text() == "Micro autorisé."
    assert not window.mic_btn.isEnabled()


def test_terminer_pose_le_marqueur(window, tmp_path, monkeypatch):
    marker = tmp_path / onboarding.MARKER_NAME
    monkeypatch.setattr(onboarding, "marker_path", lambda: marker)
    window.pages.setCurrentIndex(2)

    window._next()

    assert onboarding.needs_onboarding(marker) is False


def test_on_ne_peut_pas_sortir_pendant_un_telechargement(window):
    """Quitter au milieu laisserait un cache à moitié écrit."""
    window.pages.setCurrentIndex(2)
    window._downloader = object()
    window._refresh_nav()

    assert not window.next_btn.isEnabled()


def test_un_telechargement_en_echec_propose_de_reessayer(window):
    window.pages.setCurrentIndex(2)
    window._on_download_done("réseau injoignable")

    assert "réseau injoignable" in window.progress_label.text()
    assert window.download_btn.text() == "Réessayer"
    assert window.next_btn.isEnabled(), "hors ligne, on doit pouvoir aller au bout"
