import logging

from app.core.config import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )


def log_startup(settings: Settings, *, dashboard_dir: str) -> None:
    logger = logging.getLogger("signalforge.startup")
    snapshot = settings.startup_snapshot()
    logger.info("SignalForge API starting")
    logger.info("app_env=%s log_level=%s", snapshot["app_env"], snapshot["log_level"])
    logger.info("database_configured=%s", snapshot["database_configured"])
    logger.info("cors_origins=%s", snapshot["cors_origins"])
    logger.info(
        "ai_enabled=%s azure_openai_configured=%s api_version=%s",
        snapshot["ai_enabled"],
        snapshot["azure_openai_configured"],
        snapshot["azure_openai_api_version"],
    )
    logger.info("dashboard_dir=%s", dashboard_dir)
