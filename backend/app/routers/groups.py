import uuid

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import idempotency, services_groups
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import GroupCreate, GroupList, GroupOut, GroupUpdate, MembersAdd

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=GroupList)
def list_groups(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_groups.list_groups(db, user)


@router.post("", status_code=201, response_model=GroupOut)
def create_group(body: GroupCreate, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    key = idempotency.parse_header(request)
    status, payload = services_groups.create_group(db, user, body, key)
    return JSONResponse(payload, status_code=status)


@router.get("/{group_id}", response_model=GroupOut)
def get_group(group_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_groups.get_group(db, user, group_id)


@router.patch("/{group_id}", response_model=GroupOut)
def update_group(group_id: uuid.UUID, body: GroupUpdate, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return services_groups.update_group(db, user, group_id, body)


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_groups.delete_group(db, user, group_id)
    return Response(status_code=204)


@router.post("/{group_id}/members", response_model=GroupOut)
def add_members(group_id: uuid.UUID, body: MembersAdd, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    return services_groups.add_members(db, user, group_id, body)


@router.delete("/{group_id}/members/{user_id}", status_code=204)
def remove_member(group_id: uuid.UUID, user_id: str, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    services_groups.remove_member(db, user, group_id, user_id)
    return Response(status_code=204)
