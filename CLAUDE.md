# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

World Pulse is an AI-powered global tech intelligence system. It automatically collects, analyzes, and summarizes tech news from multiple sources, then delivers insights via Telegram and a web interface.

## Design Principles

Follow SOLID, KISS, DRY, and YAGNI. Don't over-engineer — this is a data pipeline, not a framework.

## Python Best Practices

- **Type hints**: All function signatures must include type annotations. Use `from __future__ import annotations` for forward references.
- **Pydantic/dataclasses**: Use `dataclasses` for internal data models (`models.py`), Pydantic for config and API schemas.
- **Async everywhere**: Use `async/await` throughout — collectors use `httpx.AsyncClient`, DB operations use `aiosqlite`, web is async FastAPI. No blocking I/O in the event loop.
- **Structured logging**: Use `logging` module with `structlog` or standard `logging.getLogger(__name__)`. No `print()` statements.
- **Error handling**: Catch specific exceptions at boundaries (network calls, LLM API, DB). Never use bare `except:`. Let unexpected errors propagate.
- **Path handling**: Use `pathlib.Path` for all file paths, never string concatenation.
- **Constants and enums**: Use `enum.StrEnum` or `enum.Enum` for fixed sets of values (categories, source names).
- **Dependency injection**: Pass dependencies (db connection, http client, config) as function parameters or constructor args, not module-level globals.
- **Linting**: Use `ruff` for linting and formatting. Run `ruff check .` and `ruff format .` before committing.

## Architecture

```
Collectors (HN/GitHub/arXiv) → Dedup → SQLite → AI Processor (LLM) → Telegram Bot + FastAPI Web
```

- **Collectors** (`worldpulse/collectors/`): Each source implements `BaseCollector`. All sources share one collection interval (configurable in `config.yaml`).
- **AI Processor** (`worldpulse/processor.py`): Uses OpenAI SDK with configurable `base_url` to support any OpenAI-compatible LLM. Batches items (10 per call) for classification + summarization.
- **Scheduler** (`worldpulse/scheduler.py`): APScheduler runs collection at a fixed interval and daily insight generation at a configured time. On startup, collection runs immediately before scheduling begins.
- **Web** (`worldpulse/web/`): FastAPI + Jinja2 server-rendered. Items displayed by category tabs, sorted by score. API routes under `/api/`.
- **Database**: SQLite via `worldpulse/db.py`. Two tables: `items` (collected + AI-processed data) and `daily_insights` (daily AI-generated summaries).

## Commands

```bash
# Install dependencies
uv pip install -e .

# Run (starts scheduler + web server)
python main.py

# Docker
docker compose up
```

## Configuration

Copy `config.yaml.example` to `config.yaml` (gitignored). All runtime config lives there: LLM endpoint/key, Telegram credentials, source toggles, schedule intervals.

## Data Sources

Hacker News (Firebase API), GitHub Trending (HTML scraping), arXiv (Atom API). Each collector is self-contained and returns a standardized item format.

## Category System

Nine predefined categories that the LLM selects from (AI Research, Open Source, LLM & Models, AI Agents, Infrastructure, Chips & Hardware, Startups & Funding, Dev Tools, Automation). Not user-configurable.
