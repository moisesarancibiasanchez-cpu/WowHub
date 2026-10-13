"""Schemas comunes reutilizables."""
from typing import Generic, List, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: List[T]
    total: int
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


class Message(BaseModel):
    message: str
