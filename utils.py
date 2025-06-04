import re
import functools
import logging
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from .config import config

logger = logging.getLogger(__name__)

@functools.lru_cache(maxsize=32)
def create_inline_keyboard_cached(items, prefix, columns, back_button):
    keyboard = []
    row = []
    for i, item in enumerate(items):
        row.append(InlineKeyboardButton(item, callback_data=f"{prefix}_{item}"))
        if (i + 1) % columns == 0:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    if back_button:
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

def create_inline_keyboard(items, prefix, columns=2, back_button=False):
    return create_inline_keyboard_cached(tuple(items), prefix, columns, back_button)

@functools.lru_cache(maxsize=12)
def create_calendar_cached(year, month):
    first_day = datetime(year, month, 1)
    last_day = (first_day + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    
    keyboard = [[
        InlineKeyboardButton("◀️", callback_data=f"{config.CALENDAR_PREV_MONTH_PREFIX}_{year}_{month}"),
        InlineKeyboardButton(first_day.strftime("%B %Y"), callback_data="ignore"),
        InlineKeyboardButton("▶️", callback_data=f"{config.CALENDAR_NEXT_MONTH_PREFIX}_{year}_{month}")
    ]]
    
    weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    keyboard.append([InlineKeyboardButton(day, callback_data="ignore") for day in weekdays])
    
    days = []
    for _ in range(first_day.weekday()):
        days.append(InlineKeyboardButton(" ", callback_data="ignore"))
    
    for day in range(1, last_day.day + 1):
        current_date = datetime(year, month, day)
        if current_date.date() < datetime.now().date():
            days.append(InlineKeyboardButton(" ", callback_data="ignore"))
        else:
            days.append(InlineKeyboardButton(
                str(day), 
                callback_data=f"{config.CALENDAR_SELECT_DAY_PREFIX}_{year}_{month}_{day}"
            ))
        if len(days) % 7 == 0:
            keyboard.append(days)
            days = []
    
    if days:
        keyboard.append(days)
    
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(keyboard)

def create_calendar(year=None, month=None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month
    return create_calendar_cached(year, month)

def validate_date(date_str):
    if not re.match(config.DATE_REGEX, date_str):
        return False
    try:
        day, month, year = map(int, date_str.split('.'))
        input_date = datetime(year, month, day).date()
        return input_date >= datetime.now().date()
    except ValueError:
        return False

def validate_time(date_str, time_str):
    if not re.match(config.TIME_REGEX, time_str):
        return False
    try:
        day, month, year = map(int, date_str.split('.'))
        hours, minutes = map(int, time_str.split(':'))
        input_dt = datetime(year, month, day, hours, minutes)
        return input_dt > datetime.now()
    except ValueError:
        return False

def validate_amount(amount_str):
    return re.match(config.AMOUNT_REGEX, amount_str) is not None

def main_menu_keyboard(is_admin=False):
    buttons = [
        [InlineKeyboardButton("📝 Создать заказ", callback_data="new_order")],
        [InlineKeyboardButton("🛎 Поддержка", callback_data="support")]
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("⚙️ Админ-панель", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def create_time_selection_keyboard():
    buttons = []
    row = []
    for i, time_slot in enumerate(config.TIME_SLOTS):
        row.append(InlineKeyboardButton(time_slot, callback_data=f"time_{time_slot}"))
        if (i + 1) % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("🔙 Назад", callback_data="back")])
    return InlineKeyboardMarkup(buttons)

def validate_date_time_format(dt_str, fmt="%d.%m.%Y %H:%M"):
    try:
        datetime.strptime(dt_str, fmt)
        return True
    except ValueError:
        return False