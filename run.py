from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import httpx
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from worldpulse.ask import AskService
from worldpulse.collectors import create_collectors
from worldpulse.config import load_config
from worldpulse.db import Database
from worldpulse.processor import AIProcessor
from worldpulse.scheduler import Scheduler
from worldpulse.telegram_bot import TelegramBot
from worldpulse.web.app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def main() -> None:
    config_path = Path("config.yaml")
    if not config_path.exists():
        logger.error("config.yaml not found. Copy config.yaml.example to config.yaml and configure it.")
        sys.exit(1)

    config = load_config(config_path)
    asyncio.run(_run(config))


async def _run(config) -> None:
    db = Database(config.database.path)
    await db.connect()

    http_client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    collectors = create_collectors(
        {
            "hackernews": {
                "enabled": config.sources.hackernews.enabled,
                "top_n": config.sources.hackernews.top_n,
            },
            "github_trending": {
                "enabled": config.sources.github_trending.enabled,
            },
            "arxiv": {
                "enabled": config.sources.arxiv.enabled,
                "categories": config.sources.arxiv.categories,
                "max_results": config.sources.arxiv.max_results,
            },
        },
        http_client,
    )

    processor = AIProcessor(config.llm)
    ask_service = AskService(db, processor)
    telegram = TelegramBot(config.telegram, http_client)

    scheduler_core = Scheduler(db, collectors, processor, telegram, config.schedule)

    logger.info("Running initial collection...")
    await scheduler_core.collect_and_process()
    logger.info("Initial collection done")

    apscheduler = AsyncIOScheduler()
    apscheduler.add_job(
        scheduler_core.collect_and_process,
        "interval",
        minutes=config.schedule.collect_interval_minutes,
        id="collect_and_process",
    )

    push_parts = config.schedule.push_time.split(":")
    push_hour = int(push_parts[0])
    push_minute = int(push_parts[1]) if len(push_parts) > 1 else 0
    apscheduler.add_job(
        scheduler_core.generate_and_push,
        "cron",
        hour=push_hour,
        minute=push_minute,
        id="generate_and_push",
    )

    apscheduler.start()
    logger.info(
        "Scheduler started: collect every %d min, push at %s",
        config.schedule.collect_interval_minutes,
        config.schedule.push_time,
    )

    app = create_app(db, ask_service)
    server = uvicorn.Config(
        app,
        host=config.web.host,
        port=config.web.port,
        log_level="info",
    )

    loop = asyncio.get_event_loop()
    stop_event = asyncio.Event()

    def _shutdown():
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    srv = uvicorn.Server(server)

    try:
        await srv.serve()
    except Exception:
        logger.exception("Server error")
    finally:
        apscheduler.shutdown(wait=False)
        await http_client.aclose()
        await db.close()
        logger.info("Shutdown complete")


if __name__ == "__main__":
    main()
