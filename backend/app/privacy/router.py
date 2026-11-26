from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import get_current_user
from app.privacy import service
from app.users.models import User

router = APIRouter(tags=["privacy"])


class ConsentIn(BaseModel):
    type: str = Field(default="student_data", pattern="^student_data$")


@router.get("/me/consents")
def my_consents(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"student_data": service.has_consent(db, user.id), "text": service.CONSENT_TEXT, "version": service.CONSENT_VERSION}


@router.post("/me/consents", status_code=201)
def give(body: ConsentIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.grant(db, user.id, body.type)
    db.commit()
    return {"student_data": True}


@router.delete("/me/consents/{type_}", status_code=204)
def withdraw(type_: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    service.revoke(db, user.id, type_)
    db.commit()


@router.post("/me/student-data/delete")
def erase(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Right-to-erasure helper for student-related content created by the user."""
    out = service.delete_student_data(db, user.id)
    db.commit()
    return out
