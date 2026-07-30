"""Local security CLI (Phase 3 Prompt 7).

Issues short-lived development tokens and seeds synthetic NovaBank security
fixtures. There is intentionally NO public API endpoint that issues tokens.

Development-token issuance requires ``local_development`` mode and a strong
``SIGNALFORGE_LOCAL_AUTH_SECRET``; production rejects the mode entirely.
"""

from __future__ import annotations

import argparse
import json
import sys

from app.core.config import get_settings
from app.db.session import get_engine, init_engine
from app.security.config import get_security_settings
from app.security.dev_tokens import issue_symmetric_token
from app.security.enums import AuthenticationMode, PrincipalType


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def cmd_issue_dev_token(args: argparse.Namespace) -> int:
    settings = get_settings()
    security = get_security_settings()
    if settings.app_env == "production":
        print("error: development tokens cannot be issued in production", file=sys.stderr)
        return 2
    if security.auth_mode != AuthenticationMode.LOCAL_DEVELOPMENT:
        print(
            "error: AUTH_MODE must be local_development to issue a development token",
            file=sys.stderr,
        )
        return 2
    if not security.local_auth_secret:
        print(
            "error: SIGNALFORGE_LOCAL_AUTH_SECRET is not set (no default is provided)",
            file=sys.stderr,
        )
        return 2
    if not security.local_auth_secret_is_strong():
        print("error: SIGNALFORGE_LOCAL_AUTH_SECRET is too weak", file=sys.stderr)
        return 2

    roles = [r.strip() for r in (args.roles or "").split(",") if r.strip()]
    memberships = [t.strip() for t in (args.tenants or "").split(",") if t.strip()]
    token = issue_symmetric_token(
        secret=security.local_auth_secret,
        issuer=security.local_dev_issuer,
        audience=security.local_dev_audience,
        subject=args.subject,
        external_tenant_id=args.tenant,
        roles=roles,
        tenant_memberships=memberships or [args.tenant],
        tenant_selector=args.tenant,
        principal_type=PrincipalType(args.principal_type),
        ttl_seconds=min(args.ttl_seconds, security.local_dev_token_ttl_seconds),
    )
    # Only the token is emitted; the signing secret is never printed.
    _print(
        {
            "token": token,
            "subject": args.subject,
            "tenant": args.tenant,
            "roles": roles,
            "ttl_seconds": min(args.ttl_seconds, security.local_dev_token_ttl_seconds),
            "note": "development token — not valid in production",
        }
    )
    return 0


def cmd_seed_novabank(args: argparse.Namespace) -> int:
    from app.db.unit_of_work import UnitOfWork
    from app.security.novabank_seed import seed_novabank_security

    init_engine()
    from sqlalchemy.orm import Session

    with Session(get_engine()) as session:
        uow = UnitOfWork(session)
        result = seed_novabank_security(uow, tenant_id=args.tenant)
        uow.commit()
    _print({"seeded": result})
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.security")
    sub = parser.add_subparsers(dest="command", required=True)

    tok = sub.add_parser("issue-dev-token", help="Issue a short-lived development JWT")
    tok.add_argument("--subject", required=True)
    tok.add_argument("--tenant", required=True, help="External/internal tenant id")
    tok.add_argument("--roles", default="", help="Comma-separated roles")
    tok.add_argument("--tenants", default="", help="Comma-separated tenant memberships")
    tok.add_argument(
        "--principal-type",
        default=PrincipalType.USER.value,
        choices=[p.value for p in PrincipalType],
    )
    tok.add_argument("--ttl-seconds", type=int, default=3600)
    tok.set_defaults(func=cmd_issue_dev_token)

    seed = sub.add_parser("seed-novabank", help="Seed synthetic NovaBank security fixtures")
    seed.add_argument("--tenant", default="novabank")
    seed.set_defaults(func=cmd_seed_novabank)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
