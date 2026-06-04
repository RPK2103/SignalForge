import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()


class Settings(BaseModel):
    azure_openai_endpoint: str = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    azure_openai_api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
    azure_openai_deployment: str = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

    def azure_openai_configured(self) -> bool:
        return bool(
            self.azure_openai_endpoint.strip()
            and self.azure_openai_api_key.strip()
            and self.azure_openai_deployment.strip()
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
