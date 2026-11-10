from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Category
from app.schemas import CategoryOut

router = APIRouter(tags=["reference"])


@router.get("/categories", response_model=list[CategoryOut])
def list_categories(response: Response, db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "public, max-age=86400"
    rows = db.scalars(select(Category).order_by(Category.sort_index, Category.id)).all()
    children: dict[int, list[CategoryOut]] = {}
    for c in rows:
        if c.parent_id is not None:
            children.setdefault(c.parent_id, []).append(CategoryOut.model_validate(c))
    out = []
    for c in rows:
        if c.parent_id is None:
            node = CategoryOut.model_validate(c)
            node.children = children.get(c.id, [])
            out.append(node)
    return out
