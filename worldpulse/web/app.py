from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from worldpulse.ask import AskService
from worldpulse.db import Database
from worldpulse.models import Category

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

CATEGORIES = ["all"] + [c.value for c in Category]
CATEGORY_NAMES = {"all": "All"}
for c in Category:
    CATEGORY_NAMES[c.value] = c.display_name


class AskRequest(BaseModel):
    question: str


def create_app(db: Database, ask_service: AskService) -> FastAPI:
    app = FastAPI(title="World Pulse")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        from jinja2 import Environment, FileSystemLoader

        env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=True)
        template = env.get_template("index.html")

        items = await db.get_items(limit=200)
        insights = await db.get_daily_insights(limit=7)

        html = template.render(
            items=items,
            insights=insights,
            categories=CATEGORIES,
            category_names=CATEGORY_NAMES,
            current_category="all",
        )
        return HTMLResponse(content=html)

    @app.get("/api/items")
    async def api_items(category: str | None = None, date: str | None = None, limit: int = 100):
        items = await db.get_items(category=category, date=date, limit=limit)
        return [
            {
                "id": i.id,
                "source": i.source,
                "title": i.title,
                "url": i.url,
                "category": i.category,
                "summary": i.summary,
                "score": i.score,
                "published_at": i.published_at.isoformat() if i.published_at else None,
            }
            for i in items
        ]

    @app.get("/api/insights")
    async def api_insights(limit: int = 10):
        insights = await db.get_daily_insights(limit=limit)
        return [
            {
                "id": ins.id,
                "date": ins.date,
                "daily_summary": ins.daily_summary,
                "trends": ins.trends,
                "item_count": ins.item_count,
            }
            for ins in insights
        ]

    @app.get("/api/insights/{date}")
    async def api_insight_by_date(date: str):
        insight = await db.get_daily_insight(date)
        if insight is None:
            return {"error": "not found"}
        return {
            "id": insight.id,
            "date": insight.date,
            "daily_summary": insight.daily_summary,
            "trends": insight.trends,
            "item_count": insight.item_count,
        }

    @app.post("/api/ask")
    async def api_ask(req: AskRequest):
        result = await ask_service.ask(req.question)
        return {
            "answer": result.answer,
            "sources": [
                {
                    "title": s.title,
                    "url": s.url,
                    "category": s.category,
                    "summary": s.summary,
                    "source": s.source,
                }
                for s in result.sources
            ],
        }

    return app
