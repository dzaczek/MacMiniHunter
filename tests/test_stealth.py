"""Tests for stealth utilities."""

import pytest
from src.utils.stealth import get_random_user_agent, create_session, FALLBACK_USER_AGENTS


def test_get_random_user_agent_returns_string():
    ua = get_random_user_agent()
    assert isinstance(ua, str)
    assert len(ua) > 20


def test_create_session_has_headers():
    session = create_session()
    assert "User-Agent" in session.headers
    assert "Accept-Language" in session.headers
    assert "de-CH" in session.headers["Accept-Language"]


def test_create_session_with_proxy():
    session = create_session(proxy="http://proxy:8080")
    assert session.proxies["http"] == "http://proxy:8080"
    assert session.proxies["https"] == "http://proxy:8080"


def test_fallback_user_agents_are_valid():
    for ua in FALLBACK_USER_AGENTS:
        assert "Mozilla" in ua
        assert len(ua) > 50
