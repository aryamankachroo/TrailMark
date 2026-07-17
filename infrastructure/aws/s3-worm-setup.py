#!/usr/bin/env python3
"""Provision the TrailMark WORM bucket with S3 Object Lock.

Object Lock can only be enabled at bucket creation time, so this script must
run before the first ledger write. It is idempotent — safe to run repeatedly.

Local dev (LocalStack): boto3 honors AWS_ENDPOINT_URL, so nothing here is
LocalStack-specific.
    AWS_ENDPOINT_URL=http://localhost:4566 \
    AWS_ACCESS_KEY_ID=test AWS_SECRET_ACCESS_KEY=test AWS_DEFAULT_REGION=us-east-1 \
    WORM_BUCKET=trailmark-worm-dev python infrastructure/aws/s3-worm-setup.py

Production: point AWS credentials at the target account (no AWS_ENDPOINT_URL).
The per-object retain-until date is set at write time by the ledger service;
COMPLIANCE mode there is what makes objects non-erasable — this script only
guarantees the bucket is Object-Lock-capable and versioned.
"""

import os
import sys

import boto3
import botocore.exceptions

BUCKET = os.getenv("WORM_BUCKET", "trailmark-worm-dev")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")


def ensure_bucket(s3) -> None:
    try:
        s3.create_bucket(
            Bucket=BUCKET,
            ObjectLockEnabledForBucket=True,
            # us-east-1 must NOT send a LocationConstraint; every other region must.
            **(
                {"CreateBucketConfiguration": {"LocationConstraint": REGION}}
                if REGION != "us-east-1"
                else {}
            ),
        )
        print(f"created bucket {BUCKET} (Object Lock enabled)")
    except botocore.exceptions.ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"bucket {BUCKET} already exists — leaving it in place")
        else:
            raise


def main() -> int:
    s3 = boto3.client("s3")
    ensure_bucket(s3)

    # Enabling Object Lock at creation implicitly enables versioning (a
    # prerequisite); it cannot be re-set afterward, so we only verify state.
    cfg = s3.get_object_lock_configuration(Bucket=BUCKET)
    enabled = cfg.get("ObjectLockConfiguration", {}).get("ObjectLockEnabled")
    if enabled != "Enabled":
        print(
            f"ERROR: bucket {BUCKET} does not have Object Lock enabled. It must "
            "be recreated — Object Lock cannot be turned on after creation.",
            file=sys.stderr,
        )
        return 1

    print(f"WORM bucket ready: arn:aws:s3:::{BUCKET} (Object Lock ENABLED)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
