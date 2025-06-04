from core.base import Base
from sqlalchemy import Column, Integer, String

class Performer(Base):
    __tablename__ = 'performers_telegram'
    id = Column(Integer, primary_key=True)
    performer_name = Column(String, unique=True, nullable=False)
    telegram_user_id = Column(Integer, unique=True, nullable=False)
    google_tokens = Column(String)

    def clear_google_tokens(self):
        """Очищает токены Google OAuth"""
        self.google_tokens = None