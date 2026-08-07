"""Prompt 10 documentation contract tests.

Focused checks only: required files exist, internal relative links resolve,
required disclaimers present, and a small set of prohibited claim phrases are
absent. This is not a general prose linter.
"""

from __future__ import annotations

import re
from pathlib import Path

# backend/tests/docs/this_file.py -> parents[3] is the repository root
REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_FILES = [
    "architecture/phase-3-microsoft-poc-startup-pitch-readiness.md",
    "docs/poc/microsoft-enterprise-poc-blueprint.md",
    "docs/poc/poc-success-framework.md",
    "docs/poc/security-governance-questionnaire.md",
    "docs/poc/data-onboarding-plan.md",
    "docs/poc/novabank-executive-demo-runbook.md",
    "docs/pitch/executive-one-pager.md",
    "docs/pitch/buyer-personas.md",
    "docs/pitch/roi-hypothesis-model.md",
    "docs/pitch/competitive-positioning.md",
    "docs/pitch/startup-pitch-outline.md",
    "docs/pitch/objections-and-responses.md",
    "docs/portfolio/signalforge-case-study.md",
    "docs/evidence/production-readiness-evidence-index.md",
    "README.md",
]

# Phrases that must not appear as affirmative product claims in Prompt 10 docs.
PROHIBITED_PATTERNS = [
    re.compile(r"microsoft\s+has\s+endorsed", re.I),
    re.compile(r"microsoft\s+partner(ship|ed)", re.I),
    re.compile(r"microsoft\s+certif", re.I),
    re.compile(r"azure\s+marketplace\s+(available|listed|published)", re.I),
    re.compile(r"\bpaid\s+customers?\b", re.I),
    re.compile(r"\bproduction\s+customers?\b", re.I),
    re.compile(r"guaranteed\s+delivery\s+improvement", re.I),
    re.compile(r"industry[- ]leading", re.I),
    re.compile(r"\bthe\s+only\s+platform\b", re.I),
    re.compile(r"best\s+in\s+market", re.I),
    re.compile(r"causal\s+prediction", re.I),  # allowed only when negated; see test
]

# "causal prediction" is allowed when clearly negated nearby.
CAUSAL_ALLOW_NEGATION = re.compile(
    r"(not|never|no).{0,40}causal\s+prediction|causal\s+prediction.{0,40}(not|never)",
    re.I | re.S,
)

REQUIRED_DISCLAIMER_SNIPPETS = [
    "Microsoft has not endorsed",
    "fictional",
    "not a probability",
]


def _iter_prompt10_markdown() -> list[Path]:
    paths = [REPO_ROOT / rel for rel in REQUIRED_FILES]
    return paths


def _extract_relative_md_links(text: str) -> list[str]:
    # [label](relative/path.md) or [label](../x.md#anchor)
    return re.findall(r"\[[^\]]*\]\((?!https?:)(?!mailto:)([^)#\s]+)(?:#[^)]*)?\)", text)


def test_required_documentation_files_exist():
    missing = [rel for rel in REQUIRED_FILES if not (REPO_ROOT / rel).is_file()]
    assert missing == [], f"Missing Prompt 10 docs: {missing}"


def test_documentation_index_links_resolve():
    broken: list[str] = []
    for path in _iter_prompt10_markdown():
        text = path.read_text(encoding="utf-8")
        for link in _extract_relative_md_links(text):
            if link.startswith("#"):
                continue
            # Ignore in-page anchors already stripped; skip pure mailto handled above.
            target = (path.parent / link).resolve()
            if not target.exists():
                broken.append(f"{path.relative_to(REPO_ROOT)} -> {link}")
    assert broken == [], "Broken internal documentation links:\n" + "\n".join(broken)


def test_required_disclaimers_present_in_package():
    # At least the architecture index and README must carry core disclaimers;
    # NovaBank fictional label must appear in demo runbook.
    arch = (REPO_ROOT / "architecture/phase-3-microsoft-poc-startup-pitch-readiness.md").read_text(
        encoding="utf-8"
    )
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    runbook = (REPO_ROOT / "docs/poc/novabank-executive-demo-runbook.md").read_text(
        encoding="utf-8"
    )
    roi = (REPO_ROOT / "docs/pitch/roi-hypothesis-model.md").read_text(encoding="utf-8")
    personas = (REPO_ROOT / "docs/pitch/buyer-personas.md").read_text(encoding="utf-8")

    assert "Microsoft has not endorsed" in arch or "Microsoft has not endorsed" in readme
    assert re.search(r"fictional", runbook, re.I)
    assert "ILLUSTRATIVE ASSUMPTION" in roi
    assert re.search(r"not\s+(a\s+)?probabilit", runbook + arch + readme, re.I)
    # Allow markdown emphasis around "not" (e.g. **not** intended...)
    combined = readme + arch + personas
    assert re.search(
        r"not\**\s*intended\s+to\s+rank\s+individual\s+employees|"
        r"\*\*not\*\*\s+intended\s+to\s+rank\s+individual\s+employees",
        combined,
        re.I,
    ) or ("not intended to rank individual employees" in combined.replace("**", ""))


def test_prohibited_claim_phrases_absent_or_negated():
    violations: list[str] = []
    # Contexts that mean the phrase is forbidden/avoided rather than asserted.
    negation = re.compile(
        r"\b(not|no|never|without|avoid|avoided|prohibited|forbid|do\s+not|"
        r"don'?t|must\s+not|claims?\s+avoided|non-claims?|non[- ]goals?)\b",
        re.I,
    )
    for path in _iter_prompt10_markdown():
        text = path.read_text(encoding="utf-8")
        rel = str(path.relative_to(REPO_ROOT))
        for pattern in PROHIBITED_PATTERNS:
            for match in pattern.finditer(text):
                snippet = text[max(0, match.start() - 60) : match.end() + 60]
                if "causal" in pattern.pattern:
                    if CAUSAL_ALLOW_NEGATION.search(snippet):
                        continue
                window = text[max(0, match.start() - 120) : match.end() + 80]
                if negation.search(window):
                    continue
                violations.append(f"{rel}: {match.group(0)!r}")
    assert violations == [], "Prohibited claim phrases:\n" + "\n".join(violations)


def test_roi_metrics_labelled_illustrative():
    roi = (REPO_ROOT / "docs/pitch/roi-hypothesis-model.md").read_text(encoding="utf-8")
    assert "ILLUSTRATIVE ASSUMPTION — NOT A MEASURED SIGNALFORGE RESULT" in roi
    assert "hypothesis" in roi.lower()


def test_no_committed_token_like_strings_in_prompt10_docs():
    # Reject long JWT-shaped strings accidentally pasted into docs.
    jwt_like = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")
    offenders: list[str] = []
    for path in _iter_prompt10_markdown():
        text = path.read_text(encoding="utf-8")
        if jwt_like.search(text):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"Token-like strings in docs: {offenders}"
