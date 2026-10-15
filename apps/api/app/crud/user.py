"""CRUD for users."""

from sqlalchemy.orm import Session

from app.models.user import User


class UserCRUD:
    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.query(User).filter(User.email == email.lower()).first()

    def get(self, db: Session, user_id: str) -> User | None:
        return db.get(User, user_id)

    def create(
        self, db: Session, email: str, name: str, hashed_password: str
    ) -> User:
        user = User(
            email=email.lower(),
            name=name,
            hashed_password=hashed_password,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    def list(self, db: Session, skip: int = 0, limit: int = 100) -> list[User]:
        return db.query(User).offset(skip).limit(limit).all()


user = UserCRUD()
