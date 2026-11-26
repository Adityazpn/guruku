"""File storage behind one interface: local disk (single server) or any S3-compatible bucket (AWS S3, Cloudflare R2, MinIO).
Files are never public. Downloads go through short-lived signed URLs; keys are random UUIDs (never user-supplied paths)."""
import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

from app.core.config import get_settings
from app.core.security import _secret


class Storage:
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def get(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...
    def signed_url(self, key: str, filename: str, content_type: str, ttl: int = 300) -> str: ...


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents:  # defence in depth against path traversal
            raise ValueError("invalid storage key")
        return p

    def put(self, key, data, content_type):
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)

    def get(self, key):
        return self._path(key).read_bytes()

    def delete(self, key):
        self._path(key).unlink(missing_ok=True)

    def signed_url(self, key, filename, content_type, ttl=300):
        payload = base64.urlsafe_b64encode(json.dumps({"k": key, "f": filename, "t": content_type, "e": int(time.time()) + ttl}).encode()).decode()
        sig = hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
        return f"/api/v1/library/files/{payload}.{sig}"


def verify_local_token(token: str) -> dict | None:
    try:
        payload, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(_secret().encode(), payload.encode(), hashlib.sha256).hexdigest(), sig):
            return None
        d = json.loads(base64.urlsafe_b64decode(payload))
        return d if d["e"] >= time.time() else None
    except Exception:  # noqa: BLE001
        return None


class S3Storage(Storage):
    def __init__(self):
        import boto3
        from botocore.config import Config

        s = get_settings()
        self.bucket = s.s3_bucket
        self.client = boto3.client("s3", endpoint_url=s.s3_endpoint or None, region_name=s.s3_region, aws_access_key_id=s.s3_access_key,
                                   aws_secret_access_key=s.s3_secret_key, config=Config(signature_version="s3v4"))

    def put(self, key, data, content_type):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key):
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def signed_url(self, key, filename, content_type, ttl=300):
        safe = filename.replace('"', "")
        return self.client.generate_presigned_url("get_object", ExpiresIn=ttl, Params={
            "Bucket": self.bucket, "Key": key, "ResponseContentDisposition": f'attachment; filename="{safe}"', "ResponseContentType": content_type})


def get_storage() -> Storage:
    s = get_settings()
    if s.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(os.environ.get("STORAGE_DIR", s.storage_dir))
