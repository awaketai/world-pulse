from __future__ import annotations

import logging

import httpx

from worldpulse.config import TelegramConfig
from worldpulse.models import DailyInsight, Item

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


class TelegramBot:
    def __init__(
        self, config: TelegramConfig, http_client: httpx.AsyncClient
    ) -> None:
        self._token = config.bot_token
        self._chat_id = config.chat_id
        self._http = http_client

    async def send_daily_report(
        self, insight: DailyInsight, top_items: list[Item]
    ) -> None:
        parts: list[str] = []
        parts.append(f"\U0001f4e1 World Pulse 科技日报 — {insight.date}")
        parts.append("")
        parts.append("━━ 今日概要 ━━")
        parts.append(insight.daily_summary)
        parts.append("")
        parts.append("━━ 趋势洞察 ━━")
        parts.append(insight.trends)
        parts.append("")
        parts.append("━━ 重点动态 ━━")

        for item in top_items[:15]:
            source_tag = {"hackernews": "HN", "github": "GH", "arxiv": "arXiv"}.get(
                item.source, item.source
            )
            parts.append(f"\U0001f4c9 [{item.category}] {item.title}")
            parts.append(f"   → {item.summary}")
            if item.url:
                parts.append(f"   \U0001f517 {item.url}")
            parts.append("")

        await self.send_message("\n".join(parts))

    async def send_message(self, text: str) -> None:
        if not self._token or not self._chat_id:
            logger.warning("Telegram not configured, skipping message")
            return

        url = f"{TELEGRAM_API}/bot{self._token}/sendMessage"

        max_len = 4096
        if len(text) <= max_len:
            await self._do_send(url, text)
            return

        for i in range(0, len(text), max_len):
            await self._do_send(url, text[i : i + max_len])

    async def _do_send(self, url: str, text: str) -> None:
        try:
            resp = await self._http.post(
                url,
                json={
                    "chat_id": self._chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                },
            )
            resp.raise_for_status()
            logger.info("Telegram message sent")
        except Exception:
            logger.exception("Failed to send Telegram message")
