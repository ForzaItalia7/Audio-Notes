"""S3-compatible private audio storage and short-lived Gnani fetch URLs."""
import hashlib
import hmac
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit

import requests


class StorageError(RuntimeError):
    pass


def configuration():
    bucket = os.getenv("AUDIO_BUCKET")
    endpoint = os.getenv("S3_ENDPOINT_URL")
    access = os.getenv("AWS_ACCESS_KEY_ID")
    secret = os.getenv("AWS_SECRET_ACCESS_KEY")
    region = os.getenv("AWS_REGION", "auto")
    if not bucket:
        return None
    if not all((endpoint, access, secret)):
        raise StorageError("AUDIO_BUCKET requires S3_ENDPOINT_URL, AWS_ACCESS_KEY_ID, and AWS_SECRET_ACCESS_KEY.")
    parts = urlsplit(endpoint)
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise StorageError("S3_ENDPOINT_URL must be an HTTPS base URL without a query or fragment.")
    return bucket, endpoint.rstrip("/"), access, secret, region


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def signing_key(secret: str, date: str, region: str) -> bytes:
    date_key = hmac.new(("AWS4" + secret).encode(), date.encode(), hashlib.sha256).digest()
    region_key = hmac.new(date_key, region.encode(), hashlib.sha256).digest()
    service_key = hmac.new(region_key, b"s3", hashlib.sha256).digest()
    return hmac.new(service_key, b"aws4_request", hashlib.sha256).digest()


def canonical_path(endpoint: str, bucket: str, key: str) -> tuple[str, str]:
    base = urlsplit(endpoint)
    path = f"{base.path.rstrip('/')}/{quote(bucket, safe='-_.~')}/{quote(key, safe='/-_.~')}"
    return path or "/", f"{base.scheme}://{base.netloc}{path}"


def make_presigned_get(path: str, expires: int = 3600) -> str:
    conf = configuration()
    if conf is None:
        raise StorageError("Audio bucket is not configured.")
    bucket, endpoint, access, secret, region = conf
    if not 1 <= expires <= 604800:
        raise ValueError("Presigned URL expiry must be within seven days.")
    prefix = f"s3://{bucket}/"
    if not path.startswith(prefix):
        raise StorageError("Audio path does not belong to the configured bucket.")
    key = path[len(prefix):]
    url_path, base_url = canonical_path(endpoint, bucket, key)
    host = urlsplit(endpoint).netloc
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date = now.strftime("%Y%m%d")
    scope = f"{date}/{region}/s3/aws4_request"
    params = {
        "X-Amz-Algorithm": "AWS4-HMAC-SHA256",
        "X-Amz-Credential": f"{access}/{scope}",
        "X-Amz-Date": amz_date,
        "X-Amz-Expires": str(expires),
        "X-Amz-SignedHeaders": "host",
    }
    canonical_query = urlencode(sorted(params.items()), quote_via=quote, safe="-_.~")
    canonical_request = f"GET\n{url_path}\n{canonical_query}\nhost:{host}\n\nhost\nUNSIGNED-PAYLOAD"
    to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{sha256_hex(canonical_request.encode())}"
    signature = hmac.new(signing_key(secret, date, region), to_sign.encode(), hashlib.sha256).hexdigest()
    return f"{base_url}?{canonical_query}&X-Amz-Signature={signature}"


def store_audio(local_path: Path, key: str, content_type: str | None):
    conf = configuration()
    if conf is None:
        return str(local_path)
    bucket, endpoint, access, secret, region = conf
    payload_hash = hashlib.sha256()
    with local_path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            payload_hash.update(chunk)
    body_hash = payload_hash.hexdigest()
    url_path, base_url = canonical_path(endpoint, bucket, key)
    host = urlsplit(endpoint).netloc
    now = datetime.now(timezone.utc)
    amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
    scope = f"{date}/{region}/s3/aws4_request"
    mime = content_type or "application/octet-stream"
    canonical_headers = f"content-type:{mime}\nhost:{host}\nx-amz-content-sha256:{body_hash}\nx-amz-date:{amz_date}\n"
    signed_headers = "content-type;host;x-amz-content-sha256;x-amz-date"
    canonical_request = f"PUT\n{url_path}\n\n{canonical_headers}\n{signed_headers}\n{body_hash}"
    to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{sha256_hex(canonical_request.encode())}"
    signature = hmac.new(signing_key(secret, date, region), to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
    with local_path.open("rb") as source:
        response = requests.put(base_url, data=source, headers={
            "Authorization": auth, "Content-Type": mime, "Content-Length": str(local_path.stat().st_size),
            "Host": host, "x-amz-content-sha256": body_hash, "x-amz-date": amz_date,
        }, timeout=(15, 1800))
    if not response.ok:
        raise StorageError(f"Object storage upload failed with HTTP {response.status_code}.")
    return f"s3://{bucket}/{key}"


def transcription_url(path: str):
    if not path.startswith("s3://"):
        return None
    return make_presigned_get(path)


def exists(path: str, local_directory: Path):
    if path.startswith("s3://"):
        url = make_presigned_get(path, 300)
        # The signed URL binds the HTTP method; use the matching GET method.
        response = requests.get(url, headers={"Range": "bytes=0-0"}, stream=True, timeout=15)
        if response.status_code == 404:
            response.close()
            return False
        if response.status_code in (401, 403):
            response.close()
            raise StorageError("Could not access the private audio object.")
        try:
            response.raise_for_status()
        finally:
            response.close()
        return True
    local = Path(path).resolve()
    try:
        local.relative_to(local_directory.resolve())
    except ValueError:
        return False
    return local.is_file()


def remove_audio(path: str):
    if path.startswith("s3://"):
        conf = configuration()
        if conf is None:
            raise StorageError("Audio bucket is not configured.")
        bucket, endpoint, access, secret, region = conf
        prefix = f"s3://{bucket}/"
        if not path.startswith(prefix):
            raise StorageError("Audio path does not belong to the configured bucket.")
        key = path[len(prefix):]
        url_path, url = canonical_path(endpoint, bucket, key)
        host = urlsplit(endpoint).netloc
        payload_hash = sha256_hex(b"")
        now = datetime.now(timezone.utc)
        amz_date, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        scope = f"{date}/{region}/s3/aws4_request"
        canonical_headers = f"host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n"
        signed_headers = "host;x-amz-content-sha256;x-amz-date"
        canonical_request = f"DELETE\n{url_path}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
        to_sign = f"AWS4-HMAC-SHA256\n{amz_date}\n{scope}\n{sha256_hex(canonical_request.encode())}"
        signature = hmac.new(signing_key(secret, date, region), to_sign.encode(), hashlib.sha256).hexdigest()
        auth = f"AWS4-HMAC-SHA256 Credential={access}/{scope}, SignedHeaders={signed_headers}, Signature={signature}"
        response = requests.delete(url, headers={"Authorization": auth, "Host": host,
            "x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}, timeout=30)
        if not response.ok:
            raise StorageError(f"Object storage delete failed with HTTP {response.status_code}.")
    else:
        remove_local_file(Path(path))


def remove_local_file(path: Path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
