from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Currency
from app.schemas import CurrencyOut

router = APIRouter(tags=["reference"])


@router.get("/currencies", response_model=list[CurrencyOut])
def list_currencies(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=86400"
    return db.scalars(select(Currency).where(Currency.is_active).order_by(Currency.code)).all()
