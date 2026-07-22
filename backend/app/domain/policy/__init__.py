"""Versioned readiness scoring policy registry."""

from app.domain.policy import v1

DEFAULT_POLICY_VERSION = v1.POLICY_VERSION

_POLICY_MODULES = {
    v1.POLICY_VERSION: v1,
}


def get_policy(version: str | None = None):
    if version is None:
        version = DEFAULT_POLICY_VERSION
    if version not in _POLICY_MODULES:
        raise ValueError(f"Unknown policy version: {version}")
    return _POLICY_MODULES[version]
