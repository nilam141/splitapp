"""Trusted-proxy handling for the login IP rate limit: X-Forwarded-For is ignored unless configured."""
from types import SimpleNamespace

from app.config import settings
from app.routers.auth import client_ip


def _req(xff=None, peer="10.0.0.1"):
    headers = {"x-forwarded-for": xff} if xff is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_default_ignores_forwarded_header(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 0)
    assert client_ip(_req("1.2.3.4")) == "10.0.0.1"


def test_one_proxy_uses_last_entry_not_spoofed_prefix(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 1)
    assert client_ip(_req("6.6.6.6, 203.0.113.9")) == "203.0.113.9"


def test_two_proxies(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert client_ip(_req("6.6.6.6, 203.0.113.9, 10.1.1.1")) == "203.0.113.9"


def test_missing_or_short_header_falls_back_to_peer(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_count", 2)
    assert client_ip(_req(None)) == "10.0.0.1"
    assert client_ip(_req("203.0.113.9")) == "10.0.0.1"
