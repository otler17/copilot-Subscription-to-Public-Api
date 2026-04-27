"""Smoke tests for the gateway and key store."""
from __future__ import annotations

import os
import tempfile

import pytest

# isolate test data dir
os.environ["C2P_DATA_DIR"] = tempfile.mkdtemp(prefix="c2p-test-")

from fastapi.testclient import TestClient  # noqa: E402

from c2p import app as app_module  # noqa: E402
from c2p import keystore  # noqa: E402


@pytest.fixture
def client():
    return TestClient(app_module.app)


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_missing_key(client):
    r = client.get("/v1/models")
    assert r.status_code == 401


def test_invalid_key(client):
    r = client.get("/v1/models", headers={"Authorization": "Bearer sk-bogus"})
    assert r.status_code == 401


def test_keystore_roundtrip():
    k = keystore.add_key("unit-test", max_rpm=5, allow_models=["gpt-4.1"])
    assert k.secret.startswith("sk-unit-test-")
    found = keystore.lookup(k.secret)
    assert found and found.name == "unit-test"
    assert keystore.revoke("unit-test") is True
    assert keystore.lookup(k.secret) is None
