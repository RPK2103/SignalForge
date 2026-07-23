"""Persistence-layer exceptions mapped to controlled API errors."""


class PersistenceError(Exception):
    """Base persistence error."""

    error_type: str = "persistence_error"
    status_code: int = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class RecordNotFoundError(PersistenceError):
    error_type = "record_not_found"
    status_code = 404


class DatabaseUnavailableError(PersistenceError):
    error_type = "database_unavailable"
    status_code = 503


class PersistenceConflictError(PersistenceError):
    error_type = "persistence_conflict"
    status_code = 409


class SnapshotIntegrityError(PersistenceError):
    error_type = "snapshot_integrity_error"
    status_code = 500


class PersistenceValidationError(PersistenceError):
    error_type = "validation_error"
    status_code = 422


class LeadershipBriefGenerationFailed(PersistenceError):
    error_type = "leadership_brief_generation_failed"
    status_code = 500
