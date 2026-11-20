"""Export schemas mirroring docs/openapi.yaml (ExportCreate, Export)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ExportCreate(BaseModel):
    scope: Literal["group", "friend"]
    group_id: uuid.UUID | None = None
    friend_user_id: uuid.UUID | None = None
    format: Literal["csv"] = "csv"


class ExportOut(BaseModel):
    id: uuid.UUID
    status: Literal["pending", "ready", "failed"]
    scope: Literal["group", "friend"]
    format: Literal["csv"]
    download_url: str | None = None
    file_name: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
