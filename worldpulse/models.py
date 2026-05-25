from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime


class Category(enum.StrEnum):
    AI_RESEARCH = "ai_research"
    OPEN_SOURCE = "open_source"
    LLM_MODELS = "llm_models"
    AI_AGENTS = "ai_agents"
    INFRASTRUCTURE = "infrastructure"
    CHIPS_HARDWARE = "chips_hardware"
    STARTUPS_FUNDING = "startups_funding"
    DEV_TOOLS = "dev_tools"
    AUTOMATION = "automation"

    @property
    def display_name(self) -> str:
        names = {
            "ai_research": "AI Research",
            "open_source": "Open Source",
            "llm_models": "LLM & Models",
            "ai_agents": "AI Agents",
            "infrastructure": "Infrastructure",
            "chips_hardware": "Chips & Hardware",
            "startups_funding": "Startups & Funding",
            "dev_tools": "Dev Tools",
            "automation": "Automation",
        }
        return names.get(self.value, self.value)


class Source(enum.StrEnum):
    HACKERNEWS = "hackernews"
    GITHUB = "github"
    ARXIV = "arxiv"


@dataclass
class Item:
    id: str
    source: str
    source_id: str
    title: str
    url: str
    content: str
    raw_data: str
    category: str = ""
    summary: str = ""
    score: float = 0.0
    published_at: datetime | None = None
    collected_at: datetime | None = None
    processed_at: datetime | None = None


@dataclass
class DailyInsight:
    id: str
    date: str
    daily_summary: str = ""
    trends: str = ""
    item_count: int = 0
    created_at: datetime | None = None


@dataclass
class AskResult:
    answer: str
    sources: list[Item] = field(default_factory=list)
    search_query: str = ""
