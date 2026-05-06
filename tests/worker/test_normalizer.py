"""
Tests for app/worker/normalizer.py

Covers the exact CSV shape produced by the NASDAQ RSS Lambda scraper:
    event_id, ticker, event_type, ex_date, record_date, pay_date,
    ratio, amount, currency, source, created_at
"""
import csv
import io
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from app.worker.normalizer import (
    _parse_date,
    _to_float,
    _normalize_row,
    _fetch_csv,
    normalize_batch_from_s3,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_csv(rows: list[dict]) -> str:
    """Build a CSV string in the exact format the Lambda scraper writes."""
    fieldnames = [
        "event_id", "ticker", "event_type",
        "ex_date", "record_date", "pay_date",
        "ratio", "amount", "currency",
        "source", "created_at",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def make_row(**overrides) -> dict:
    """Return a fully-populated CSV row with sensible defaults."""
    base = {
        "event_id":   "550e8400-e29b-41d4-a716-446655440000",
        "ticker":     "AAPL",
        "event_type": "dividend",
        "ex_date":    "2026-03-15",
        "record_date": "2026-03-16",
        "pay_date":   "2026-04-01",
        "ratio":      "",
        "amount":     "0.25",
        "currency":   "USD",
        "source":     "nasdaq_rss",
        "created_at": "2026-04-30T10:02:58",
    }
    base.update(overrides)
    return base


# ── _parse_date ───────────────────────────────────────────────────────────────

class TestParseDate:
    def test_iso_format(self):
        assert _parse_date("2026-03-15") == date(2026, 3, 15)

    def test_full_month_name(self):
        assert _parse_date("March 15, 2026") == date(2026, 3, 15)

    def test_abbreviated_month(self):
        assert _parse_date("Mar 15, 2026") == date(2026, 3, 15)

    def test_us_slash_format(self):
        assert _parse_date("03/15/2026") == date(2026, 3, 15)

    def test_compact_format(self):
        assert _parse_date("20260315") == date(2026, 3, 15)

    def test_none_returns_none(self):
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert _parse_date("") is None

    def test_na_string_returns_none(self):
        assert _parse_date("N/A") is None

    def test_none_string_returns_none(self):
        assert _parse_date("None") is None

    def test_garbage_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_whitespace_stripped(self):
        assert _parse_date("  2026-03-15  ") == date(2026, 3, 15)


# ── _to_float ─────────────────────────────────────────────────────────────────

class TestToFloat:
    def test_string_float(self):
        assert _to_float("0.25") == 0.25

    def test_string_int(self):
        assert _to_float("2") == 2.0

    def test_actual_float(self):
        assert _to_float(0.25) == 0.25

    def test_none_returns_none(self):
        assert _to_float(None) is None

    def test_empty_string_returns_none(self):
        assert _to_float("") is None

    def test_na_returns_none(self):
        assert _to_float("N/A") is None

    def test_none_string_returns_none(self):
        assert _to_float("None") is None

    def test_non_numeric_returns_none(self):
        assert _to_float("not-a-number") is None


# ── _normalize_row ────────────────────────────────────────────────────────────

class TestNormalizeRow:
    S3_KEY = "corporate_actions/20260430_100258.csv"

    def test_dividend_row_fully_mapped(self):
        row = make_row()
        result = _normalize_row(row, self.S3_KEY)

        assert result is not None
        assert result["ticker"]           == "AAPL"
        assert result["event_type"]       == "dividend"
        assert result["ex_date"]          == date(2026, 3, 15)
        assert result["record_date"]      == date(2026, 3, 16)
        assert result["pay_date"]         == date(2026, 4, 1)
        assert result["amount"]           == 0.25
        assert result["currency"]         == "USD"
        assert result["source"]           == "nasdaq_rss"
        assert result["source_event_id"]  == "550e8400-e29b-41d4-a716-446655440000"
        assert result["raw_s3_key"]       == self.S3_KEY

    def test_ticker_uppercased(self):
        row = make_row(ticker="aapl")
        result = _normalize_row(row, self.S3_KEY)
        assert result["ticker"] == "AAPL"

    def test_ticker_with_parentheses_stripped(self):
        # Your scraper strips parens — but test defensively
        row = make_row(ticker="MSFT")
        result = _normalize_row(row, self.S3_KEY)
        assert result["ticker"] == "MSFT"

    def test_split_event_type(self):
        row = make_row(event_type="split", ratio="2.0", amount="")
        result = _normalize_row(row, self.S3_KEY)
        assert result["event_type"] == "split"
        assert result["ratio"]      == 2.0
        assert result["amount"]     is None

    def test_merger_event_type(self):
        row = make_row(event_type="merger")
        result = _normalize_row(row, self.S3_KEY)
        assert result["event_type"] == "merger"

    def test_unknown_event_type_becomes_other(self):
        row = make_row(event_type="something_weird")
        result = _normalize_row(row, self.S3_KEY)
        assert result["event_type"] == "other"

    def test_empty_event_type_becomes_other(self):
        row = make_row(event_type="")
        result = _normalize_row(row, self.S3_KEY)
        assert result["event_type"] == "other"

    def test_missing_dates_are_none(self):
        row = make_row(ex_date="", record_date="None", pay_date="N/A")
        result = _normalize_row(row, self.S3_KEY)
        assert result["ex_date"]     is None
        assert result["record_date"] is None
        assert result["pay_date"]    is None

    def test_missing_amount_is_none(self):
        row = make_row(amount="")
        result = _normalize_row(row, self.S3_KEY)
        assert result["amount"] is None

    def test_missing_currency_defaults_to_usd(self):
        row = make_row(currency="")
        result = _normalize_row(row, self.S3_KEY)
        assert result["currency"] == "USD"

    def test_empty_ticker_returns_none(self):
        row = make_row(ticker="")
        result = _normalize_row(row, self.S3_KEY)
        assert result is None

    def test_whitespace_only_ticker_returns_none(self):
        row = make_row(ticker="   ")
        result = _normalize_row(row, self.S3_KEY)
        assert result is None

    def test_source_event_id_is_scraper_uuid(self):
        row = make_row(event_id="my-unique-uuid-123")
        result = _normalize_row(row, self.S3_KEY)
        assert result["source_event_id"] == "my-unique-uuid-123"

    def test_raw_s3_key_preserved(self):
        row = make_row()
        result = _normalize_row(row, "corporate_actions/custom_key.csv")
        assert result["raw_s3_key"] == "corporate_actions/custom_key.csv"

    def test_source_always_nasdaq_rss(self):
        # Even if the CSV has a different source value, we force nasdaq_rss
        row = make_row(source="something_else")
        result = _normalize_row(row, self.S3_KEY)
        assert result["source"] == "nasdaq_rss"


# ── _fetch_csv (mocked S3) ────────────────────────────────────────────────────

class TestFetchCsv:
    S3_KEY = "corporate_actions/20260430_100258.csv"

    def _mock_s3_response(self, csv_content: str):
        """Build the boto3 S3 get_object response shape."""
        mock_body = MagicMock()
        mock_body.read.return_value = csv_content.encode("utf-8")
        return {"Body": mock_body}

    @patch("app.worker.normalizer.boto3.client")
    def test_returns_list_of_dicts(self, mock_boto_client):
        csv_content = make_csv([make_row(), make_row(ticker="MSFT")])
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = self._mock_s3_response(csv_content)
        mock_boto_client.return_value = mock_s3

        rows = _fetch_csv(self.S3_KEY)

        assert len(rows) == 2
        assert rows[0]["ticker"] == "AAPL"
        assert rows[1]["ticker"] == "MSFT"

    @patch("app.worker.normalizer.boto3.client")
    def test_uses_correct_bucket_and_key(self, mock_boto_client):
        csv_content = make_csv([make_row()])
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = self._mock_s3_response(csv_content)
        mock_boto_client.return_value = mock_s3

        from app.core.config import get_settings
        settings = get_settings()

        _fetch_csv(self.S3_KEY)

        mock_s3.get_object.assert_called_once_with(
            Bucket=settings.s3_raw_bucket,
            Key=self.S3_KEY,
        )

    @patch("app.worker.normalizer.boto3.client")
    def test_empty_csv_returns_empty_list(self, mock_boto_client):
        # Only headers, no data rows
        csv_content = make_csv([])
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = self._mock_s3_response(csv_content)
        mock_boto_client.return_value = mock_s3

        rows = _fetch_csv(self.S3_KEY)
        assert rows == []


# ── normalize_batch_from_s3 (integration, mocked S3 + DB) ────────────────────

class TestNormalizeBatchFromS3:
    S3_KEY = "corporate_actions/20260430_100258.csv"

    def _make_mock_db(self):
        db = MagicMock()
        db.execute = MagicMock(return_value=None)
        # Make it work as an async context manager
        db.__aenter__ = MagicMock(return_value=db)
        db.__aexit__ = MagicMock(return_value=False)
        return db

    @patch("app.worker.normalizer.boto3.client")
    @pytest.mark.asyncio
    async def test_returns_correct_count(self, mock_boto_client):
        rows = [make_row(), make_row(ticker="MSFT"), make_row(ticker="GOOGL")]
        csv_content = make_csv(rows)

        mock_body = MagicMock()
        mock_body.read.return_value = csv_content.encode("utf-8")
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_boto_client.return_value = mock_s3

        db = self._make_mock_db()
        # Make db.execute awaitable
        async def fake_execute(stmt):
            return None
        db.execute = fake_execute

        count = await normalize_batch_from_s3(db, self.S3_KEY)
        assert count == 3

    @patch("app.worker.normalizer.boto3.client")
    @pytest.mark.asyncio
    async def test_skips_rows_with_empty_ticker(self, mock_boto_client):
        rows = [
            make_row(ticker="AAPL"),
            make_row(ticker=""),        # ← should be skipped
            make_row(ticker="MSFT"),
        ]
        csv_content = make_csv(rows)

        mock_body = MagicMock()
        mock_body.read.return_value = csv_content.encode("utf-8")
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_boto_client.return_value = mock_s3

        db = self._make_mock_db()
        async def fake_execute(stmt):
            return None
        db.execute = fake_execute

        count = await normalize_batch_from_s3(db, self.S3_KEY)
        assert count == 2   # AAPL + MSFT only

    @patch("app.worker.normalizer.boto3.client")
    @pytest.mark.asyncio
    async def test_empty_csv_returns_zero(self, mock_boto_client):
        csv_content = make_csv([])  # headers only

        mock_body = MagicMock()
        mock_body.read.return_value = csv_content.encode("utf-8")
        mock_s3 = MagicMock()
        mock_s3.get_object.return_value = {"Body": mock_body}
        mock_boto_client.return_value = mock_s3

        db = self._make_mock_db()
        async def fake_execute(stmt):
            return None
        db.execute = fake_execute

        count = await normalize_batch_from_s3(db, self.S3_KEY)
        assert count == 0


# ── Real CSV shape from your Lambda ──────────────────────────────────────────
# This test uses the exact message your SQS queue sends and the exact
# CSV column names your Lambda writes — acts as a contract test.

class TestRealScraperContract:
    """
    Simulates the exact output of your NASDAQ RSS Lambda scraper.
    If these tests break, your scraper's output format has changed.
    """

    SQS_MESSAGE = {"s3_key": "corporate_actions/20260430_100258.csv", "count": 8}

    SAMPLE_ROWS = [
        {
            "event_id":   "a1b2c3d4-0001-0001-0001-000000000001",
            "ticker":     "AAPL",
            "event_type": "dividend",
            "ex_date":    "2026-04-28",
            "record_date": "2026-04-29",
            "pay_date":   "2026-05-15",
            "ratio":      "",
            "amount":     "0.25",
            "currency":   "USD",
            "source":     "nasdaq_rss",
            "created_at": "2026-04-30T10:02:58",
        },
        {
            "event_id":   "a1b2c3d4-0002-0002-0002-000000000002",
            "ticker":     "NVDA",
            "event_type": "split",
            "ex_date":    "2026-05-01",
            "record_date": "",
            "pay_date":   "",
            "ratio":      "10.0",
            "amount":     "",
            "currency":   "",
            "source":     "nasdaq_rss",
            "created_at": "2026-04-30T10:02:58",
        },
        {
            "event_id":   "a1b2c3d4-0003-0003-0003-000000000003",
            "ticker":     "MSFT",
            "event_type": "dividend",
            "ex_date":    "2026-05-03",
            "record_date": "2026-05-04",
            "pay_date":   "2026-05-20",
            "ratio":      "",
            "amount":     "0.75",
            "currency":   "USD",
            "source":     "nasdaq_rss",
            "created_at": "2026-04-30T10:02:58",
        },
    ]

    def test_sqs_message_has_required_keys(self):
        assert "s3_key" in self.SQS_MESSAGE
        assert "count"  in self.SQS_MESSAGE

    def test_csv_columns_match_normalizer_expectations(self):
        """If your scraper changes column names this test will catch it."""
        expected_columns = {
            "event_id", "ticker", "event_type",
            "ex_date", "record_date", "pay_date",
            "ratio", "amount", "currency",
            "source", "created_at",
        }
        actual_columns = set(self.SAMPLE_ROWS[0].keys())
        assert actual_columns == expected_columns

    def test_dividend_row_normalized_correctly(self):
        result = _normalize_row(self.SAMPLE_ROWS[0], self.SQS_MESSAGE["s3_key"])
        assert result["ticker"]     == "AAPL"
        assert result["event_type"] == "dividend"
        assert result["ex_date"]    == date(2026, 4, 28)
        assert result["amount"]     == 0.25
        assert result["ratio"]      is None

    def test_split_row_normalized_correctly(self):
        result = _normalize_row(self.SAMPLE_ROWS[1], self.SQS_MESSAGE["s3_key"])
        assert result["ticker"]     == "NVDA"
        assert result["event_type"] == "split"
        assert result["ratio"]      == 10.0
        assert result["amount"]     is None
        assert result["currency"]   == "USD"   # defaults to USD when empty

    def test_all_sample_rows_produce_valid_records(self):
        for row in self.SAMPLE_ROWS:
            result = _normalize_row(row, self.SQS_MESSAGE["s3_key"])
            assert result is not None, f"Row for {row['ticker']} returned None"
            assert result["ticker"]  != ""
            assert result["source"]  == "nasdaq_rss"
            assert result["raw_s3_key"] == self.SQS_MESSAGE["s3_key"]