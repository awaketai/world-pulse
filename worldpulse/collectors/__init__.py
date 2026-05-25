from __future__ import annotations

from typing import Any

import httpx

from worldpulse.collectors.base import BaseCollector
from worldpulse.collectors.github_trending import GitHubTrendingCollector
from worldpulse.collectors.hackernews import HackerNewsCollector
from worldpulse.collectors.arxiv import ArxivCollector

__all__ = [
    "BaseCollector",
    "HackerNewsCollector",
    "GitHubTrendingCollector",
    "ArxivCollector",
    "create_collectors",
]


def create_collectors(
    sources_config: dict[str, Any],
    http_client: httpx.AsyncClient,
) -> list[BaseCollector]:
    collectors: list[BaseCollector] = []

    hn = sources_config.get("hackernews", {})
    if hn.get("enabled", True):
        collectors.append(HackerNewsCollector(hn, http_client))

    gh = sources_config.get("github_trending", {})
    if gh.get("enabled", True):
        collectors.append(GitHubTrendingCollector(gh, http_client))

    arxiv = sources_config.get("arxiv", {})
    if arxiv.get("enabled", True):
        collectors.append(ArxivCollector(arxiv, http_client))

    return collectors
