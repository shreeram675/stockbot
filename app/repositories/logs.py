from sqlalchemy.orm import Session

from app.db.models import AlertLog, SystemLog


class LogRepository:
    def __init__(self, db: Session):
        self.db = db

    def system(self, level: str, event: str, details: dict | None = None) -> None:
        self.db.add(SystemLog(level=level, event=event, details=details or {}))
        self.db.commit()

    def alert(
        self,
        alert_type: str,
        message: str,
        delivery_status: str,
        user_id: str | None = None,
        details: dict | None = None,
    ) -> None:
        self.db.add(
            AlertLog(
                user_id=user_id,
                alert_type=alert_type,
                message=message,
                delivery_status=delivery_status,
                details=details or {},
            )
        )
        self.db.commit()

