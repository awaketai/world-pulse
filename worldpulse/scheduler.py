from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from worldpulse.collectors.base import BaseCollector
from worldpulse.config import ScheduleConfig
from worldpulse.db import Database
from worldpulse.dedup import filter_duplicates
from worldpulse.processor import AIProcessor
from worldpulse.telegram_bot import TelegramBot

logger = logging.getLogger(__name__)


class Scheduler:
    def __init__(
        self,
        db: Database,
        collectors: list[BaseCollector],
        processor: AIProcessor,
        telegram: TelegramBot,
        config: ScheduleConfig,
    ) -> None:
        self._db = db
        self._collectors = collectors
        self._processor = processor
        self._telegram = telegram
        self._config = config

    async def collect_and_process(self) -> None:
        logger.info("Starting collection cycle")
        all_items = []

        tasks = [collector.collect() for collector in self._collectors]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, Exception):
                logger.error("Collector failed: %s", result)
                continue
            all_items.extend(result)

        if not all_items:
            logger.info("No items collected")
            return

        new_items = await filter_duplicates(self._db, all_items)
        if not new_items:
            logger.info("No new items after dedup")
            return

        inserted = await self._db.insert_items(new_items)
        logger.info("Inserted %d new items", inserted)

        await self._process_pending()

    async def _process_pending(self) -> None:
        unprocessed = await self._db.get_unprocessed_items()
        if not unprocessed:
            logger.info("No unprocessed items")
            return

        logger.info("Processing %d items", len(unprocessed))
        results = await self._processor.process_items(unprocessed)

        for item, (category, summary, score) in zip(unprocessed, results):
            await self._db.update_item_processed(item.id, category, summary, score)

        logger.info("Processed %d items", len(results))

    async def generate_and_push(self) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        yesterday = datetime.now(timezone.utc)
        from datetime import timedelta

        yesterday_str = (yesterday - timedelta(days=1)).strftime("%Y-%m-%d")

        items = await self._db.get_items_by_date_range(yesterday_str, today)
        if not items:
            logger.info("No items for insight generation")
            return

        logger.info("Generating daily insight for %s with %d items", yesterday_str, len(items))
        insight = await self._processor.generate_daily_insight(items, yesterday_str)
        await self._db.save_daily_insight(insight)

        top_items = sorted(items, key=lambda i: i.score, reverse=True)[:15]
        await self._telegram.send_daily_report(insight, top_items)
        logger.info("Daily insight generated and pushed for %s", yesterday_str)
