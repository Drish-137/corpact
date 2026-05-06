from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


EventType = Literal[
    "dividend", "split", "merger", "spinoff", "rights_issue", "name_change", "other"
]


class CorporateActionBase(BaseModel):
    ticker: str
    company_name: str | None = None
    event_type: EventType
    ex_date: date | None = None
    record_date: date | None = None
    pay_date: date | None = None
    declared_date: date | None = None
    ratio: float | None = None
    amount: float | None = None
    currency: str | None = None
    description: str | None = None


class CorporateActionCreate(CorporateActionBase):
    source: str
    source_event_id: str | None = None
    raw_s3_key: str | None = None


class CorporateActionRead(CorporateActionBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: str
    created_at: datetime


class CorporateActionList(BaseModel):
    items: list[CorporateActionRead]
    total: int
    page: int
    page_size: int


class TickerSummary(BaseModel):
    ticker: str
    company_name: str | None
    event_count: int
    latest_event_date: date | None
