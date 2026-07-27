"""Regression tests for CORS_ORIGINS parsing in Settings.

Covers the Phase 2 CORS hardening: comma-separated, JSON-array, wildcard,
plain single origin, whitespace normalization, and safe defaults. The list
field is annotated with ``NoDecode`` so pydantic-settings does not attempt to
JSON-decode the raw env value before the validator runs.
"""

import pytest

from app.core.config import DEFAULT_DEV_CORS_ORIGINS, Settings

DEFAULT_ORIGINS = [
    origin.strip() for origin in DEFAULT_DEV_CORS_ORIGINS.split(",") if origin.strip()
]


def parse(value: object) -> list[str]:
    return Settings.parse_cors_origins(value)


def test_single_plain_origin():
    assert parse("https://app.example.com") == ["https://app.example.com"]


def test_comma_separated_origins():
    assert parse("https://a.com,https://b.com") == ["https://a.com", "https://b.com"]


def test_comma_separated_with_whitespace_is_normalized():
    assert parse("  https://a.com , https://b.com  ") == [
        "https://a.com",
        "https://b.com",
    ]


def test_json_array_string():
    assert parse('["https://a.com", "https://b.com"]') == [
        "https://a.com",
        "https://b.com",
    ]


def test_wildcard_preserved():
    assert parse("*") == ["*"]


def test_empty_string_falls_back_to_dev_defaults():
    assert parse("") == DEFAULT_ORIGINS


def test_none_falls_back_to_dev_defaults():
    assert parse(None) == DEFAULT_ORIGINS


def test_list_input_is_normalized():
    assert parse(["https://a.com", " https://b.com "]) == [
        "https://a.com",
        "https://b.com",
    ]


def test_invalid_type_raises():
    with pytest.raises(TypeError):
        parse(123)


def test_env_driven_json_array(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ORIGINS", '["https://prod.example.com","https://admin.example.com"]')
    settings = Settings()
    assert settings.cors_origins == [
        "https://prod.example.com",
        "https://admin.example.com",
    ]


def test_env_driven_comma_separated(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://x.com,https://y.com")
    settings = Settings()
    assert settings.cors_origins == ["https://x.com", "https://y.com"]


def test_default_when_unset(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    settings = Settings()
    assert settings.cors_origins == DEFAULT_ORIGINS
