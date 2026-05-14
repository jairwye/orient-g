import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.main import app


def test_startup_rejects_default_auth_secret_when_enforced(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "enforce_non_default_auth_secret", True)
    monkeypatch.setattr(settings, "auth_secret", "orient-g-auth-secret-change-in-production")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_startup_rejects_default_auth_secret_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "enforce_non_default_auth_secret", False)
    monkeypatch.setattr(settings, "auth_secret", "orient-g-auth-secret-change-in-production")
    monkeypatch.setattr(settings, "db_migration_mode", "alembic")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass


def test_startup_rejects_legacy_migration_mode_in_production(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "enforce_non_default_auth_secret", False)
    monkeypatch.setattr(settings, "auth_secret", "not-default-secret")
    monkeypatch.setattr(settings, "db_migration_mode", "legacy")
    with pytest.raises(RuntimeError):
        with TestClient(app):
            pass

