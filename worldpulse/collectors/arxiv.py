from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from worldpulse.collectors.base import BaseCollector
from worldpulse.models import Item

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
ATOM_NS = "{http://www.w3.org/2005/Atom}"


class ArxivCollector(BaseCollector):
    async def collect(self) -> list[Item]:
        categories = self._config.get("categories", ["cs.AI", "cs.CL", "cs.LG"])
        max_results = self._config.get("max_results", 20)

        cat_query = " OR ".join(f"cat:{c}" for c in categories)
        params = {
            "search_query": cat_query,
            "start": 0,
            "max_results": max_results,
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }

        try:
            resp = await self._http.get(ARXIV_API, params=params)
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to fetch arXiv")
            return []

        items: list[Item] = []
        try:
            root = ElementTree.fromstring(resp.text)
        except Exception:
            logger.exception("Failed to parse arXiv XML")
            return []

        for entry in root.findall(f"{ATOM_NS}entry"):
            title_el = entry.find(f"{ATOM_NS}title")
            summary_el = entry.find(f"{ATOM_NS}summary")
            published_el = entry.find(f"{ATOM_NS}published")
            id_el = entry.find(f"{ATOM_NS}id")

            if title_el is None or id_el is None:
                continue

            title = title_el.text.strip().replace("\n", " ") if title_el.text else ""
            abstract = summary_el.text.strip().replace("\n", " ") if summary_el and summary_el.text else ""
            arxiv_id = id_el.text.strip().rstrip("/").split("/")[-1]
            published = published_el.text.strip() if published_el is not None else None

            source_id = arxiv_id
            item_id = hashlib.sha256(f"arxiv:{source_id}".encode()).hexdigest()[:16]
            raw_data = json.dumps({
                "arxiv_id": arxiv_id,
                "title": title,
                "abstract": abstract[:500],
                "published": published,
            }, ensure_ascii=False)

            pub_dt = None
            if published:
                try:
                    pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
                except ValueError:
                    pass

            items.append(Item(
                id=item_id,
                source="arxiv",
                source_id=source_id,
                title=title,
                url=f"https://arxiv.org/abs/{arxiv_id}",
                content=abstract[:500],
                raw_data=raw_data,
                published_at=pub_dt,
            ))

        logger.info("arXiv: collected %d items", len(items))
        return items
