"""Simulation domain validation errors."""


class SimulationValidationError(Exception):
    """Raised when a simulation operation conflicts with team state."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
