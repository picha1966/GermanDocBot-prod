# -*- coding: utf-8 -*-
"""
Progress Bar Generator - візуальний індикатор прогресу
"""

from typing import Tuple


class ProgressBar:
    """
    Генератор візуального прогрес-бару для Telegram
    """
    
    # Стилі прогрес-барів
    STYLES = {
        'default': ('■', '□'),
        'blocks': ('█', '░'),
        'circles': ('●', '○'),
        'arrows': ('▶', '▷'),
        'stars': ('★', '☆'),
        'hearts': ('❤️', '🤍'),
        'squares': ('🟩', '⬜'),
        'modern': ('━', '─'),
    }
    
    def __init__(self, style: str = 'default', length: int = 10):
        """
        Args:
            style: Стиль прогрес-бару
            length: Довжина прогрес-бару в символах
        """
        self.style = style
        self.length = length
        self.filled_char, self.empty_char = self.STYLES.get(style, self.STYLES['default'])
    
    def generate(
        self,
        current: int,
        total: int,
        show_percentage: bool = True,
        show_fraction: bool = True,
        prefix: str = 'Прогрес',
        suffix: str = ''
    ) -> str:
        """
        Генерує прогрес-бар
        
        Args:
            current: Поточний крок (починаючи з 1)
            total: Загальна кількість кроків
            show_percentage: Показувати відсоток
            show_fraction: Показувати дріб (3/10)
            prefix: Префікс перед прогресом
            suffix: Суфікс після прогресу
            
        Returns:
            Рядок з прогрес-баром
        """
        if total <= 0:
            return ''
        
        # Обчислюємо прогрес
        progress = min(current / total, 1.0)
        filled_length = int(self.length * progress)
        
        # Генеруємо бар
        bar = self.filled_char * filled_length + self.empty_char * (self.length - filled_length)
        
        # Формуємо рядок
        parts = []
        
        if prefix:
            parts.append(prefix + ':')
        
        parts.append(f'[{bar}]')
        
        if show_percentage:
            percentage = int(progress * 100)
            parts.append(f'{percentage}%')
        
        if show_fraction:
            parts.append(f'({current}/{total})')
        
        if suffix:
            parts.append(suffix)
        
        return ' '.join(parts)
    
    def generate_emoji(
        self,
        current: int,
        total: int,
        emoji_filled: str = '🟩',
        emoji_empty: str = '⬜'
    ) -> str:
        """
        Генерує прогрес-бар з емодзі
        """
        if total <= 0:
            return ''
        
        progress = min(current / total, 1.0)
        filled_length = int(self.length * progress)
        
        return emoji_filled * filled_length + emoji_empty * (self.length - filled_length)
    
    def generate_circular(
        self,
        current: int,
        total: int
    ) -> str:
        """
        Генерує круговий індикатор прогресу
        """
        if total <= 0:
            return '⭕'
        
        progress = current / total
        
        if progress <= 0:
            return '⭕'
        elif progress < 0.25:
            return '◔'
        elif progress < 0.5:
            return '◑'
        elif progress < 0.75:
            return '◕'
        elif progress < 1.0:
            return '◕'
        else:
            return '●'
    
    def generate_steps(
        self,
        current: int,
        total: int,
        step_names: list = None
    ) -> str:
        """
        Генерує покроковий індикатор
        
        Args:
            current: Поточний крок
            total: Загальна кількість
            step_names: Назви кроків (опціонально)
            
        Returns:
            Рядок з кроками
        """
        steps = []
        
        for i in range(1, total + 1):
            if i < current:
                steps.append('✅')
            elif i == current:
                steps.append('📝')
            else:
                steps.append('⬜')
        
        return ' '.join(steps)


def create_progress_message(
    current_step: int,
    total_steps: int,
    field_question: str,
    step_number_emoji: str = None,
    lang: str = 'ua',
    style: str = 'blocks'
) -> str:
    """
    Створює повне повідомлення з прогресом для бота
    
    Args:
        current_step: Поточний крок (починаючи з 1)
        total_steps: Загальна кількість кроків
        field_question: Питання для поточного поля
        step_number_emoji: Емодзі номера кроку (наприклад, '1️⃣')
        lang: Мова
        style: Стиль прогрес-бару
        
    Returns:
        Форматоване повідомлення
    """
    pb = ProgressBar(style=style, length=10)
    
    # Генеруємо прогрес-бар
    progress_bar = pb.generate(
        current=current_step,
        total=total_steps,
        show_percentage=True,
        show_fraction=True,
        prefix=''
    )
    
    # Формуємо заголовок прогресу
    if lang == 'de':
        progress_label = 'Fortschritt'
    elif lang == 'en':
        progress_label = 'Progress'
    else:
        progress_label = 'Прогрес'
    
    # Формуємо повідомлення
    if step_number_emoji:
        message = f"{step_number_emoji} <b>{field_question}:</b>\n\n"
    else:
        message = f"<b>{current_step}. {field_question}:</b>\n\n"
    
    message += f"📊 {progress_label}: {progress_bar}"
    
    return message


def get_step_emoji(step: int) -> str:
    """
    Повертає емодзі для номера кроку
    """
    emojis = {
        1: '1️⃣', 2: '2️⃣', 3: '3️⃣', 4: '4️⃣', 5: '5️⃣',
        6: '6️⃣', 7: '7️⃣', 8: '8️⃣', 9: '9️⃣', 10: '🔟'
    }
    return emojis.get(step, f'{step}.')


# Глобальний екземпляр
progress_bar = ProgressBar(style='blocks', length=10)
