# -*- coding: utf-8 -*-
"""
Inline Calendar Widget для Telegram Bot
Створює інтерактивний календар для вибору дат
"""

import calendar
from datetime import datetime, date, timedelta
from typing import List, Tuple, Optional
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


class CalendarWidget:
    """
    Інтерактивний календар для вибору дат в Telegram
    """
    
    # Назви місяців
    MONTHS_UA = [
        '', 'Січень', 'Лютий', 'Березень', 'Квітень', 'Травень', 'Червень',
        'Липень', 'Серпень', 'Вересень', 'Жовтень', 'Листопад', 'Грудень'
    ]
    MONTHS_DE = [
        '', 'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
        'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
    ]
    MONTHS_EN = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    
    # Дні тижня
    DAYS_UA = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Нд']
    DAYS_DE = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So']
    DAYS_EN = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
    
    def __init__(
        self,
        callback_prefix: str = 'cal',
        min_date: date = None,
        max_date: date = None,
        lang: str = 'ua'
    ):
        """
        Args:
            callback_prefix: Префікс для callback_data
            min_date: Мінімальна дата для вибору
            max_date: Максимальна дата для вибору
            lang: Мова (ua, de, en)
        """
        self.prefix = callback_prefix
        self.min_date = min_date or date(1950, 1, 1)
        self.max_date = max_date or date.today()
        self.lang = lang
    
    def _get_months(self) -> List[str]:
        """Отримати назви місяців для поточної мови"""
        if self.lang == 'de':
            return self.MONTHS_DE
        elif self.lang == 'en':
            return self.MONTHS_EN
        return self.MONTHS_UA
    
    def _get_days(self) -> List[str]:
        """Отримати назви днів для поточної мови"""
        if self.lang == 'de':
            return self.DAYS_DE
        elif self.lang == 'en':
            return self.DAYS_EN
        return self.DAYS_UA
    
    def create_calendar(
        self,
        year: int = None,
        month: int = None,
        field_name: str = 'date'
    ) -> InlineKeyboardMarkup:
        """
        Створити клавіатуру з календарем
        
        Args:
            year: Рік (за замовчуванням поточний)
            month: Місяць (за замовчуванням поточний)
            field_name: Назва поля для callback
            
        Returns:
            InlineKeyboardMarkup з календарем
        """
        today = date.today()
        year = year or today.year
        month = month or today.month
        
        keyboard = []
        months = self._get_months()
        days = self._get_days()
        
        # Заголовок з місяцем і роком
        header = [
            InlineKeyboardButton(
                text='◀️',
                callback_data=f'{self.prefix}:prev:{year}:{month}:{field_name}'
            ),
            InlineKeyboardButton(
                text=f'{months[month]} {year}',
                callback_data=f'{self.prefix}:ignore'
            ),
            InlineKeyboardButton(
                text='▶️',
                callback_data=f'{self.prefix}:next:{year}:{month}:{field_name}'
            ),
        ]
        keyboard.append(header)
        
        # Дні тижня
        week_days = [
            InlineKeyboardButton(text=day, callback_data=f'{self.prefix}:ignore')
            for day in days
        ]
        keyboard.append(week_days)
        
        # Дні місяця
        cal = calendar.monthcalendar(year, month)
        
        for week in cal:
            row = []
            for day in week:
                if day == 0:
                    row.append(InlineKeyboardButton(
                        text=' ',
                        callback_data=f'{self.prefix}:ignore'
                    ))
                else:
                    current_date = date(year, month, day)
                    
                    # Перевіряємо чи дата в допустимому діапазоні
                    if self.min_date <= current_date <= self.max_date:
                        # Виділяємо сьогоднішній день
                        day_text = f'[{day}]' if current_date == today else str(day)
                        row.append(InlineKeyboardButton(
                            text=day_text,
                            callback_data=f'{self.prefix}:day:{year}:{month}:{day}:{field_name}'
                        ))
                    else:
                        # Недоступна дата
                        row.append(InlineKeyboardButton(
                            text='·',
                            callback_data=f'{self.prefix}:ignore'
                        ))
            
            keyboard.append(row)
        
        # Швидкий вибір року (для дати народження)
        year_buttons = []
        
        # Кнопки для швидкого переходу на 10 років
        if year > self.min_date.year + 10:
            year_buttons.append(InlineKeyboardButton(
                text='⏪ -10',
                callback_data=f'{self.prefix}:year:{year-10}:{month}:{field_name}'
            ))
        
        year_buttons.append(InlineKeyboardButton(
            text='📅 Рік',
            callback_data=f'{self.prefix}:select_year:{year}:{month}:{field_name}'
        ))
        
        if year < self.max_date.year - 10:
            year_buttons.append(InlineKeyboardButton(
                text='+10 ⏩',
                callback_data=f'{self.prefix}:year:{year+10}:{month}:{field_name}'
            ))
        
        keyboard.append(year_buttons)
        
        # Кнопка скасування
        keyboard.append([
            InlineKeyboardButton(
                text='❌ Скасувати' if self.lang == 'ua' else 'Abbrechen' if self.lang == 'de' else 'Cancel',
                callback_data=f'{self.prefix}:cancel:{field_name}'
            )
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    def create_year_selector(
        self,
        current_year: int,
        month: int,
        field_name: str = 'date'
    ) -> InlineKeyboardMarkup:
        """
        Створити вибір року
        """
        keyboard = []
        
        # Заголовок
        keyboard.append([
            InlineKeyboardButton(
                text='📅 Виберіть рік' if self.lang == 'ua' else 'Jahr auswählen',
                callback_data=f'{self.prefix}:ignore'
            )
        ])
        
        # Роки по 5 в ряд
        start_year = max(self.min_date.year, current_year - 15)
        end_year = min(self.max_date.year, current_year + 5)
        
        years = list(range(start_year, end_year + 1))
        
        for i in range(0, len(years), 5):
            row = []
            for year in years[i:i+5]:
                text = f'[{year}]' if year == current_year else str(year)
                row.append(InlineKeyboardButton(
                    text=text,
                    callback_data=f'{self.prefix}:year:{year}:{month}:{field_name}'
                ))
            keyboard.append(row)
        
        # Кнопка назад
        keyboard.append([
            InlineKeyboardButton(
                text='◀️ Назад',
                callback_data=f'{self.prefix}:back:{current_year}:{month}:{field_name}'
            )
        ])
        
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    def process_callback(
        self,
        callback_data: str
    ) -> Tuple[str, Optional[dict]]:
        """
        Обробити callback від календаря
        
        Args:
            callback_data: Дані callback
            
        Returns:
            Tuple[action, data]
            action: 'date_selected', 'navigate', 'cancel', 'ignore'
            data: словник з даними або None
        """
        parts = callback_data.split(':')
        
        if len(parts) < 2:
            return 'ignore', None
        
        action = parts[1]
        
        if action == 'ignore':
            return 'ignore', None
        
        elif action == 'cancel':
            field_name = parts[2] if len(parts) > 2 else 'date'
            return 'cancel', {'field_name': field_name}
        
        elif action == 'day':
            # Вибрано дату
            year, month, day, field_name = int(parts[2]), int(parts[3]), int(parts[4]), parts[5]
            selected_date = date(year, month, day)
            return 'date_selected', {
                'date': selected_date,
                'formatted': selected_date.strftime('%d.%m.%Y'),
                'field_name': field_name
            }
        
        elif action in ['prev', 'next', 'year', 'back']:
            year, month = int(parts[2]), int(parts[3])
            field_name = parts[4] if len(parts) > 4 else 'date'
            
            if action == 'prev':
                # Попередній місяць
                if month == 1:
                    year -= 1
                    month = 12
                else:
                    month -= 1
            elif action == 'next':
                # Наступний місяць
                if month == 12:
                    year += 1
                    month = 1
                else:
                    month += 1
            
            return 'navigate', {
                'year': year,
                'month': month,
                'field_name': field_name
            }
        
        elif action == 'select_year':
            year, month = int(parts[2]), int(parts[3])
            field_name = parts[4] if len(parts) > 4 else 'date'
            return 'year_select', {
                'year': year,
                'month': month,
                'field_name': field_name
            }
        
        return 'ignore', None


# Глобальний екземпляр для дати народження
birth_date_calendar = CalendarWidget(
    callback_prefix='birthcal',
    min_date=date(1930, 1, 1),
    max_date=date.today(),
    lang='ua'
)

# Для дати заселення
move_in_calendar = CalendarWidget(
    callback_prefix='movecal',
    min_date=date.today() - timedelta(days=365),  # Рік назад
    max_date=date.today() + timedelta(days=365),  # Рік вперед
    lang='ua'
)

# Для дати народження дитини
child_birth_calendar = CalendarWidget(
    callback_prefix='childcal',
    min_date=date(2000, 1, 1),
    max_date=date.today(),
    lang='ua'
)
