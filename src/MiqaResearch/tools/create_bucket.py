import os
import sys
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT_URL"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    region_name="us-east-1",
)
bucket = os.environ["S3_BUCKET"]

for attempt in range(60):
    try:
        try:
            s3.head_bucket(Bucket=bucket)
        except ClientError:
            s3.create_bucket(Bucket=bucket)
        print(f"bucket {bucket} ready")
        sys.exit(0)
    except (BotoCoreError, ClientError) as exc:
        print(f"waiting for RustFS ({exc})", flush=True)
        time.sleep(1)

sys.exit("gave up waiting for RustFS")
