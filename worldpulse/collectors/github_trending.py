from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from bs4 import BeautifulSoup

from worldpulse.collectors.base import BaseCollector
from worldpulse.models import Item

logger = logging.getLogger(__name__)

GITHUB_TRENDING_URL = "https://github.com/trending"


class GitHubTrendingCollector(BaseCollector):
    async def collect(self) -> list[Item]:
        try:
            resp = await self._http.get(
                GITHUB_TRENDING_URL,
                headers={"Accept": "text/html"},
                follow_redirects=True,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Failed to fetch GitHub Trending")
            return []

        soup = BeautifulSoup(resp.text, "lxml")
        articles = soup.select("article.Box-row")
        items: list[Item] = []

        for article in articles:
            name_el = article.select_one("h2 a")
            if not name_el:
                continue

            repo_name = name_el.get("href", "").strip("/").strip()
            if not repo_name:
                continue

            desc_el = article.select_one("p")
            description = desc_el.get_text(strip=True) if desc_el else ""

            lang_el = article.select_one("[itemprop='programmingLanguage']")
            language = lang_el.get_text(strip=True) if lang_el else ""

            stars_el = article.select_one("a.Link--muted.d-inline-block.mr-3")
            stars = 0
            if stars_el:
                stars_text = stars_el.get_text(strip=True).replace(",", "")
                stars = int(stars_text) if stars_text.isdigit() else 0

            today_el = article.select_one("span.d-inline-block.float-sm-right")
            today_stars = 0
            if today_el:
                match = re.search(r"(\d[\d,]*)", today_el.get_text())
                if match:
                    today_stars = int(match.group(1).replace(",", ""))

            source_id = repo_name.replace("/", "_")
            item_id = hashlib.sha256(f"github:{source_id}".encode()).hexdigest()[:16]
            raw_data = json.dumps({
                "repo": repo_name,
                "description": description,
                "language": language,
                "stars": stars,
                "today_stars": today_stars,
            }, ensure_ascii=False)

            content_parts = []
            if description:
                content_parts.append(description)
            if language:
                content_parts.append(f"Language: {language}")
            if today_stars:
                content_parts.append(f"+{today_stars} stars today")

            items.append(Item(
                id=item_id,
                source="github",
                source_id=source_id,
                title=repo_name,
                url=f"https://github.com/{repo_name}",
                content="\n".join(content_parts),
                raw_data=raw_data,
                published_at=datetime.now(timezone.utc),
            ))

        logger.info("GitHub Trending: collected %d items", len(items))
        return items
