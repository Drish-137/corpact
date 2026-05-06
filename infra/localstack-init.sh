#!/bin/bash
# Runs inside LocalStack on startup — creates local SQS queue and S3 bucket

awslocal sqs create-queue --queue-name corpact-events
awslocal s3 mb s3://corpact-raw-events

echo "LocalStack resources created"
