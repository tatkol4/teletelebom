import os
import shutil
os.environ["SQLALCHEMY_WARN_20"] = "0"

# Удаляем старую базу данных
if os.path.exists("orders.db"):
    os.remove("orders.db")

from core.database import db, Base
from models.order import Order
from models.support_ticket import SupportTicket
from models.performer import Performer

# Создаем таблицы
Base.metadata.create_all(db.engine)

# Сохраняем ID объектов
order_id = None
ticket_id = None
performer_id = None

# Тест создания заказа
with db.session_scope() as session:
    # Тест Order
    new_order = Order(
        user_id=12345,
        order_date="01.01.2025",
        order_time="12:00",
        order_location="Тестовый адрес"
    )
    session.add(new_order)
    session.flush()
    order_id = new_order.id  # Сохраняем ID
    
    # Тест SupportTicket
    new_ticket = SupportTicket(
        user_id=54321,
        message="Тестовая проблема"
    )
    session.add(new_ticket)
    session.flush()
    ticket_id = new_ticket.id  # Сохраняем ID
    
    # Тест Performer (с уникальным ID)
    new_performer = Performer(
        performer_name="Тестовый Исполнитель",
        telegram_user_id=99999  # Уникальное значение
    )
    session.add(new_performer)
    session.flush()
    performer_id = new_performer.id  # Сохраняем ID
    
    print(f"Создан заказ ID: {order_id}")
    print(f"Создано обращение ID: {ticket_id}")
    print(f"Создан исполнитель ID: {performer_id}")

# Проверка после коммита
with db.session_scope() as session:
    # Загружаем объекты по ID из новой сессии
    order = session.get(Order, order_id)
    ticket = session.query(SupportTicket).get(ticket_id)
    performer = session.query(Performer).get(performer_id)
    
    print(f"\nПроверка после коммита:")
    print(f"Заказ {order.id}: {order.order_location}")
    print(f"Обращение {ticket.id}: {ticket.message}")
    print(f"Исполнитель {performer.id}: {performer.performer_name}")

# Дополнительная проверка количества записей
with db.session_scope() as session:
    orders_count = session.query(Order).count()
    tickets_count = session.query(SupportTicket).count()
    performers_count = session.query(Performer).count()
    
    print(f"\nИтоговое количество записей:")
    print(f"Заказов: {orders_count}")
    print(f"Обращений: {tickets_count}")
    print(f"Исполнителей: {performers_count}")

print("\nТест завершен успешно!")
