"""Canonical capability definitions used by the intelligence domain."""

from app.domain.enums import CapabilityCategory
from app.domain.models import CapabilityDefinition

STANDARD_CAPABILITIES: dict[str, CapabilityDefinition] = {
    "python": CapabilityDefinition(
        id="python",
        name="Python",
        category=CapabilityCategory.BACKEND,
        keywords=["python"],
    ),
    "java": CapabilityDefinition(
        id="java",
        name="Java",
        category=CapabilityCategory.BACKEND,
        keywords=["java", "spring boot"],
    ),
    "azure": CapabilityDefinition(
        id="azure",
        name="Azure",
        category=CapabilityCategory.CLOUD,
        keywords=["azure"],
    ),
    "generative_ai": CapabilityDefinition(
        id="generative_ai",
        name="Generative AI",
        category=CapabilityCategory.AI,
        keywords=["generative ai", "gen ai", "llm"],
    ),
    "react": CapabilityDefinition(
        id="react",
        name="React",
        category=CapabilityCategory.BACKEND,
        keywords=["react"],
    ),
    "kubernetes": CapabilityDefinition(
        id="kubernetes",
        name="Kubernetes",
        category=CapabilityCategory.DEVOPS,
        keywords=["kubernetes", "k8s"],
    ),
    "terraform": CapabilityDefinition(
        id="terraform",
        name="Terraform",
        category=CapabilityCategory.DEVOPS,
        keywords=["terraform"],
    ),
    "sql": CapabilityDefinition(
        id="sql",
        name="SQL",
        category=CapabilityCategory.DATA,
        keywords=["sql", "database"],
    ),
    "security": CapabilityDefinition(
        id="security",
        name="Security",
        category=CapabilityCategory.SECURITY,
        keywords=["security", "oauth", "identity"],
    ),
    "architecture": CapabilityDefinition(
        id="architecture",
        name="Architecture",
        category=CapabilityCategory.ARCHITECTURE,
        keywords=["architecture", "system design"],
    ),
    "delivery": CapabilityDefinition(
        id="delivery",
        name="Delivery Execution",
        category=CapabilityCategory.DELIVERY_EXECUTION,
        keywords=["agile", "delivery", "execution"],
    ),
}

_LEGACY_SKILL_ALIASES: dict[str, str] = {
    "azure": "azure",
    "python": "python",
    "generative ai": "generative_ai",
    "java": "java",
    "spring boot": "java",
    "react": "react",
    "ui": "react",
    "figma": "react",
    "kubernetes": "kubernetes",
    "terraform": "terraform",
    "sql": "sql",
    "security": "security",
    "architecture": "architecture",
}


def get_capability(capability_id: str) -> CapabilityDefinition | None:
    return STANDARD_CAPABILITIES.get(capability_id)


def resolve_capability_id(label: str) -> str | None:
    normalized = label.strip().lower()
    if normalized in _LEGACY_SKILL_ALIASES:
        return _LEGACY_SKILL_ALIASES[normalized]
    for cap_id, definition in STANDARD_CAPABILITIES.items():
        if definition.name.lower() == normalized:
            return cap_id
        if normalized in (kw.lower() for kw in definition.keywords):
            return cap_id
    slug = normalized.replace(" ", "_")
    return slug if slug in STANDARD_CAPABILITIES else None


def all_capabilities() -> list[CapabilityDefinition]:
    return list(STANDARD_CAPABILITIES.values())
