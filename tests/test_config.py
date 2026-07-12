"""Validation de l'URL backend : HTTPS obligatoire hors loopback."""

import pytest

from benji.config import ensure_secure_backend_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8000/",
    "http://localhost:8000",
    "http://[::1]:8000",
    "https://api.benji.example.com",
    "https://api.benji.example.com:8443/v1",
])
def test_accepts_local_http_and_any_https(url):
    assert ensure_secure_backend_url(url) == url


@pytest.mark.parametrize("url", [
    "http://api.benji.example.com",
    "http://192.168.1.10:8000",
    "http://benji.internal",
])
def test_rejects_remote_http(url):
    with pytest.raises(ValueError, match="https"):
        ensure_secure_backend_url(url)


@pytest.mark.parametrize("url", [
    "ws://127.0.0.1:8000",   # la conversion http→ws se fait en aval, jamais en config
    "ftp://example.com",
    "api.benji.example.com",  # schéma manquant
])
def test_rejects_non_http_schemes(url):
    with pytest.raises(ValueError):
        ensure_secure_backend_url(url)
