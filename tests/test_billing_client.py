"""BillingClient : appels checkout/portail vers le backend, sans réseau (httpx mocké)."""

import httpx
import pytest

from benji.billing import BillingClient


def _transport(handler):
    return httpx.MockTransport(handler)


def test_checkout_url_sends_bearer_and_returns_url():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"checkout_url": "https://stripe.test/c/abc"})

    client = BillingClient("http://test/", token="tok", transport=_transport(handler))
    assert client.checkout_url() == "https://stripe.test/c/abc"
    assert str(seen[0].url) == "http://test/v1/billing/checkout"
    assert seen[0].headers["authorization"] == "Bearer tok"


def test_portal_url_returns_url():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/billing/portal"
        return httpx.Response(200, json={"portal_url": "https://stripe.test/p/xyz"})

    client = BillingClient("http://test", token="tok", transport=_transport(handler))
    assert client.portal_url() == "https://stripe.test/p/xyz"


def test_missing_token_raises_before_network():
    # Aucun appel réseau ne doit partir sans jeton.
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("ne doit pas être appelé")

    client = BillingClient("http://test", token=None, transport=_transport(handler))
    with pytest.raises(RuntimeError, match="Connexion au compte"):
        client.checkout_url()


def test_backend_error_raised():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, text="payment required")

    client = BillingClient("http://test", token="tok", transport=_transport(handler))
    with pytest.raises(RuntimeError, match="402"):
        client.checkout_url()
