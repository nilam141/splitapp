"""Receipt images (S6-B-5). Order of checks: 404/403 (can the caller see the expense), 402 (premium), 409 (expense
deleted), then the file: 413 over 10 MB, 422 when it is not a JPEG or PNG (the declared type AND the file's first bytes
must agree). At most one receipt per expense; a new upload replaces the old one."""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Expense, Receipt, User
from app.schemas_expenses import ExpenseOut
from app.services_expenses import _load_visible, expense_out
from app.services_premium import require_premium
from app.storage import get_storage

MAX_BYTES = 10 * 1024 * 1024
_TYPES = {"image/jpeg": ("jpg", b"\xff\xd8\xff"), "image/png": ("png", b"\x89PNG\r\n\x1a\n")}


def _invalid(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message, {"fields": [{"field": "file", "message": message}]})


def too_large() -> ApiError:
    return ApiError(413, "VALIDATION_ERROR", "File too large", {"max_bytes": MAX_BYTES})


def check_upload_allowed(db: Session, me: User, expense_id: uuid.UUID) -> Expense:
    e = _load_visible(db, me, expense_id)
    require_premium(me, "receipt")
    if e.deleted_at is not None:
        raise ApiError(409, "ALREADY_DELETED", "Restore the expense to add a receipt")
    return e


def save_receipt(db: Session, me: User, expense_id: uuid.UUID, data: bytes, content_type: str | None) -> ExpenseOut:
    e = check_upload_allowed(db, me, expense_id)
    if len(data) > MAX_BYTES:
        raise too_large()
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype not in _TYPES:
        raise _invalid("Only JPEG and PNG images are accepted")
    ext, magic = _TYPES[ctype]
    if not data.startswith(magic):
        raise _invalid("The file is not a valid " + ("JPEG" if ext == "jpg" else "PNG") + " image")
    store = get_storage()
    key = f"receipts/{e.id}/{uuid.uuid4().hex}.{ext}"
    store.put(key, data)
    old = db.scalar(select(Receipt).where(Receipt.expense_id == e.id))
    old_key = old.storage_key if old is not None else None
    try:
        if old is None:
            db.add(Receipt(id=uuid.uuid4(), expense_id=e.id, storage_key=key, content_type=ctype,
                           size_bytes=len(data), uploaded_by=me.id))
        else:
            old.storage_key, old.content_type, old.size_bytes, old.uploaded_by = key, ctype, len(data), me.id
        db.commit()
    except Exception:
        db.rollback()
        store.delete(key)
        raise
    if old_key:
        store.delete(old_key)
    return expense_out(db, e, me.id)


def delete_receipt(db: Session, me: User, expense_id: uuid.UUID) -> None:
    """204 whether or not there was one. Not premium-gated: a user who lapsed can still remove their image."""
    e = _load_visible(db, me, expense_id)
    row = db.scalar(select(Receipt).where(Receipt.expense_id == e.id))
    if row is None:
        return
    key = row.storage_key
    db.delete(row)
    db.commit()
    get_storage().delete(key)
