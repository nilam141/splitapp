"""Object storage for receipts and exports (S6-B-5, S6-B-7). One local-disk implementation behind a small interface;
a cloud bucket would replace `LocalStorage` and return its own presigned URLs from `signed_url`. Local URLs are
`<storage_public_base_url>/<key>?exp=<unix>&sig=<hmac>` and are served by `app.routers.files` (not part of the API
contract: it is the stand-in for the bucket's own HTTP endpoint)."""
import hashlib
import hmac
import re
import time
from pathlib import Path

from app.config import settings

_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,200}$")


def _secret() -> bytes:
    return (settings.storage_signing_secret or settings.jwt_secret).encode()


def _sign(key: str, exp: int) -> str:
    return hmac.new(_secret(), f"{key}\n{exp}".encode(), hashlib.sha256).hexdigest()


class LocalStorage:
    def __init__(self, root: str):
        self.root = Path(root).resolve()

    def _path(self, key: str) -> Path:
        if not _KEY.match(key) or ".." in key.split("/"):
            raise ValueError("invalid storage key")
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid storage key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".part")
        tmp.write_bytes(data)
        tmp.replace(path)

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def signed_url(self, key: str, ttl_seconds: int, now: float | None = None) -> str:
        exp = int((time.time() if now is None else now) + ttl_seconds)
        return f"{settings.storage_public_base_url.rstrip('/')}/{key}?exp={exp}&sig={_sign(key, exp)}"

    def verify(self, key: str, exp: int, sig: str, now: float | None = None) -> bool:
        return exp >= (time.time() if now is None else now) and hmac.compare_digest(sig, _sign(key, exp))


def get_storage() -> LocalStorage:
    return LocalStorage(settings.storage_dir)
