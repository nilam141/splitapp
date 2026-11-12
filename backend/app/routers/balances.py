import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import services_balances
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import GroupBalances, OverallBalances

router = APIRouter(tags=["balances"])


@router.get("/groups/{group_id}/balances", response_model=GroupBalances)
def get_group_balances(group_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_balances.group_balances(db, user.id, group_id)


@router.get("/balances", response_model=OverallBalances)
def get_overall_balances(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_balances.overall_balances(db, user.id)
