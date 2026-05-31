"""Small non-durable helpers for the Simple CRM app."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PageResult:
    """A small page of domain objects plus enough metadata for UI controls."""

    items: list
    total: int
    page: int
    page_size: int

    @property
    def page_count(self) -> int:
        if self.total == 0:
            return 1
        return ((self.total - 1) // self.page_size) + 1

    @property
    def has_previous(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.page_count
