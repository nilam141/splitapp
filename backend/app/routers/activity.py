import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app import services_activity
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas_settlements import ActivityPage

router = APIRouter(tags=["activity"])


@router.get("/activity", response_model=ActivityPage)
def list_activity(limit: int = Query(50, ge=1, le=100), cursor: str | None = Query(None),
                  group_id: uuid.UUID | None = Query(None), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    return services_activity.list_activity(db, user, limit, cursor, group_id)


@router.post("/activity/read", status_code=204)
def mark_activity_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_activity.mark_read(db, user)
    return Response(status_code=204)
