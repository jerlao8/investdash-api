from __future__ import annotations

from pydantic import BaseModel


class ReorderFavoritesRequest(BaseModel):
    slugs: list[str]
