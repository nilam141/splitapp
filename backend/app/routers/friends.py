import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import idempotency, services_friends
from app.auth_deps import get_current_user
from app.db import get_db
from app.models import User
from app.schemas import Friend, FriendCreate, FriendCreated, FriendList

router = APIRouter(prefix="/friends", tags=["friends"])


@router.get("", response_model=FriendList)
def list_friends(filter: Literal["all", "outstanding", "owes_me", "i_owe"] = Query("all"),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return FriendList(items=services_friends.list_friends(db, user, filter))


@router.post("", status_code=201, response_model=FriendCreated, responses={200: {"model": FriendCreated}})
def add_friend(body: FriendCreate, request: Request, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    key = idempotency.parse_header(request)
    status, payload = services_friends.add_friend(db, user, body, key)
    return JSONResponse(payload, status_code=status)


@router.get("/{user_id}", response_model=Friend)
def get_friend(user_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_friends.get_friend(db, user, user_id)


@router.delete("/{user_id}", status_code=204)
def remove_friend(user_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    services_friends.remove_friend(db, user, user_id)
    return Response(status_code=204)
