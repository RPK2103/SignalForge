"""Unit-level pending-UoW telemetry semantics (Prompt 8).

Proves the UnitOfWork pending queue is instance-local, flushes only after a
durable commit, clears on rollback/commit-failure, does not re-emit on a second
commit, and never undoes committed business data when the provider fails.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.db.unit_of_work import UnitOfWork
from app.observability.domain import record_cos_review
from app.observability.metrics import MetricName
from app.observability.provider import InMemoryObservabilityProvider
from app.observability.runtime import reset_observability_provider, set_observability_provider


@pytest.fixture
def obs_provider() -> InMemoryObservabilityProvider:
    provider = InMemoryObservabilityProvider()
    set_observability_provider(provider)
    try:
        yield provider
    finally:
        reset_observability_provider()


def test_one_queued_event_flushes_on_commit(uow, obs_provider):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 1


def test_multiple_queued_events_flush_on_commit(uow, obs_provider):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="rejected"))
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="rejected") == 1
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 2


def test_rollback_clears_pending(uow, obs_provider):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    uow.rollback()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_commit_failure_clears_pending(uow, obs_provider, monkeypatch):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))

    def _boom():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(uow.session, "commit", _boom)
    with pytest.raises(RuntimeError, match="commit failed"):
        uow.commit()
    # Queues cleared by commit() itself on failure — a follow-up empty commit
    # must not emit the discarded success.
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0
    monkeypatch.undo()
    uow.rollback()
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_second_commit_does_not_re_emit(uow, obs_provider):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 1
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 1


def test_close_without_commit_leaves_no_emitted_success(db_session, obs_provider):
    uow = UnitOfWork(db_session)
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    db_session.close()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 0


def test_provider_failure_during_flush_does_not_raise(uow):
    class ExplodingProvider(InMemoryObservabilityProvider):
        def increment(self, *a, **k):
            raise RuntimeError("telemetry boom")

    set_observability_provider(ExplodingProvider())
    try:
        uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
        # Commit of business data succeeds; telemetry fail-open must not raise.
        uow.commit()
    finally:
        reset_observability_provider()


def test_two_concurrent_uows_do_not_share_pending(migrated_db, obs_provider):
    engine = get_engine(migrated_db)
    with Session(engine) as session_a, Session(engine) as session_b:
        uow_a = UnitOfWork(session_a)
        uow_b = UnitOfWork(session_b)
        uow_a.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
        uow_b.note_pending_telemetry(lambda: record_cos_review(outcome="rejected"))
        uow_a.commit()
        assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 1
        assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="rejected") == 0
        uow_b.rollback()
        assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="rejected") == 0
        assert obs_provider.counter_total(MetricName.COS_REVIEWS) == 1


def test_reuse_after_rollback_queues_freshly(uow, obs_provider):
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="accepted"))
    uow.rollback()
    uow.note_pending_telemetry(lambda: record_cos_review(outcome="corrected"))
    uow.commit()
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="accepted") == 0
    assert obs_provider.counter_total(MetricName.COS_REVIEWS, outcome="corrected") == 1
