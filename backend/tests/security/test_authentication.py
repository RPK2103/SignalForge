"""Adversarial authentication tests (Phase 3 Prompt 7).

Entra RS256 validation with a locally generated keypair and a fake JWKS — no
network access. Also covers local-development and test-mode boundaries.
"""

from __future__ import annotations

import time

import pytest

from app.core.config import get_settings
from app.security.authentication import (
    TEST_AUDIENCE,
    TEST_ISSUER,
    TEST_SECRET,
    AuthenticationService,
)
from app.security.config import SecuritySettings, get_security_settings
from app.security.dev_tokens import issue_symmetric_token
from app.security.enums import AuthenticationFailureCategory, AuthenticationMode
from tests.security.conftest import ENTRA_AUDIENCE, ENTRA_ISSUER, KID
from tests.security.keys import public_jwk, sign_entra_token


def _fail(verifier, token) -> AuthenticationFailureCategory:
    result = verifier.verify(token)
    assert not result.succeeded
    return result.failure_category


def test_valid_entra_token_succeeds(entra_verifier, rsa_key):
    token = sign_entra_token(rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE)
    result = entra_verifier.verify(token)
    assert result.succeeded
    assert result.principal.authentication_mode == AuthenticationMode.ENTRA_OIDC
    assert result.principal.external_tenant_id == "entra-tenant-guid"


def test_missing_token(entra_verifier):
    assert _fail(entra_verifier, "") == AuthenticationFailureCategory.MISSING_TOKEN


def test_malformed_token(entra_verifier):
    assert _fail(entra_verifier, "not-a-jwt") == AuthenticationFailureCategory.MALFORMED_TOKEN


def test_algorithm_none_rejected(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE, algorithm="none"
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM


def test_unsigned_token_rejected(entra_verifier):
    # A token with alg none and no signature segment.
    import base64
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "none", "kid": KID}).encode()).rstrip(b"=")
    payload = base64.urlsafe_b64encode(json.dumps({"sub": "x"}).encode()).rstrip(b"=")
    token = f"{header.decode()}.{payload.decode()}."
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM


def test_wrong_algorithm_hs256_rejected(entra_verifier):
    # HS256 token cannot be verified against the RSA allowlist.
    forged = issue_symmetric_token(
        secret="attacker",
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        subject="x",
        external_tenant_id="entra-tenant-guid",
    )
    assert _fail(entra_verifier, forged) == AuthenticationFailureCategory.UNSUPPORTED_ALGORITHM


def test_expired_token(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key,
        kid=KID,
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        ttl_seconds=-3600,
        issued_now=int(time.time()) - 7200,
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.EXPIRED


def test_not_yet_valid_token(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key,
        kid=KID,
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        not_before_offset=3600,
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.NOT_YET_VALID


def test_wrong_issuer(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key, kid=KID, issuer="https://evil.example/v2.0", audience=ENTRA_AUDIENCE
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.INVALID_ISSUER


def test_wrong_audience(entra_verifier, rsa_key):
    token = sign_entra_token(rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience="api://someone-else")
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.INVALID_AUDIENCE


def test_unknown_tenant(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key,
        kid=KID,
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        tenant_id="some-other-tenant",
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.UNKNOWN_TENANT


def test_missing_subject(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE, omit=("sub",)
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.MISSING_SUBJECT


def test_unknown_key_id(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key, kid="unknown-kid", issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.UNKNOWN_KEY_ID


def test_jwks_timeout(entra_verifier_with_client, rsa_key):
    verifier, fake_client = entra_verifier_with_client
    fake_client.raise_timeout = True
    token = sign_entra_token(rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE)
    assert _fail(verifier, token) == AuthenticationFailureCategory.JWKS_UNAVAILABLE


def test_jwks_malformed(entra_verifier_with_client, rsa_key):
    verifier, fake_client = entra_verifier_with_client
    fake_client.raise_malformed = True
    token = sign_entra_token(rsa_key, kid=KID, issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE)
    assert _fail(verifier, token) == AuthenticationFailureCategory.JWKS_MALFORMED


def test_key_rotation_refreshes_jwks(entra_verifier_with_client, rsa_key):
    verifier, fake_client = entra_verifier_with_client
    # Rotate to a new kid the cache has not seen; a valid token forces a refresh.
    from tests.security.keys import generate_rsa_keypair

    new_key = generate_rsa_keypair()
    fake_client.set_keys([public_jwk(new_key, "rotated-kid")])
    token = sign_entra_token(
        new_key, kid="rotated-kid", issuer=ENTRA_ISSUER, audience=ENTRA_AUDIENCE
    )
    result = verifier.verify(token)
    assert result.succeeded


def test_oversized_token_rejected(entra_verifier, rsa_key):
    token = sign_entra_token(
        rsa_key,
        kid=KID,
        issuer=ENTRA_ISSUER,
        audience=ENTRA_AUDIENCE,
        extra_claims={"padding": "x" * 20000},
    )
    assert _fail(entra_verifier, token) == AuthenticationFailureCategory.TOKEN_TOO_LARGE


# -- environment/mode boundaries ---------------------------------------------
def _security_settings(mode: AuthenticationMode, **overrides) -> SecuritySettings:
    get_security_settings.cache_clear()
    return SecuritySettings(AUTH_MODE=mode.value, **overrides)


def test_test_mode_token_works_in_development():
    settings = _security_settings(AuthenticationMode.TEST)
    service = AuthenticationService(settings, "development")
    token = issue_symmetric_token(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        subject="s",
        external_tenant_id="novabank",
        roles=["tenant_admin"],
    )
    assert service.authenticate(token).succeeded


def test_test_mode_impossible_in_production():
    settings = _security_settings(AuthenticationMode.TEST)
    service = AuthenticationService(settings, "production")
    token = issue_symmetric_token(
        secret=TEST_SECRET,
        issuer=TEST_ISSUER,
        audience=TEST_AUDIENCE,
        subject="s",
        external_tenant_id="novabank",
    )
    result = service.authenticate(token)
    assert not result.succeeded
    assert result.failure_category == AuthenticationFailureCategory.MODE_NOT_PERMITTED


def test_local_development_mode_impossible_in_production():
    settings = _security_settings(
        AuthenticationMode.LOCAL_DEVELOPMENT,
        SIGNALFORGE_LOCAL_AUTH_SECRET="x" * 40,
    )
    service = AuthenticationService(settings, "production")
    result = service.authenticate("anything")
    assert not result.succeeded
    assert result.failure_category == AuthenticationFailureCategory.MODE_NOT_PERMITTED


def test_local_development_token_roundtrip():
    settings = _security_settings(
        AuthenticationMode.LOCAL_DEVELOPMENT,
        SIGNALFORGE_LOCAL_AUTH_SECRET="dev-secret-strong-enough-abcdefghij-1234",
    )
    service = AuthenticationService(settings, "development")
    token = issue_symmetric_token(
        secret=settings.local_auth_secret,
        issuer=settings.local_dev_issuer,
        audience=settings.local_dev_audience,
        subject="dev-user",
        external_tenant_id="novabank",
        roles=["executive_reader"],
    )
    result = service.authenticate(token)
    assert result.succeeded
    assert result.principal.claimed_roles == ("executive_reader",)


@pytest.fixture(autouse=True)
def _restore_caches():
    yield
    get_security_settings.cache_clear()
    get_settings.cache_clear()
