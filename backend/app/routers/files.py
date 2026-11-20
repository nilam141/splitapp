"""Serves locally stored files through signed, expiring URLs (the stand-in for a bucket's presigned URLs).
Not in docs/openapi.yaml on purpose: clients only ever see the full URL in `receipt_url` / `download_url`."""
import mimetypes

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.errors import ApiError
from app.storage import get_storage

router = APIRouter(include_in_schema=False)


@router.get("/files/{key:path}")
def get_file(key: str, exp: int = Query(...), sig: str = Query(...)):
    store = get_storage()
    try:
        ok = store.verify(key, exp, sig) and store.exists(key)
    except ValueError:
        ok = False
    if not ok:
        raise ApiError(404, "NOT_FOUND", "File not found or link expired")
    media = mimetypes.guess_type(key)[0] or "application/octet-stream"
    headers = {"Cache-Control": "private, no-store"}
    if key.endswith(".csv"):
        headers["Content-Disposition"] = f'attachment; filename="{key.rsplit("/", 1)[-1]}"'
    return Response(store.read(key), media_type=media, headers=headers)
