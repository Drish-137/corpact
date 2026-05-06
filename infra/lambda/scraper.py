import csv
import io
import json
import os
import uuid
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
import boto3
import re


FEED_URL = "https://www.nasdaqtrader.com/Rss.aspx?feed=currentheadlines&categorylist=105"

s3 = boto3.client("s3")
sqs = boto3.client("sqs")

S3_BUCKET = os.environ["S3_BUCKET"]
S3_PREFIX = os.environ.get("S3_PREFIX", "corporate_actions/")
SQS_URL = os.environ["SQS_URL"]


def extract_fields(item):
    """
    Convert RSS item → normalized corporate action record.
    You can expand this logic as needed.
    """
    title = item.findtext("title") or ""
    desc = item.findtext("description") or ""

    # crude extraction helpers
    def find_date(label):
        for part in desc.split(";"):
            if label.lower() in part.lower():
                return part.split(":")[-1].strip()
        return None

    return {
        "event_id": str(uuid.uuid4()),
        "ticker": title.split(" ")[0].replace("(", "").replace(")", ""),
        "event_type": (
            "dividend" if "dividend" in title.lower()
            else "split" if "split" in title.lower()
            else "merger" if "merger" in title.lower()
            else "other"
        ),
        "ex_date": find_date("ex-date"),
        "record_date": find_date("record date"),
        "pay_date": find_date("pay date"),
        #"ratio": None,
        #"amount": None,
        "ratio":  find_ratio(desc),
        "amount": find_amount(desc),    
        "currency": None,
        "source": "nasdaq_rss",
        "created_at": datetime.utcnow().isoformat()
    }


def find_amount(desc):
    match = re.search(r'\$\s?([\d,]+\.?\d*)\s?per share', desc, re.IGNORECASE)
    if match:
        return float(match.group(1).replace(",", ""))
    return None


def find_ratio(desc):
    # e.g. "2-for-1 split" or "3:1 split"
    match = re.search(r'(\d+)[\-\s]for[\-\s](\d+)', desc, re.IGNORECASE)
    if match:
        return round(int(match.group(1)) / int(match.group(2)), 6)
    match = re.search(r'(\d+):(\d+)', desc)
    if match:
        return round(int(match.group(1)) / int(match.group(2)), 6)
    return None


def lambda_handler(event, context):
    # Fetch feed
    with urllib.request.urlopen(FEED_URL) as resp:
        xml_data = resp.read()

    # Parse XML
    root = ET.fromstring(xml_data)
    items = root.findall(".//item")

    records = [extract_fields(it) for it in items]

    # Write CSV to memory
    csv_buf = io.StringIO()
    writer = csv.DictWriter(csv_buf, fieldnames=[
        "event_id", "ticker", "event_type",
        "ex_date", "record_date", "pay_date",
        "ratio", "amount", "currency",
        "source", "created_at"
    ])
    writer.writeheader()
    writer.writerows(records)

    # Upload to S3
    key = f"{S3_PREFIX}{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=key,
        Body=csv_buf.getvalue().encode("utf-8"),
        ContentType="text/csv"
    )

    # Notify SQS
    sqs.send_message(
        QueueUrl=SQS_URL,
        MessageBody=json.dumps({"s3_key": key, "count": len(records)})
    )

    return {
        "status": "ok",
        "records_written": len(records),
        "s3_key": key
    }
