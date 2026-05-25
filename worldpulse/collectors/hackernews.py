from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from worldpulse.collectors.base import BaseCollector
from worldpulse.models import Item

logger = logging.getLogger(__name__)


class HackerNewsCollector(BaseCollector):
    def __init__(self, config: dict[str, Any], http_client: httpx.AsyncClient) -> None:
        super().__init__(config, http_client)
        self._sem = asyncio.Semaphore(10)
        self._api_url = config.get("api_url", "https://hacker-news.firebaseio.com/v0")

    async def collect(self) -> list[Item]:
        top_n = self._config.get("top_n", 30)
        try:
            resp = await self._http.get(f"{self._api_url}/topstories.json")
            resp.raise_for_status()
            story_ids: list[int] = resp.json()[:top_n]
        except Exception:
            logger.exception("Failed to fetch HN top stories")
            return []

        tasks = [self._fetch_story(sid) for sid in story_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        items: list[Item] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            if result is not None:
                items.append(result)

        logger.info("HN: collected %d items", len(items))
        return items

    async def _fetch_story(self, sid: int) -> Item | None:
        async with self._sem:
            try:
                resp = await self._http.get(f"{self._api_url}/item/{sid}.json")
                resp.raise_for_status()
                story = resp.json()
            except Exception:
                logger.warning("Failed to fetch HN story %s", sid)
                return None

        if story.get("type") != "story" or not story.get("title"):
            return None

        source_id = str(story["id"])
        item_id = hashlib.sha256(f"hackernews:{source_id}".encode()).hexdigest()[:16]
        raw_data = json.dumps(story, ensure_ascii=False)

        return Item(
            id=item_id,
            source="hackernews",
            source_id=source_id,
            title=story["title"],
            url=story.get("url", ""),
            content=story.get("text", ""),
            raw_data=raw_data,
            published_at=datetime.fromtimestamp(story.get("time", 0), tz=timezone.utc),
        )
