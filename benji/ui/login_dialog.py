"""Dialogue de connexion / inscription au compte Benji.

Modal, sur le thread Qt. La requête réseau (login/register) est rapide (un POST)
et reste synchrone ; le bouton passe en « Connexion… » le temps de l'appel.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from benji.account import AuthError, Session


class LoginDialog(QDialog):
    def __init__(self, session: Session, parent=None):
        super().__init__(parent)
        self._session = session
        self.setWindowTitle("Compte Benji")
        self.setModal(True)
        self.setMinimumWidth(340)

        self._email = QLineEdit()
        self._email.setPlaceholderText("vous@exemple.com")
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setPlaceholderText("Mot de passe")

        form = QFormLayout()
        form.addRow("Email", self._email)
        form.addRow("Mot de passe", self._password)

        self._error = QLabel()
        self._error.setStyleSheet("color: #d9534f;")
        self._error.setWordWrap(True)
        self._error.hide()

        self._login_btn = QPushButton("Se connecter")
        self._login_btn.setDefault(True)
        self._login_btn.clicked.connect(self._do_login)
        self._register_btn = QPushButton("Créer un compte")
        self._register_btn.clicked.connect(self._do_register)

        buttons = QHBoxLayout()
        buttons.addWidget(self._register_btn)
        buttons.addStretch(1)
        buttons.addWidget(self._login_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Connecte-toi pour retrouver ton abonnement\n"
                                "sur tous tes appareils."))
        layout.addLayout(form)
        layout.addWidget(self._error)
        layout.addLayout(buttons)

        self._password.returnPressed.connect(self._do_login)

    def _credentials(self) -> tuple[str, str] | None:
        email = self._email.text().strip()
        password = self._password.text()
        if not email or not password:
            self._show_error("Email et mot de passe requis.")
            return None
        return email, password

    def _attempt(self, action, label: str) -> None:
        creds = self._credentials()
        if creds is None:
            return
        self._error.hide()
        self._set_busy(True, label)
        try:
            action(*creds)
        except AuthError as e:
            self._show_error(str(e))
            return
        finally:
            self._set_busy(False, label)
        self.accept()

    def _do_login(self) -> None:
        self._attempt(self._session.login, "Se connecter")

    def _do_register(self) -> None:
        self._attempt(self._session.register, "Créer un compte")

    def _set_busy(self, busy: bool, label: str) -> None:
        self._login_btn.setEnabled(not busy)
        self._register_btn.setEnabled(not busy)
        if busy:
            self._login_btn.setText("Connexion…")
        else:
            self._login_btn.setText("Se connecter")
            self._register_btn.setText("Créer un compte")

    def _show_error(self, msg: str) -> None:
        self._error.setText(msg)
        self._error.show()
