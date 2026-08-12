"""Registry eksperimental; tidak terhubung ke inference produksi."""

from ml.registry.metadata import ModelMetadata, persist_experimental_model

__all__ = ["ModelMetadata", "persist_experimental_model"]
