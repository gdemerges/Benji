"""Client de facturation : déclenche le paiement Stripe via le backend Benji.

Le poste n'a **aucune** clé Stripe. Il appelle le backend authentifié (Bearer),
récupère l'URL de Checkout (passage Pro) ou du portail (gestion/résiliation), et
l'ouvre dans le navigateur. Tout le secret (clé Stripe, prix) reste côté serveur
(cf. docs/cloud-architecture.md). Endpoints : docs/api-contract.md §7.
"""

from __future__ import annotations

import logging
import webbrowser

log = logging.getLogger(__name__)


class BillingClient:
    def __init__(
        self,
        base_url: str,
        token: str | None,
        *,
        timeout: float = 30.0,
        transport=None,  # httpx transport injectable (tests)
    ):
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport

    def _post(self, path: str) -> dict:
        if not self._token:
            raise RuntimeError("Connexion au compte requise (jeton backend absent).")

        import httpx

        headers = {"Authorization": f"Bearer {self._token}"}
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            resp = client.post(f"{self._base_url}{path}", headers=headers)
        if resp.status_code != 200:
            raise RuntimeError(f"Backend a répondu {resp.status_code}: {resp.text}")
        return resp.json()

    def checkout_url(self) -> str:
        """URL de Checkout Stripe pour souscrire l'abonnement Pro."""
        return self._post("/v1/billing/checkout")["checkout_url"]

    def portal_url(self) -> str:
        """URL du Billing Portal Stripe (changer de carte, résilier…)."""
        return self._post("/v1/billing/portal")["portal_url"]


def open_checkout(base_url: str, token: str | None) -> None:
    """Ouvre la page de paiement Stripe dans le navigateur (peut bloquer/réseau)."""
    webbrowser.open(BillingClient(base_url, token).checkout_url())


def open_portal(base_url: str, token: str | None) -> None:
    """Ouvre le portail de gestion d'abonnement dans le navigateur."""
    webbrowser.open(BillingClient(base_url, token).portal_url())
