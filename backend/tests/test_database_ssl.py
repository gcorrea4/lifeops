"""TLS options for managed MySQL (DB_SSL_CA). No database connection is made."""

from app import database
from app.core.settings import settings


def test_connect_args_empty_without_ca(monkeypatch):
    monkeypatch.setattr(settings, "DB_SSL_CA", "")
    assert database._connect_args() == {}


def test_connect_args_use_ca_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "DB_SSL_CA", "/certs/ca.pem")
    assert database._connect_args() == {"ssl": {"ca": "/certs/ca.pem"}}
