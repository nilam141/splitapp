import uuid

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app import services_recurring
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas_recurring import RecurringCreate, RecurringList, RecurringRuleOut, RecurringUpdate

router = APIRouter(prefix="/recurring-expenses", tags=["recurring"])


@router.get("", response_model=RecurringList)
def list_recurring(group_id: uuid.UUID | None = Query(None), user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return services_recurring.list_rules(db, user, group_id)


@router.post("", status_code=201, response_model=RecurringRuleOut)
def create_recurring(body: RecurringCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_recurring.create_rule(db, user, body)


@router.patch("/{rule_id}", response_model=RecurringRuleOut)
def update_recurring(rule_id: uuid.UUID, body: RecurringUpdate, user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    return services_recurring.update_rule(db, user, rule_id, body)


@router.delete("/{rule_id}", status_code=204)
def delete_recurring(rule_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_recurring.delete_rule(db, user, rule_id)
    return Response(status_code=204)
