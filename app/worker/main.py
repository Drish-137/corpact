"""
Worker: polls SQS for NASDAQ RSS batch notifications,
downloads each CSV from S3, normalizes rows, upserts into RDS PostgreSQL.

SQS message shape:
    { "s3_key": "corporate_actions/20260430_100258.csv", "count": 8 }

Run via:
    python -m app.worker.main
"""
import asyncio
import json
import signal

import boto3
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.logging import logger, setup_logging
from app.worker.normalizer import normalize_batch_from_s3

settings = get_settings()

POLL_WAIT    = 20   # SQS long-poll seconds — reduces empty receives
MAX_MESSAGES = 10   # max per receive call (your scraper sends 1 at a time, but safe to allow more)

_running = True     # flipped to False on SIGTERM/SIGINT for graceful shutdown


# ── Signal handling ───────────────────────────────────────────────────────────

def _handle_shutdown(sig, frame):
    global _running
    logger.info("shutdown signal received — draining and stopping", signal=sig)
    _running = False


# ── SQS client factory ────────────────────────────────────────────────────────

def _sqs_client():
    kwargs = {"region_name": settings.aws_region}
    if settings.aws_endpoint_url:
        # LocalStack in local dev — set AWS_ENDPOINT_URL=http://localstack:4566
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return boto3.client("sqs", **kwargs)


# ── Message processor ─────────────────────────────────────────────────────────

async def process_message(body: dict) -> None:
    """
    Handle one SQS message from the NASDAQ RSS Lambda scraper.
    Expects: { "s3_key": "corporate_actions/20260430_100258.csv", "count": 8 }
    """
    s3_key         = body.get("s3_key")
    expected_count = body.get("count", 0)

    if not s3_key:
        logger.warning("message missing s3_key — skipping", body=body)
        return

    async with AsyncSessionLocal() as db:
        actual_count = await normalize_batch_from_s3(db, s3_key)
        await db.commit()

    if actual_count != expected_count:
        logger.warning(
            "row count mismatch",
            s3_key=s3_key,
            expected=expected_count,
            actual=actual_count,
        )
    else:
        logger.info(
            "batch processed",
            s3_key=s3_key,
            expected=expected_count,
            actual=actual_count,
        )


# ── Main poll loop ────────────────────────────────────────────────────────────

async def run_loop() -> None:
    sqs = _sqs_client()
    logger.info("worker started", queue=settings.sqs_queue_url)

    while _running:
        try:
            resp = sqs.receive_message(
                QueueUrl            = settings.sqs_queue_url,
                MaxNumberOfMessages = MAX_MESSAGES,
                WaitTimeSeconds     = POLL_WAIT,   # long-poll — no charge for empty waits
            )
        except ClientError as exc:
            logger.error("sqs receive_message failed", error=str(exc))
            await asyncio.sleep(5)   # back off before retrying
            continue

        messages = resp.get("Messages", [])

        if not messages:
            # Normal — queue is empty, loop and long-poll again
            continue

        for msg in messages:
            receipt = msg["ReceiptHandle"]

            try:
                body = json.loads(msg["Body"])
                await process_message(body)

                # Only delete from SQS after successful processing
                sqs.delete_message(
                    QueueUrl      = settings.sqs_queue_url,
                    ReceiptHandle = receipt,
                )

            except json.JSONDecodeError as exc:
                logger.error("invalid JSON in SQS message", error=str(exc), body=msg["Body"])
                # Delete malformed messages so they don't block the queue forever
                sqs.delete_message(
                    QueueUrl      = settings.sqs_queue_url,
                    ReceiptHandle = receipt,
                )

            except Exception as exc:
                logger.error(
                    "message processing failed — leaving in queue for retry",
                    error=str(exc),
                    s3_key=json.loads(msg["Body"]).get("s3_key"),
                )
                # Do NOT delete — SQS will redeliver after the visibility timeout
                # Configure a dead-letter queue in AWS to catch repeated failures


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    setup_logging()

    signal.signal(signal.SIGTERM, _handle_shutdown)  # sent by Kubernetes on pod shutdown
    signal.signal(signal.SIGINT,  _handle_shutdown)  # Ctrl+C in local dev

    asyncio.run(run_loop())


if __name__ == "__main__":
    main()