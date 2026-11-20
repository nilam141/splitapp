import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from app import services_exports
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas_exports import ExportCreate, ExportOut

router = APIRouter(prefix="/exports", tags=["exports"])


def _generate_in_background(bind, export_id: uuid.UUID) -> None:
    """Runs after the 202 is sent, on its own session (the request's session is closed by then)."""
    with Session(bind=bind, expire_on_commit=False) as session:
        services_exports.generate(session, export_id)


@router.post("", status_code=202, response_model=ExportOut)
def create_export(body: ExportCreate, tasks: BackgroundTasks, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    out = services_exports.create_export(db, user, body)
    tasks.add_task(_generate_in_background, db.get_bind(), out.id)
    return out


@router.get("/{export_id}", response_model=ExportOut)
def get_export(export_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_exports.get_export(db, user, export_id)
