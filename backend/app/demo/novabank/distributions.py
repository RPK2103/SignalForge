"""Deterministic distribution helpers (SHA-256 derived; never process hash())."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


def stable_digest(*parts: str) -> str:
    canonical = "|".join(part.strip().lower() for part in parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stable_int(*parts: str, modulo: int) -> int:
    if modulo <= 0:
        raise ValueError("modulo must be positive")
    digest = stable_digest(*parts)
    return int(digest[:16], 16) % modulo


def choose(options: Sequence[T], *parts: str) -> T:
    if not options:
        raise ValueError("options must be non-empty")
    return options[stable_int(*parts, modulo=len(options))]


def choose_weighted(options: Sequence[T], weights: Sequence[int], *parts: str) -> T:
    if len(options) != len(weights):
        raise ValueError("options and weights length mismatch")
    total = sum(weights)
    if total <= 0:
        raise ValueError("weights must sum to a positive value")
    cursor = stable_int(*parts, modulo=total)
    running = 0
    for option, weight in zip(options, weights, strict=True):
        running += weight
        if cursor < running:
            return option
    return options[-1]


def bounded_title(prefix: str, index: int, max_len: int = 120) -> str:
    raw = f"{prefix} {index:04d}"
    return raw[:max_len]
