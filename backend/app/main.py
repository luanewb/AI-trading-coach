from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, ai, alerts, analytics, dashboard, journal, mt5, news, rules
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.bootstrap import bootstrap_database
from app.db.session import engine
from app.services.news_scheduler import start_news_sync_scheduler, stop_news_sync_scheduler

configure_logging()
settings = get_settings()

app = FastAPI(title="AI Trading Coach API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(accounts.router)
app.include_router(mt5.router)
app.include_router(journal.router)
app.include_router(rules.router)
app.include_router(dashboard.router)
app.include_router(alerts.router)
app.include_router(ai.router)
app.include_router(analytics.router)
app.include_router(news.router)


@app.on_event("startup")
def startup() -> None:
    bootstrap_database(engine)
    start_news_sync_scheduler()


@app.on_event("shutdown")
async def shutdown() -> None:
    await stop_news_sync_scheduler()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
