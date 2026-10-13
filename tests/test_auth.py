"""Tests de autenticación: registro, login, refresh, /me."""
import pytest


def test_register_user_without_tenant(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "test@example.com",
        "password": "test1234",
        "full_name": "Test User",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["user"]["email"] == "test@example.com"
    assert data["current_tenant"] is None
    assert "access_token" in data
    assert "refresh_token" in data


def test_register_user_with_tenant(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "maria@cafenorte.cl",
        "password": "demo1234",
        "full_name": "María González",
        "create_tenant": True,
        "tenant_legal_name": "Café Norte SpA",
        "tenant_slug": "cafe-norte",
        "tenant_industry": "gastro",
    })
    assert r.status_code == 201, r.text
    data = r.json()
    assert data["current_tenant"] is not None
    assert data["current_tenant"]["tenant_slug"] == "cafe-norte"
    assert data["current_tenant"]["is_owner"] is True


def test_register_duplicate_email(client):
    client.post("/api/v1/auth/register", json={
        "email": "dup@example.com", "password": "test1234", "full_name": "User",
    })
    r = client.post("/api/v1/auth/register", json={
        "email": "dup@example.com", "password": "test1234", "full_name": "User2",
    })
    assert r.status_code == 409


def test_register_weak_password(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "weak@example.com", "password": "12345678", "full_name": "X",
    })
    assert r.status_code == 422


def test_login_success(client):
    client.post("/api/v1/auth/register", json={
        "email": "u@e.com", "password": "test1234", "full_name": "Test User",
    })
    r = client.post("/api/v1/auth/login", json={"email": "u@e.com", "password": "test1234"})
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["email"] == "u@e.com"


def test_login_wrong_password(client):
    client.post("/api/v1/auth/register", json={
        "email": "u@e.com", "password": "test1234", "full_name": "Test User",
    })
    r = client.post("/api/v1/auth/login", json={"email": "u@e.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_refresh_token(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "r@e.com", "password": "test1234", "full_name": "Refresh User",
    })
    refresh = r.json()["refresh_token"]
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_me_requires_auth(client):
    r = client.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_me_with_token(client):
    r = client.post("/api/v1/auth/register", json={
        "email": "me@e.com", "password": "test1234", "full_name": "ME",
    })
    token = r.json()["access_token"]
    r = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["email"] == "me@e.com"
