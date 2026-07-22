"""Repository factory for catalog data access."""

from app.repositories.catalog_repository import CatalogRepository
from app.repositories.mock_catalog_repository import MockCatalogRepository


def get_catalog_repository() -> CatalogRepository:
    return MockCatalogRepository()
