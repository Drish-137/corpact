import csv
import io
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.corporate_action import CorporateAction
from app.models.schemas import CorporateActionList, CorporateActionRead

router = APIRouter()


@router.get("", response_model=CorporateActionList)
async def list_events(
    ticker: str | None = Query(None, description="Filter by ticker symbol"),
    event_type: str | None = Query(None, description="Filter by event type"),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    q = select(CorporateAction)
    if ticker:
        q = q.where(CorporateAction.ticker == ticker.upper())
    if event_type:
        q = q.where(CorporateAction.event_type == event_type)
    if from_date:
        q = q.where(CorporateAction.ex_date >= from_date)
    if to_date:
        q = q.where(CorporateAction.ex_date <= to_date)

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    q = q.order_by(CorporateAction.ex_date.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    return CorporateActionList(
        items=[CorporateActionRead.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/upcoming", response_model=list[CorporateActionRead])
async def upcoming_events(
    days: int = Query(30, ge=1, le=180),
    db: AsyncSession = Depends(get_db),
):
    from datetime import timedelta
    today = date.today()
    cutoff = today + timedelta(days=days)
    q = (
        select(CorporateAction)
        .where(CorporateAction.ex_date >= today)
        .where(CorporateAction.ex_date <= cutoff)
        .order_by(CorporateAction.ex_date)
    )
    rows = (await db.execute(q)).scalars().all()
    return [CorporateActionRead.model_validate(r) for r in rows]


@router.get("/export")
async def export_csv(
    ticker: str | None = Query(None),
    event_type: str | None = Query(None),
    from_date: date | None = Query(None),
    to_date: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(CorporateAction)
    if ticker:
        q = q.where(CorporateAction.ticker == ticker.upper())
    if event_type:
        q = q.where(CorporateAction.event_type == event_type)
    if from_date:
        q = q.where(CorporateAction.ex_date >= from_date)
    if to_date:
        q = q.where(CorporateAction.ex_date <= to_date)
    q = q.order_by(CorporateAction.ex_date.desc())
    rows = (await db.execute(q)).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "ticker", "company_name", "event_type",
        "ex_date", "record_date", "pay_date",
        "amount", "currency", "ratio", "source",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.ticker, r.company_name, r.event_type,
            r.ex_date, r.record_date, r.pay_date,
            r.amount, r.currency, r.ratio, r.source,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=corporate_actions.csv"},
    )


@router.get("/{event_id}", response_model=CorporateActionRead)
async def get_event(event_id: str, db: AsyncSession = Depends(get_db)):
    from fastapi import HTTPException
    row = await db.get(CorporateAction, event_id)
    if not row:
        raise HTTPException(status_code=404, detail="Event not found")
    return CorporateActionRead.model_validate(row)
