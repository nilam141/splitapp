import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import idempotency, services_settlements
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas_settlements import (SettleAllOut, SettleAllRequest, SettlementCreate, SettlementOut, SettlementPage,
                                     SettlementUpdate)

router = APIRouter(tags=["settlements"])


@router.get("/settlements", response_model=SettlementPage)
def list_settlements(limit: int = Query(50, ge=1, le=100), cursor: str | None = Query(None),
                     group_id: uuid.UUID | None = Query(None), friend_user_id: uuid.UUID | None = Query(None),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_settlements.list_settlements(db, user, limit, cursor, group_id, friend_user_id)


@router.post("/settlements", status_code=201, response_model=SettlementOut)
def create_settlement(body: SettlementCreate, request: Request, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    key = idempotency.parse_header(request)
    status, payload = services_settlements.create_settlement(db, user, body, key)
    return JSONResponse(payload, status_code=status)


@router.post("/settlements/settle-all", status_code=201, response_model=SettleAllOut)
def settle_all(body: SettleAllRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_settlements.settle_all(db, user, body)


@router.get("/settlements/{settlement_id}", response_model=SettlementOut)
def get_settlement(settlement_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_settlements.get_settlement(db, user, settlement_id)


@router.patch("/settlements/{settlement_id}", response_model=SettlementOut)
def update_settlement(settlement_id: uuid.UUID, body: SettlementUpdate, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return services_settlements.update_settlement(db, user, settlement_id, body)


@router.delete("/settlements/{settlement_id}", response_model=SettlementOut)
def delete_settlement(settlement_id: uuid.UUID, user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return services_settlements.delete_settlement(db, user, settlement_id)


@router.post("/settlements/{settlement_id}/restore", response_model=SettlementOut)
def restore_settlement(settlement_id: uuid.UUID, user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    return services_settlements.restore_settlement(db, user, settlement_id)
