from core.base import Base
from sqlalchemy import Column, Integer, String, DateTime
import datetime 

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    user_name = Column(String)
    username = Column(String)
    order_date = Column(String, nullable=False)
    order_time = Column(String, nullable=False)
    order_location = Column(String)
    order_performers = Column(String)
    order_program = Column(String)
    order_amount = Column(String)
    order_details = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default='pending')
    calendar_event_id = Column(String)