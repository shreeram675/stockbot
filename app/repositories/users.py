from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RiskPreference, User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_telegram_id(self, telegram_user_id: int) -> User | None:
        return self.db.scalar(select(User).where(User.telegram_user_id == telegram_user_id))

    def get_or_create(self, telegram_user_id: int, display_name: str | None) -> User:
        user = self.get_by_telegram_id(telegram_user_id)
        if user:
            return user
        user = User(telegram_user_id=telegram_user_id, display_name=display_name)
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def latest_risk(self, user_id: str) -> RiskPreference | None:
        return self.db.scalar(
            select(RiskPreference)
            .where(RiskPreference.user_id == user_id)
            .order_by(RiskPreference.created_at.desc())
        )

    def set_risk(self, user_id: str, mode: str, custom_notes: str | None = None) -> RiskPreference:
        preference = RiskPreference(user_id=user_id, mode=mode, custom_notes=custom_notes)
        self.db.add(preference)
        self.db.commit()
        self.db.refresh(preference)
        return preference

