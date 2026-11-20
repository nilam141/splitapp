from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app import services_reminders
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import ReminderCreate

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post("", status_code=202)
def create_reminder(body: ReminderCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_reminders.create_reminder(db, user, body)
    return Response(status_code=202)
