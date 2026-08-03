"""Enable ``python -m app.observability`` to run the observability CLI."""

from __future__ import annotations

from app.observability.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
