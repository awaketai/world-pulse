from __future__ import annotations

import logging

from worldpulse.db import Database
from worldpulse.models import AskResult
from worldpulse.processor import AIProcessor

logger = logging.getLogger(__name__)


class AskService:
    def __init__(self, db: Database, processor: AIProcessor) -> None:
        self._db = db
        self._processor = processor

    async def ask(self, question: str) -> AskResult:
        items = await self._db.search_items(question, days=7, limit=20)

        if not items:
            return AskResult(
                answer="目前没有找到与您问题相关的数据。请尝试换个关键词，或等待系统采集更多情报。",
                sources=[],
                search_query=question,
            )

        result = await self._processor.answer_question(question, items)
        return result
