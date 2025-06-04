from core.base import Base
from sqlalchemy import Column, Integer, String, DateTime, Boolean
import datetime

class SupportTicket(Base):
    __tablename__ = 'support_tickets'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    user_name = Column(String)  # Может быть NULL
    username = Column(String)   # Может быть NULL
    message = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    resolved = Column(Boolean, default=False)
    photo_path = Column(String) 