"""
Normalizes CSV batches written by the NASDAQ RSS Lambda scraper.

SQS message shape:  { "s3_key": "corporate_actions/20260430_100258.csv", "count": 8 }
CSV columns:        event_id, ticker, event_type, ex_date, record_date,
                    pay_date, ratio, amount, currency, source, created_at
"""
import csv
import io
from datetime import datetime

import boto3
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.core.logging import logger
from app.models.corporate_action import CorporateAction


# ── Date parsing ──────────────────────────────────────────────────────────────

def _parse_date(val: str | None):
    """
     find_date() returns free-text scraped from the RSS
    description, e.g. "March 15, 2026" or "2026-03-15" or "03/15/2026".
    try the most common formats in order.
    """
    if not val or val.strip() in ("", "None", "N/A"):
        return None
    val = val.strip()
    for fmt in (
        "%Y-%m-%d",       # 2026-03-15
        "%B %d, %Y",      # March 15, 2026
        "%b %d, %Y",      # Mar 15, 2026
        "%m/%d/%Y",       # 03/15/2026
        "%d/%m/%Y",       # 15/03/2026
        "%Y%m%d",         # 20260315
    ):
        try:
            return datetime.strptime(val, fmt).date()
        except ValueError:
            continue
    logger.warning("could not parse date", value=val)
    return None


def _to_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "", "None", "N/A") else None
    except (ValueError, TypeError):
        return None


# ── Row normalizer ────────────────────────────────────────────────────────────

def _normalize_row(row: dict, s3_key: str) -> dict | None:
    """
    Maps one CSV row (from your Lambda scraper) to a CorporateAction record.
    Returns None if the row is too malformed to save.
    """
    ticker = (row.get("ticker") or "").strip().upper()
    if not ticker:
        return None

    # Your scraper already sets event_type to dividend/split/merger/other
    # We just normalise casing and strip whitespace.
    event_type = (row.get("event_type") or "other").strip().lower()
    if event_type not in ("dividend", "split", "merger", "spinoff", "rights_issue", "name_change"):
        event_type = "other"

    # event_id from your scraper is a UUID — perfect dedup key
    source_event_id = (row.get("event_id") or "").strip() or None

    return {
        "ticker":           ticker,
        "company_name":     None,          # not in RSS feed — can enrich later
        "event_type":       event_type,
        "ex_date":          _parse_date(row.get("ex_date")),
        "record_date":      _parse_date(row.get("record_date")),
        "pay_date":         _parse_date(row.get("pay_date")),
        "declared_date":    None,          # not in RSS feed
        "ratio":            _to_float(row.get("ratio")),
        "amount":           _to_float(row.get("amount")),
        "currency":         (row.get("currency") or "USD").strip() or "USD",
        "description":      None,
        "source":           "nasdaq_rss",
        "source_event_id":  source_event_id,
        "raw_s3_key":       s3_key,
    }


# ── S3 fetch ──────────────────────────────────────────────────────────────────

def _fetch_csv(s3_key: str) -> list[dict]:
    """Download the CSV from S3 and return rows as a list of dicts."""
    settings = get_settings()
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url

    s3 = boto3.client("s3", **kwargs)
    obj = s3.get_object(Bucket=settings.s3_raw_bucket, Key=s3_key)
    body = obj["Body"].read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(body)))


# ── Main entry point ──────────────────────────────────────────────────────────

async def normalize_batch_from_s3(db: AsyncSession, s3_key: str) -> int:
    """
    Called by the worker for each SQS message.
    Downloads the CSV, normalizes every row, upserts into RDS.
    Returns the number of rows successfully written.
    """
    rows = _fetch_csv(s3_key)
    written = 0
    skipped = 0

    for row in rows:
        data = _normalize_row(row, s3_key)

        if data is None:
            skipped += 1
            continue

        stmt = pg_insert(CorporateAction).values(**data)

        if data["source_event_id"]:
            # Your scraper generates a UUID per row — use it as the dedup key
            stmt = stmt.on_conflict_do_update(
                index_elements=["source_event_id"],
                set_={
                    k: v for k, v in data.items()
                    if k not in ("source_event_id", "created_at")
                },
            )

        await db.execute(stmt)
        written += 1

    logger.info(
        "batch normalized",
        s3_key=s3_key,
        written=written,
        skipped=skipped,
    )
    return written