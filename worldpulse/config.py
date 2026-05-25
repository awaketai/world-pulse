from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class LLMConfig:
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    model: str = "gpt-4o-mini"


@dataclass
class TelegramConfig:
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class HackerNewsConfig:
    enabled: bool = True
    top_n: int = 30


@dataclass
class GitHubTrendingConfig:
    enabled: bool = True


@dataclass
class ArxivConfig:
    enabled: bool = True
    categories: list[str] = field(default_factory=lambda: ["cs.AI", "cs.CL", "cs.LG"])
    max_results: int = 20


@dataclass
class SourcesConfig:
    hackernews: HackerNewsConfig = field(default_factory=HackerNewsConfig)
    github_trending: GitHubTrendingConfig = field(default_factory=GitHubTrendingConfig)
    arxiv: ArxivConfig = field(default_factory=ArxivConfig)


@dataclass
class ScheduleConfig:
    collect_interval_minutes: int = 120
    push_time: str = "09:00"


@dataclass
class DatabaseConfig:
    path: str = "data/worldpulse.db"


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8080


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    sources: SourcesConfig = field(default_factory=SourcesConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    web: WebConfig = field(default_factory=WebConfig)


def load_config(path: str | Path) -> AppConfig:
    p = Path(path)
    if not p.exists():
        return AppConfig()

    with p.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    llm_raw = raw.get("llm", {})
    telegram_raw = raw.get("telegram", {})
    sources_raw = raw.get("sources", {})
    schedule_raw = raw.get("schedule", {})
    db_raw = raw.get("database", {})
    web_raw = raw.get("web", {})

    hn_raw = sources_raw.get("hackernews", {})
    gh_raw = sources_raw.get("github_trending", {})
    arxiv_raw = sources_raw.get("arxiv", {})

    return AppConfig(
        llm=LLMConfig(
            base_url=llm_raw.get("base_url", LLMConfig.base_url),
            api_key=llm_raw.get("api_key", ""),
            model=llm_raw.get("model", LLMConfig.model),
        ),
        telegram=TelegramConfig(
            bot_token=telegram_raw.get("bot_token", ""),
            chat_id=telegram_raw.get("chat_id", ""),
        ),
        sources=SourcesConfig(
            hackernews=HackerNewsConfig(
                enabled=hn_raw.get("enabled", True),
                top_n=hn_raw.get("top_n", 30),
            ),
            github_trending=GitHubTrendingConfig(
                enabled=gh_raw.get("enabled", True),
            ),
            arxiv=ArxivConfig(
                enabled=arxiv_raw.get("enabled", True),
                categories=arxiv_raw.get("categories", ["cs.AI", "cs.CL", "cs.LG"]),
                max_results=arxiv_raw.get("max_results", 20),
            ),
        ),
        schedule=ScheduleConfig(
            collect_interval_minutes=schedule_raw.get("collect_interval_minutes", 120),
            push_time=schedule_raw.get("push_time", "09:00"),
        ),
        database=DatabaseConfig(path=db_raw.get("path", "data/worldpulse.db")),
        web=WebConfig(
            host=web_raw.get("host", "0.0.0.0"),
            port=web_raw.get("port", 8080),
        ),
    )
