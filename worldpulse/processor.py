from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from openai import AsyncOpenAI

from worldpulse.config import LLMConfig
from worldpulse.models import AskResult, Category, DailyInsight, Item

logger = logging.getLogger(__name__)

CATEGORIES = [c.display_name for c in Category]

PROCESS_PROMPT = """\
你是一个科技情报分类助手。对以下每条情报进行分类、总结和重要性评分。

可选分类：
{categories}

对每条情报返回 JSON 格式：
{{
    "items": [
        {{
            "index": 0,
            "category": "分类名",
            "summary": "中文总结（80-150字，说明这是什么、为什么重要、有什么影响）",
            "score_adjustment": 5
        }}
    ]
}}

summary 要求：
- 说明这个项目/新闻/论文是什么
- 为什么值得关注
- 可能带来的影响或意义
- 不要泛泛而谈，要具体

score_adjustment 范围 0-10，10 表示极其重要（如重大突破、影响行业的发布）。

情报列表：
{items_text}"""

INSIGHT_PROMPT = """\
你是科技情报分析专家。基于以下今日收集的情报数据，生成每日分析报告。

情报数据（按分类分组）：
{items_text}

返回 JSON 格式：
{{
    "daily_summary": "今日科技动态概要（3-5段，中文）",
    "trends": "值得关注的趋势（Markdown 列表，中文）"
}}"""

ASK_PROMPT = """\
你是科技情报分析助手。基于以下已采集的情报数据回答用户问题。
如果数据不足以回答，直接说明"目前没有足够的相关数据来回答这个问题"，不要编造。

情报数据：
{context}

用户问题：{question}"""

SOURCE_BASE_SCORES: dict[str, float] = {
    "hackernews": 40.0,
    "github": 30.0,
    "arxiv": 20.0,
}


def _compute_score(item: Item, adjustment: float) -> float:
    base = SOURCE_BASE_SCORES.get(item.source, 20.0)
    engagement = 0.0

    if item.source == "hackernews":
        try:
            raw = json.loads(item.raw_data)
            engagement += min(raw.get("score", 0) / 10, 30)
            engagement += min(raw.get("descendants", 0) / 5, 20)
        except (json.JSONDecodeError, TypeError):
            pass
    elif item.source == "github":
        try:
            raw = json.loads(item.raw_data)
            engagement += min(raw.get("today_stars", 0) / 10, 30)
        except (json.JSONDecodeError, TypeError):
            pass

    return base + engagement + adjustment


class AIProcessor:
    def __init__(self, config: LLMConfig) -> None:
        self._client = AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key,
        )
        self._model = config.model

    async def process_items(self, items: list[Item]) -> list[tuple[str, str, float]]:
        if not items:
            return []

        results: list[tuple[str, str, float]] = []
        batch_size = 10

        for i in range(0, len(items), batch_size):
            batch = items[i : i + batch_size]
            items_text = "\n".join(
                f"[{j}] 标题: {it.title}\n    内容: {it.content[:200]}"
                for j, it in enumerate(batch)
            )

            prompt = PROCESS_PROMPT.format(
                categories="\n".join(f"- {c}" for c in CATEGORIES),
                items_text=items_text,
            )

            try:
                response = await self._client.chat.completions.create(
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                    temperature=0.3,
                )
                content = response.choices[0].message.content or "{}"
                parsed = json.loads(content)
            except Exception:
                logger.exception("LLM processing failed for batch %d", i // batch_size)
                for _ in batch:
                    results.append(("dev_tools", "处理失败", 0.0))
                continue

            item_results = {r["index"]: r for r in parsed.get("items", [])}
            for j, item in enumerate(batch):
                r = item_results.get(j, {})
                category = r.get("category", "dev_tools")
                summary = r.get("summary", "")
                adjustment = float(r.get("score_adjustment", 5))
                score = _compute_score(item, adjustment)
                results.append((category, summary, score))

        return results

    async def generate_daily_insight(
        self, items: list[Item], date: str
    ) -> DailyInsight:
        items_by_cat: dict[str, list[Item]] = {}
        for item in items:
            cat = item.category or "other"
            items_by_cat.setdefault(cat, []).append(item)

        items_text = ""
        for cat, cat_items in items_by_cat.items():
            items_text += f"\n## {cat}\n"
            for it in cat_items[:10]:
                items_text += f"- [{it.source}] {it.title}: {it.summary}\n"

        prompt = INSIGHT_PROMPT.format(items_text=items_text)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.5,
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
        except Exception:
            logger.exception("Failed to generate daily insight")
            parsed = {}

        return DailyInsight(
            id=f"insight-{date}",
            date=date,
            daily_summary=parsed.get("daily_summary", ""),
            trends=parsed.get("trends", ""),
            item_count=len(items),
            created_at=datetime.now(timezone.utc),
        )

    async def answer_question(
        self, question: str, context_items: list[Item]
    ) -> AskResult:
        context_lines = []
        for item in context_items:
            context_lines.append(
                f"- [{item.category}] {item.title}\n  总结: {item.summary}\n  来源: {item.source} | {item.published_at}\n  链接: {item.url}"
            )
        context = "\n".join(context_lines)

        prompt = ASK_PROMPT.format(context=context, question=question)

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.5,
            )
            answer = response.choices[0].message.content or "无法生成回答"
        except Exception:
            logger.exception("Failed to answer question")
            answer = "抱歉，生成回答时出现错误"

        return AskResult(
            answer=answer,
            sources=context_items,
            search_query=question,
        )
