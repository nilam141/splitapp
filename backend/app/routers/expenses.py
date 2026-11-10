import uuid

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app import idempotency, services_expenses, timeline
from app.auth_deps import get_current_user
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.schemas_expenses import (CommentCreate, CommentOut, CommentPage, ExpenseCreate, ExpenseOut, ExpensePage,
                                  ExpenseUpdate, TimelinePage)

router = APIRouter(tags=["expenses"])

Limit = Query(50, ge=1, le=100)


@router.post("/groups/{group_id}/expenses", status_code=201, response_model=ExpenseOut)
def create_group_expense(group_id: uuid.UUID, body: ExpenseCreate, request: Request,
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = idempotency.parse_header(request)
    status, payload = services_expenses.create_expense(db, user, body, group_id, key)
    return JSONResponse(payload, status_code=status)


@router.get("/groups/{group_id}/expenses", response_model=ExpensePage)
def list_group_expenses(group_id: uuid.UUID, limit: int = Limit, cursor: str | None = Query(None),
                        include_deleted: bool = Query(False), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    return services_expenses.list_group_expenses(db, user, group_id, limit, cursor, include_deleted)


@router.get("/groups/{group_id}/timeline", response_model=TimelinePage, tags=["groups"])
def list_group_timeline(group_id: uuid.UUID, limit: int = Limit, cursor: str | None = Query(None),
                        include_deleted: bool = Query(False), user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    return timeline.list_timeline(db, user, group_id, limit, cursor, include_deleted)


@router.get("/expenses", response_model=ExpensePage)
def list_expenses(limit: int = Limit, cursor: str | None = Query(None), q: str | None = Query(None, min_length=2),
                  friend_user_id: uuid.UUID | None = Query(None), non_group: bool | None = Query(None),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if q is not None:  # premium search ships with S6-B-6
        raise ApiError(501, "NOT_IMPLEMENTED", "Expense search is not available yet")
    return services_expenses.list_expenses(db, user, limit, cursor, friend_user_id, non_group)


@router.post("/expenses", status_code=201, response_model=ExpenseOut)
def create_expense(body: ExpenseCreate, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    key = idempotency.parse_header(request)
    status, payload = services_expenses.create_expense(db, user, body, None, key)
    return JSONResponse(payload, status_code=status)


@router.get("/expenses/{expense_id}", response_model=ExpenseOut)
def get_expense(expense_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_expenses.get_expense(db, user, expense_id)


@router.patch("/expenses/{expense_id}", response_model=ExpenseOut)
def update_expense(expense_id: uuid.UUID, body: ExpenseUpdate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return services_expenses.update_expense(db, user, expense_id, body)


@router.delete("/expenses/{expense_id}", response_model=ExpenseOut)
def delete_expense(expense_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_expenses.delete_expense(db, user, expense_id)


@router.post("/expenses/{expense_id}/restore", response_model=ExpenseOut)
def restore_expense(expense_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_expenses.restore_expense(db, user, expense_id)


@router.get("/expenses/{expense_id}/comments", tags=["comments"], response_model=CommentPage)
def list_comments(expense_id: uuid.UUID, limit: int = Limit, cursor: str | None = Query(None),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return services_expenses.list_comments(db, user, expense_id, limit, cursor)


@router.post("/expenses/{expense_id}/comments", tags=["comments"], status_code=201, response_model=CommentOut)
def create_comment(expense_id: uuid.UUID, body: CommentCreate, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    return services_expenses.create_comment(db, user, expense_id, body)
