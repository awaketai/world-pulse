from __future__ import annotations

import logging

from worldpulse.db import Database
from worldpulse.models import Item

logger = logging.getLogger(__name__)


async def filter_duplicates(db: Database, items: list[Item]) -> list[Item]:
    if not items:
        return []

    existing_ids: set[str] = set()
    seen_source_ids: set[str] = set()
    for item in items:
        seen_source_ids.add(f"{item.source}:{item.source_id}")

    if seen_source_ids:
        existing = await db.get_items_by_ids([item.id for item in items])
        existing_ids = {i.id for i in existing}

    new_items = [item for item in items if item.id not in existing_ids]
    dup_count = len(items) - len(new_items)
    if dup_count > 0:
        logger.info("Dedup: removed %d duplicates", dup_count)

    return new_items
