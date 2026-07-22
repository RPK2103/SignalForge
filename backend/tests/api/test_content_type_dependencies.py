"""Unit tests for JSON Content-Type validation helpers."""

import pytest

from app.api.dependencies import is_json_media_type


@pytest.mark.parametrize(
    "content_type",
    [
        "application/json",
        "application/json; charset=utf-8",
        "Application/JSON",
        "application/vnd.api+json",
        "application/problem+json",
        "application/ld+json",
    ],
)
def test_accepts_json_media_types(content_type: str):
    assert is_json_media_type(content_type) is True


@pytest.mark.parametrize(
    "content_type",
    [
        "",
        "text/plain",
        "application/xml",
        "text/xml",
        "multipart/form-data",
        "application/javascript",
        "text/json",
    ],
)
def test_rejects_non_json_media_types(content_type: str):
    assert is_json_media_type(content_type) is False
