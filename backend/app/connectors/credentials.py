"""Credential resolvers — never persist or log resolved secret values."""

from __future__ import annotations

import os
import re
from typing import Protocol, runtime_checkable

from app.connectors.errors import ConnectorError
from app.domain.enterprise_enums import ConnectorErrorCategory

# Allowlisted opaque reference formats only. Raw tokens are rejected.
# env:// may only reference SIGNALFORGE_* variables (no arbitrary process env reads).
_ENV_REF = re.compile(r"^env://(SIGNALFORGE_[A-Z][A-Z0-9_]{0,51})$")
_VAULT_REF = re.compile(r"^vault://[a-z0-9][a-z0-9\-_/]{0,200}#[a-z0-9_\-]{1,64}$")
_PUBLIC_REF = re.compile(r"^public://none$")

_RAW_SECRET_HINTS = re.compile(
    r"^(ghp_|gho_|ghu_|ghs_|ghr_|github_pat_|sk-|xox[baprs]-)",
    re.IGNORECASE,
)


class ResolvedCredential:
    """Opaque wrapper; ``__repr__`` never reveals the token."""

    __slots__ = ("_token", "reference")

    def __init__(self, reference: str, token: str | None) -> None:
        self.reference = reference
        self._token = token

    @property
    def token(self) -> str | None:
        return self._token

    def __repr__(self) -> str:
        return (
            f"ResolvedCredential(reference={self.reference!r}, has_token={self._token is not None})"
        )

    def __str__(self) -> str:
        return self.__repr__()


@runtime_checkable
class CredentialResolver(Protocol):
    def resolve(self, credential_reference: str | None) -> ResolvedCredential: ...


def validate_credential_reference(reference: str | None) -> str | None:
    """Validate allowlisted reference formats; reject apparent raw secrets."""
    if reference is None or reference == "":
        return None
    if _RAW_SECRET_HINTS.match(reference.strip()):
        raise ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            "Raw secret values are not allowed in credential_reference",
            retryable=False,
        )
    if _PUBLIC_REF.match(reference) or _ENV_REF.match(reference) or _VAULT_REF.match(reference):
        return reference
    if reference.startswith("env://"):
        raise ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            "env:// credential references must use an allowlisted SIGNALFORGE_* variable",
            retryable=False,
        )
    raise ConnectorError(
        ConnectorErrorCategory.INVALID_CONFIGURATION,
        "credential_reference must be env://SIGNALFORGE_*, vault://...#key, or public://none",
        retryable=False,
    )


class PublicCredentialResolver:
    """Supports unauthenticated public provider access; returns no token."""

    def resolve(self, credential_reference: str | None) -> ResolvedCredential:
        if credential_reference in (None, "", "public://none"):
            return ResolvedCredential(credential_reference or "public://none", None)
        raise ConnectorError(
            ConnectorErrorCategory.INVALID_CONFIGURATION,
            "PublicCredentialResolver only accepts public://none or empty reference",
            retryable=False,
        )


class EnvironmentCredentialResolver:
    """Local/CI-only resolver for ``env://VAR_NAME`` references.

    Never persists the resolved value. Azure Key Vault integration is deferred.
    """

    def resolve(self, credential_reference: str | None) -> ResolvedCredential:
        validated = validate_credential_reference(credential_reference)
        if validated is None or validated == "public://none":
            return ResolvedCredential(validated or "public://none", None)
        match = _ENV_REF.match(validated)
        if match is None:
            if _VAULT_REF.match(validated):
                raise ConnectorError(
                    ConnectorErrorCategory.MISSING_CREDENTIAL,
                    "vault:// credential references require Prompt 7 secret-store integration",
                    retryable=False,
                )
            raise ConnectorError(
                ConnectorErrorCategory.INVALID_CONFIGURATION,
                "Unsupported credential_reference format",
                retryable=False,
            )
        env_name = match.group(1)
        value = os.environ.get(env_name)
        if value is None or value == "":
            raise ConnectorError(
                ConnectorErrorCategory.MISSING_CREDENTIAL,
                f"Environment variable for credential reference is not set ({env_name})",
                retryable=False,
            )
        return ResolvedCredential(validated, value)


class ChainedCredentialResolver:
    """Try public, then environment resolvers."""

    def __init__(self) -> None:
        self._public = PublicCredentialResolver()
        self._env = EnvironmentCredentialResolver()

    def resolve(self, credential_reference: str | None) -> ResolvedCredential:
        validated = validate_credential_reference(credential_reference)
        if validated is None or validated == "public://none":
            return self._public.resolve(validated)
        return self._env.resolve(validated)
