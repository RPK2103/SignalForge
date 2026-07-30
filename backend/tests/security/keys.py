"""Locally generated RSA keys + fake JWKS for Entra JWT tests.

No network access is required: unit tests generate a keypair, publish its public
JWK through a fake JWKS client, and sign RS256 tokens with the private key.
"""

from __future__ import annotations

import json
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.security.jwks import JwksClient, JwksProviderError


def generate_rsa_keypair() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def public_jwk(private_key: rsa.RSAPrivateKey, kid: str) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    jwk["alg"] = "RS256"
    jwk["use"] = "sig"
    return jwk


def sign_entra_token(
    private_key: rsa.RSAPrivateKey,
    *,
    kid: str,
    issuer: str,
    audience: str,
    subject: str = "user-subject",
    tenant_id: str = "entra-tenant-guid",
    algorithm: str = "RS256",
    ttl_seconds: int = 300,
    not_before_offset: int = 0,
    issued_now: int | None = None,
    extra_claims: dict | None = None,
    omit: tuple[str, ...] = (),
) -> str:
    now = int(issued_now if issued_now is not None else time.time())
    payload: dict = {
        "sub": subject,
        "iss": issuer,
        "aud": audience,
        "tid": tenant_id,
        "iat": now,
        "nbf": now + not_before_offset,
        "exp": now + ttl_seconds,
    }
    if extra_claims:
        payload.update(extra_claims)
    for claim in omit:
        payload.pop(claim, None)
    key = None if algorithm == "none" else private_key
    headers = {"kid": kid}
    return jwt.encode(payload, key, algorithm=algorithm, headers=headers)


class FakeJwksClient(JwksClient):
    """In-memory JWKS client that can simulate provider failures."""

    def __init__(self, keys: list[dict]) -> None:
        self._keys = keys
        self.calls = 0
        self.raise_timeout = False
        self.raise_malformed = False

    def set_keys(self, keys: list[dict]) -> None:
        self._keys = keys

    def fetch(self, uri: str) -> list[dict]:
        self.calls += 1
        if self.raise_timeout:
            from app.security.enums import AuthenticationFailureCategory

            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_UNAVAILABLE, "jwks request timed out"
            )
        if self.raise_malformed:
            from app.security.enums import AuthenticationFailureCategory

            raise JwksProviderError(
                AuthenticationFailureCategory.JWKS_MALFORMED, "jwks response was not valid json"
            )
        return list(self._keys)
