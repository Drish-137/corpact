import pytest
from contextlib import asynccontextmanager
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.main import app
from app.core.config import get_settings
from app.core.database import Base, get_db
from app.models.corporate_action import CorporateAction

settings = get_settings()


@asynccontextmanager
async def noop_lifespan(app):
    yield

app.router.lifespan_context = noop_lifespan


@pytest.fixture
async def engine():
    _engine = create_async_engine(
        settings.db_url,
        echo=False,
        pool_size=5,        # ← increased from 1
        max_overflow=5,     # ← allow overflow connections
    )
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(session_factory):
    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.fixture
async def sample_event(db_session):
    evt = CorporateAction(
        ticker="AAPL",
        company_name="Apple Inc.",
        event_type="dividend",
        amount=0.25,
        currency="USD",
        source="nasdaq_rss",
        source_event_id="AAPL_div_2024-02-09",
    )
    db_session.add(evt)
    await db_session.commit()
    await db_session.refresh(evt)
    return evt


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_list_events_empty(client):
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


async def test_list_events_with_data(client, sample_event):
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


async def test_filter_by_ticker(client, sample_event):
    resp = await client.get("/api/events?ticker=AAPL")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await client.get("/api/events?ticker=MSFT")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


async def test_get_event_not_found(client):
    resp = await client.get("/api/events/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


async def test_export_csv(client, sample_event):
    resp = await client.get("/api/events/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "AAPL" in resp.text