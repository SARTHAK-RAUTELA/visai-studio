"""
Storage service — Phase 5.
Abstracts file storage: local filesystem in dev, AWS S3 in production.
Set USE_S3=true in .env to enable S3; otherwise uses local paths.
"""

import os
from pathlib import Path


class StorageService:
    def __init__(self):
        self.use_s3 = os.getenv("USE_S3", "false").lower() in ("1", "true", "yes")
        self._s3 = None
        self._bucket = None

        if self.use_s3:
            try:
                import boto3
                self._bucket = os.getenv("S3_BUCKET_NAME", "")
                self._s3 = boto3.client(
                    "s3",
                    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    region_name=os.getenv("AWS_REGION", "us-east-1"),
                )
            except ImportError:
                print("Warning: boto3 is not installed. Falling back to local storage.")
                self.use_s3 = False

    def save(self, local_path: str, key: str) -> str:
        """Upload file to S3 and return URL, or return local_path if local mode."""
        if not self.use_s3:
            return local_path
        self._s3.upload_file(local_path, self._bucket, key)
        return f"https://{self._bucket}.s3.amazonaws.com/{key}"

    def get_url(self, key: str) -> str:
        """Return presigned S3 URL (1 hour) or file:// URI in local mode."""
        if not self.use_s3:
            return Path(key).resolve().as_uri()
        url = self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=3600,
        )
        return url

    def delete(self, key: str) -> bool:
        """Delete file from S3 or local disk. Returns True on success."""
        try:
            if self.use_s3:
                self._s3.delete_object(Bucket=self._bucket, Key=key)
            else:
                path = Path(key)
                if path.exists():
                    path.unlink()
            return True
        except Exception as e:
            print(f"StorageService.delete failed for '{key}': {e}")
            return False

    def exists(self, key: str) -> bool:
        """Check whether a file exists locally or in S3."""
        if not self.use_s3:
            return Path(key).exists()
        try:
            self._s3.head_object(Bucket=self._bucket, Key=key)
            return True
        except Exception:
            return False

    def list_outputs(self, prefix: str = "") -> list:
        """
        List output files.
        Returns list of {"key", "size", "modified"} dicts.
        """
        if not self.use_s3:
            base = Path(prefix) if prefix else Path(".")
            if not base.exists():
                return []
            results = []
            for p in sorted(base.iterdir()):
                if p.is_file():
                    stat = p.stat()
                    results.append({
                        "key": str(p),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })
            return results

        paginator = self._s3.get_paginator("list_objects_v2")
        results = []
        for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
            for obj in page.get("Contents", []):
                results.append({
                    "key": obj["Key"],
                    "size": obj["Size"],
                    "modified": obj["LastModified"].timestamp(),
                })
        return results
