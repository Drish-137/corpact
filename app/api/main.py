from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import events, tickers
from app.core.config import get_settings
from app.core.database import engine, Base
from app.core.logging import setup_logging, logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    if settings.app_env != "test":          # ← add this check
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    logger.info("corpact API started", env=settings.app_env)
    yield
    await engine.dispose()
    logger.info("corpact API stopped")


app = FastAPI(
    title="corpact",
    description="Corporate actions public financial data API",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if not settings.is_production else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if not settings.is_production else ["https://yourdomain.com"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/api/events", tags=["events"])
app.include_router(tickers.router, prefix="/api/tickers", tags=["tickers"])


@app.get("/health")
async def health():
    return {"status": "ok"}
