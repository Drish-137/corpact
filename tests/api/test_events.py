import pytest
from httpx import AsyncClient, ASGITransport

from app.api.main import app
from app.core.database import AsyncSessionLocal, Base, engine
from app.models.corporate_action import CorporateAction


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture
async def sample_event():
    async with AsyncSessionLocal() as db:
        evt = CorporateAction(
            ticker="AAPL",
            company_name="Apple Inc.",
            event_type="dividend",
            amount=0.25,
            currency="USD",
            source="yfinance",
            source_event_id="AAPL_div_2024-02-09",
        )
        db.add(evt)
        await db.commit()
        await db.refresh(evt)
        return evt


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_list_events_empty(client):
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_events_with_data(client, sample_event):
    resp = await client.get("/api/events")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["ticker"] == "AAPL"


@pytest.mark.asyncio
async def test_filter_by_ticker(client, sample_event):
    resp = await client.get("/api/events?ticker=AAPL")
    assert resp.status_code == 200
    assert resp.json()["total"] == 1

    resp = await client.get("/api/events?ticker=MSFT")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


@pytest.mark.asyncio
async def test_get_event_not_found(client):
    resp = await client.get("/api/events/nonexistent-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_export_csv(client, sample_event):
    resp = await client.get("/api/events/export")
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "AAPL" in resp.text
