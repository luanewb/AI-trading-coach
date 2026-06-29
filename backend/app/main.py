from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import accounts, ai, alerts, journal, mt5, rules
from app.core.config import get_settings
from app.core.logging import configure_logging

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
app.include_router(alerts.router)
app.include_router(ai.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
