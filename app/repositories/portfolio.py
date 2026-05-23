from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Holding, PortfolioSnapshot, Recommendation


class PortfolioRepository:
    def __init__(self, db: Session):
        self.db = db

    def save_snapshot(self, snapshot: PortfolioSnapshot, holdings: list[Holding]) -> PortfolioSnapshot:
        self.db.add(snapshot)
        self.db.flush()
        for holding in holdings:
            holding.snapshot_id = snapshot.id
            self.db.add(holding)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def latest_snapshot(self, user_id: str) -> PortfolioSnapshot | None:
        return self.db.scalar(
            select(PortfolioSnapshot)
            .where(PortfolioSnapshot.user_id == user_id)
            .order_by(PortfolioSnapshot.captured_at.desc())
        )

    def snapshots(self, user_id: str, limit: int = 60) -> list[PortfolioSnapshot]:
        return list(
            self.db.scalars(
                select(PortfolioSnapshot)
                .where(PortfolioSnapshot.user_id == user_id)
                .order_by(PortfolioSnapshot.captured_at.desc())
                .limit(limit)
            )
        )

    def holdings_for_snapshot(self, snapshot_id: str) -> list[Holding]:
        return list(self.db.scalars(select(Holding).where(Holding.snapshot_id == snapshot_id)))

    def save_recommendation(self, recommendation: Recommendation) -> Recommendation:
        self.db.add(recommendation)
        self.db.commit()
        self.db.refresh(recommendation)
        return recommendation

    def latest_recommendation(self, user_id: str) -> Recommendation | None:
        return self.db.scalar(
            select(Recommendation)
            .where(Recommendation.user_id == user_id)
            .order_by(Recommendation.created_at.desc())
        )

