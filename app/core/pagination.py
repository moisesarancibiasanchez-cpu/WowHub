"""Paginación estándar y helper para respuestas paginadas."""
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """Wrapper genérico de página."""
    items: List[T]
    total: int = Field(..., description="Total de registros que cumplen el filtro")
    page: int = Field(..., ge=1)
    page_size: int = Field(..., ge=1, le=200)
    total_pages: int = Field(..., ge=0)

    @classmethod
    def build(cls, items: List[T], total: int, page: int, page_size: int) -> "Page[T]":
        total_pages = (total + page_size - 1) // page_size if page_size else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


def get_pagination_params(
    page: int = 1,
    page_size: int = 20,
) -> tuple[int, int]:
    """Normaliza parámetros de paginación."""
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    return page, page_size
