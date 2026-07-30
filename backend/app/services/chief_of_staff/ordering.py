"""Deterministic ordering helpers for Chief of Staff evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Sequence, TypeVar

T = TypeVar("T")

_SEVERITY_RANK = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
    "unknown": 5,
}


def severity_rank(value: str | None) -> int:
    if not value:
        return 99
    return _SEVERITY_RANK.get(str(value).lower(), 50)


def _ts_desc(value: datetime | None) -> float:
    if value is None:
        return float("-inf")
    return -value.timestamp()


def order_by(
    items: Sequence[T],
    *key_fns: Callable[[T], Any],
) -> list[T]:
    return sorted(items, key=lambda item: tuple(fn(item) for fn in key_fns))


def order_risks(items: Sequence[T], *, severity_attr: str, id_attr: str) -> list[T]:
    return order_by(
        items,
        lambda i: severity_rank(getattr(i, severity_attr, None)),
        lambda i: getattr(i, id_attr),
    )


def order_by_event_then_id(
    items: Sequence[T],
    *,
    event_attr: str,
    id_attr: str,
) -> list[T]:
    return order_by(
        items,
        lambda i: _ts_desc(getattr(i, event_attr, None)),
        lambda i: getattr(i, id_attr),
    )
