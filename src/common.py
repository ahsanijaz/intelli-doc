"""Shared helpers for the pKYC POC. Everything talks to an S3-compatible
endpoint (MinIO, moto, AWS) selected via S3_ENDPOINT env var."""
import os, json, yaml, boto3
from botocore.config import Config

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "out")

def load_ontology():
    with open(os.path.join(ROOT, "config", "ontology.yaml")) as f:
        return yaml.safe_load(f)

def s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ.get("S3_ENDPOINT", "http://127.0.0.1:9000"),
        aws_access_key_id=os.environ.get("S3_KEY", "minioadmin"),
        aws_secret_access_key=os.environ.get("S3_SECRET", "minioadmin"),
        region_name="us-east-1",
        config=Config(s3={"addressing_style": "path"}),
    )

def put_json(client, bucket, key, obj):
    client.put_object(Bucket=bucket, Key=key, Body=json.dumps(obj, indent=2).encode())

def get_json(client, bucket, key):
    return json.loads(client.get_object(Bucket=bucket, Key=key)["Body"].read())

def list_keys(client, bucket, prefix=""):
    keys, token = [], None
    while True:
        kw = dict(Bucket=bucket, Prefix=prefix, MaxKeys=1000)
        if token: kw["ContinuationToken"] = token
        r = client.list_objects_v2(**kw)
        keys += [o["Key"] for o in r.get("Contents", [])]
        if not r.get("IsTruncated"): return keys
        token = r["NextContinuationToken"]

def save_out(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w") as f:
        json.dump(obj, f, indent=2)
