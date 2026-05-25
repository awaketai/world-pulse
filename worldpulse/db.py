from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite

from worldpulse.models import DailyInsight, Item

logger = logging.getLogger(__name__)

_CREATE_ITEMS = """
CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    title TEXT NOT NULL,
    url TEXT,
    content TEXT,
    raw_data TEXT,
    category TEXT,
    summary TEXT,
    score REAL DEFAULT 0,
    published_at TIMESTAMP,
    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP
)
"""

_CREATE_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(
    title, content, summary,
    content='items',
    content_rowid='rowid',
    tokenize='unicode61'
)
"""

_CREATE_FTS_INSERT_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
    INSERT INTO items_fts(rowid, title, content, summary)
    VALUES (new.rowid, new.title, new.content, new.summary);
END
"""

_CREATE_FTS_UPDATE_TRIGGER = """
CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE ON items BEGIN
    INSERT INTO items_fts(items_fts, rowid, title, content, summary)
    VALUES ('delete', old.rowid, old.title, old.content, old.summary);
    INSERT INTO items_fts(rowid, title, content, summary)
    VALUES (new.rowid, new.title, new.content, new.summary);
END
"""

_CREATE_INSIGHTS = """
CREATE TABLE IF NOT EXISTS daily_insights (
    id TEXT PRIMARY KEY,
    date TEXT NOT NULL UNIQUE,
    daily_summary TEXT,
    trends TEXT,
    item_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _row_to_item(row: aiosqlite.Row) -> Item:
    return Item(
        id=row["id"],
        source=row["source"],
        source_id=row["source_id"],
        title=row["title"],
        url=row["url"] or "",
        content=row["content"] or "",
        raw_data=row["raw_data"] or "",
        category=row["category"] or "",
        summary=row["summary"] or "",
        score=row["score"] or 0.0,
        published_at=_parse_ts(row["published_at"]),
        collected_at=_parse_ts(row["collected_at"]),
        processed_at=_parse_ts(row["processed_at"]),
    )


def _row_to_insight(row: aiosqlite.Row) -> DailyInsight:
    return DailyInsight(
        id=row["id"],
        date=row["date"],
        daily_summary=row["daily_summary"] or "",
        trends=row["trends"] or "",
        item_count=row["item_count"] or 0,
        created_at=_parse_ts(row["created_at"]),
    )


def _parse_ts(val: str | None) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    return datetime.fromisoformat(val)


class Database:
    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self._path))
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._db.execute(_CREATE_ITEMS)
        await self._db.execute(_CREATE_FTS)
        await self._db.execute(_CREATE_FTS_INSERT_TRIGGER)
        await self._db.execute(_CREATE_FTS_UPDATE_TRIGGER)
        await self._db.execute(_CREATE_INSIGHTS)
        await self._db.commit()
        logger.info("Database initialized: %s", self._path)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def insert_items(self, items: list[Item]) -> int:
        if not items:
            return 0
        assert self._db is not None
        count = 0
        for item in items:
            try:
                await self._db.execute(
                    """INSERT OR IGNORE INTO items
                    (id, source, source_id, title, url, content, raw_data, published_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item.id,
                        item.source,
                        item.source_id,
                        item.title,
                        item.url,
                        item.content,
                        item.raw_data,
                        item.published_at.isoformat() if item.published_at else None,
                    ),
                )
                count += 1
            except Exception:
                logger.exception("Failed to insert item: %s", item.id)
        await self._db.commit()
        return count

    async def get_unprocessed_items(self) -> list[Item]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM items WHERE processed_at IS NULL ORDER BY collected_at DESC"
        )
        rows = await cursor.fetchall()
        return [_row_to_item(r) for r in rows]

    async def update_item_processed(
        self, item_id: str, category: str, summary: str, score: float
    ) -> None:
        assert self._db is not None
        await self._db.execute(
            """UPDATE items SET category=?, summary=?, score=?, processed_at=?
            WHERE id=?""",
            (category, summary, score, datetime.now(timezone.utc).isoformat(), item_id),
        )
        await self._db.commit()

    async def get_items(
        self,
        category: str | None = None,
        date: str | None = None,
        limit: int = 100,
    ) -> list[Item]:
        assert self._db is not None
        conditions = ["processed_at IS NOT NULL"]
        params: list[object] = []
        if category:
            conditions.append("category = ?")
            params.append(category)
        if date:
            conditions.append("DATE(collected_at) = ?")
            params.append(date)
        where = " AND ".join(conditions)
        cursor = await self._db.execute(
            f"SELECT * FROM items WHERE {where} ORDER BY score DESC LIMIT ?",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_item(r) for r in rows]

    async def get_items_by_ids(self, ids: list[str]) -> list[Item]:
        if not ids:
            return []
        assert self._db is not None
        placeholders = ",".join("?" * len(ids))
        cursor = await self._db.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})", ids
        )
        rows = await cursor.fetchall()
        return [_row_to_item(r) for r in rows]

    async def search_items(
        self, query: str, days: int = 7, limit: int = 20
    ) -> list[Item]:
        assert self._db is not None
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Try FTS5 first
        results = await self._search_fts(query, since, limit)
        if results:
            return results

        # Fallback: LIKE search for Chinese/multilingual support
        return await self._search_like(query, since, limit)

    async def _search_fts(
        self, query: str, since: str, limit: int
    ) -> list[Item]:
        assert self._db is not None
        try:
            fts_query = " OR ".join(f'"{w}"' for w in query.split() if len(w) > 1)
            if not fts_query:
                return []
            cursor = await self._db.execute(
                """SELECT i.* FROM items i
                JOIN items_fts f ON i.rowid = f.rowid
                WHERE items_fts MATCH ?
                AND i.processed_at IS NOT NULL
                AND i.collected_at >= ?
                ORDER BY rank
                LIMIT ?""",
                (fts_query, since, limit),
            )
            rows = await cursor.fetchall()
            return [_row_to_item(r) for r in rows]
        except Exception:
            return []

    async def _search_like(
        self, query: str, since: str, limit: int
    ) -> list[Item]:
        assert self._db is not None
        words = [w for w in query.split() if len(w) > 1]
        if not words:
            words = [query]
        conditions = []
        params: list[object] = [since]
        for word in words:
            conditions.append("(title LIKE ? OR content LIKE ? OR summary LIKE ?)")
            params.extend([f"%{word}%", f"%{word}%", f"%{word}%"])
        where = " OR ".join(conditions)
        cursor = await self._db.execute(
            f"""SELECT * FROM items
            WHERE processed_at IS NOT NULL
            AND collected_at >= ?
            AND ({where})
            ORDER BY score DESC
            LIMIT ?""",
            (*params, limit),
        )
        rows = await cursor.fetchall()
        return [_row_to_item(r) for r in rows]

    async def get_items_by_date_range(
        self, start: str, end: str
    ) -> list[Item]:
        assert self._db is not None
        cursor = await self._db.execute(
            """SELECT * FROM items
            WHERE processed_at IS NOT NULL
            AND DATE(collected_at) >= ? AND DATE(collected_at) <= ?
            ORDER BY score DESC""",
            (start, end),
        )
        rows = await cursor.fetchall()
        return [_row_to_item(r) for r in rows]

    async def save_daily_insight(self, insight: DailyInsight) -> None:
        assert self._db is not None
        await self._db.execute(
            """INSERT OR REPLACE INTO daily_insights
            (id, date, daily_summary, trends, item_count)
            VALUES (?, ?, ?, ?, ?)""",
            (insight.id, insight.date, insight.daily_summary, insight.trends, insight.item_count),
        )
        await self._db.commit()

    async def get_daily_insights(self, limit: int = 10) -> list[DailyInsight]:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM daily_insights ORDER BY date DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [_row_to_insight(r) for r in rows]

    async def get_daily_insight(self, date: str) -> DailyInsight | None:
        assert self._db is not None
        cursor = await self._db.execute(
            "SELECT * FROM daily_insights WHERE date = ?", (date,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_insight(row)
