"""Auth endpoints: register, login, me."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import hash_password, verify_password, create_access_token
from app.core.deps import get_current_user
from app.crud.user import user as user_crud
from app.schemas.auth import LoginRequest, RegisterRequest, Token
from app.schemas.user import UserOut
from app.models.user import User

router = APIRouter(tags=["auth"])


@router.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> Token:
    if user_crud.get_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    user = user_crud.create(
        db,
        email=payload.email,
        name=payload.name,
        hashed_password=hash_password(payload.password),
    )
    token = create_access_token(subject=user.id, extra_claims={"email": user.email})
    return Token(access_token=token, user_id=user.id)


@router.post("/auth/login", response_model=Token)
def login_json(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = user_crud.get_by_email(db, payload.email)
    if user is None or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")

    token = create_access_token(subject=user.id, extra_claims={"email": user.email})
    return Token(access_token=token, user_id=user.id)


@router.post("/auth/login/form", response_model=Token)
def login_form(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """OAuth2 password flow (works with FastAPI's Swagger UI 'Authorize')."""
    user = user_crud.get_by_email(db, form.username)
    if user is None or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(subject=user.id, extra_claims={"email": user.email})
    return Token(access_token=token, user_id=user.id)


@router.get("/auth/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user
