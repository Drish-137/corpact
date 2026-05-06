from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.corporate_action import CorporateAction
from app.models.schemas import TickerSummary

router = APIRouter()


@router.get("", response_model=list[TickerSummary])
async def list_tickers(db: AsyncSession = Depends(get_db)):
    q = (
        select(
            CorporateAction.ticker,
            CorporateAction.company_name,
            func.count(CorporateAction.id).label("event_count"),
            func.max(CorporateAction.ex_date).label("latest_event_date"),
        )
        .group_by(CorporateAction.ticker, CorporateAction.company_name)
        .order_by(CorporateAction.ticker)
    )
    rows = (await db.execute(q)).all()
    return [
        TickerSummary(
            ticker=r.ticker,
            company_name=r.company_name,
            event_count=r.event_count,
            latest_event_date=r.latest_event_date,
        )
        for r in rows
    ]
