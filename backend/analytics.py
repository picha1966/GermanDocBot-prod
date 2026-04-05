# -*- coding: utf-8 -*-
"""
Analytics Module - модуль аналітики для відстеження поведінки користувачів
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
from enum import Enum


class AnalyticsEventType(Enum):
    """Типи аналітичних подій"""
    # User lifecycle
    USER_START = 'user_start'
    USER_RETURN = 'user_return'
    GDPR_CONSENT = 'gdpr_consent'
    GDPR_DECLINE = 'gdpr_decline'
    
    # Document funnel
    DOC_SELECTED = 'doc_selected'
    FIELD_STARTED = 'field_started'
    FIELD_COMPLETED = 'field_completed'
    FIELD_ERROR = 'field_error'
    FORM_COMPLETED = 'form_completed'
    FORM_ABANDONED = 'form_abandoned'
    DRAFT_SAVED = 'draft_saved'
    DRAFT_RESTORED = 'draft_restored'
    
    # Payment funnel
    PAYMENT_INITIATED = 'payment_initiated'
    PAYMENT_SUCCESS = 'payment_success'
    PAYMENT_FAILED = 'payment_failed'
    PAYMENT_CANCELLED = 'payment_cancelled'
    
    # Document delivery
    PDF_GENERATED = 'pdf_generated'
    PDF_ERROR = 'pdf_error'
    DOC_DOWNLOADED = 'doc_downloaded'
    
    # Features
    PROMO_APPLIED = 'promo_applied'
    PROMO_INVALID = 'promo_invalid'
    REFERRAL_USED = 'referral_used'
    FAMILY_DATA_REUSED = 'family_data_reused'
    ADVISOR_SHOWN = 'advisor_shown'
    ADVISOR_CLICKED = 'advisor_clicked'


@dataclass
class AnalyticsEvent:
    """Аналітична подія"""
    event_type: AnalyticsEventType
    user_id: int
    doc_type: Optional[str] = None
    step_name: Optional[str] = None
    event_data: Optional[Dict] = None
    timestamp: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            'event_type': self.event_type.value,
            'user_id': self.user_id,
            'doc_type': self.doc_type,
            'step_name': self.step_name,
            'event_data': self.event_data or {},
            'timestamp': self.timestamp or datetime.now().isoformat()
        }


class AnalyticsTracker:
    """
    Трекер аналітики для відстеження воронки та поведінки користувачів
    """
    
    def __init__(self, db=None):
        """
        Args:
            db: Екземпляр Database для збереження подій
        """
        self.db = db
    
    def track(
        self,
        event_type: AnalyticsEventType,
        user_id: int,
        doc_type: str = None,
        step_name: str = None,
        event_data: dict = None
    ):
        """
        Відстежити подію
        
        Args:
            event_type: Тип події
            user_id: ID користувача
            doc_type: Тип документа (опціонально)
            step_name: Назва кроку (опціонально)
            event_data: Додаткові дані (опціонально)
        """
        if self.db:
            self.db.log_analytics_event(
                user_id=user_id,
                event_type=event_type.value,
                event_data=event_data,
                doc_type=doc_type,
                step_name=step_name
            )
    
    # ==================== SHORTCUT METHODS ====================
    
    def track_user_start(self, user_id: int, is_new: bool = True, referral_code: str = None):
        """Відстежити старт користувача"""
        self.track(
            AnalyticsEventType.USER_START if is_new else AnalyticsEventType.USER_RETURN,
            user_id,
            event_data={'is_new': is_new, 'referral_code': referral_code}
        )
    
    def track_doc_selected(self, user_id: int, doc_type: str):
        """Відстежити вибір документа"""
        self.track(
            AnalyticsEventType.DOC_SELECTED,
            user_id,
            doc_type=doc_type
        )
    
    def track_field_progress(
        self,
        user_id: int,
        doc_type: str,
        field_name: str,
        field_index: int,
        total_fields: int,
        is_completed: bool = True,
        error: str = None
    ):
        """Відстежити прогрес заповнення поля"""
        event_type = AnalyticsEventType.FIELD_COMPLETED if is_completed else AnalyticsEventType.FIELD_ERROR
        
        self.track(
            event_type,
            user_id,
            doc_type=doc_type,
            step_name=field_name,
            event_data={
                'field_index': field_index,
                'total_fields': total_fields,
                'progress': round((field_index / total_fields) * 100, 1),
                'error': error
            }
        )
    
    def track_form_completed(self, user_id: int, doc_type: str, fields_count: int):
        """Відстежити завершення форми"""
        self.track(
            AnalyticsEventType.FORM_COMPLETED,
            user_id,
            doc_type=doc_type,
            event_data={'fields_count': fields_count}
        )
    
    def track_payment(
        self,
        user_id: int,
        doc_type: str,
        status: str,
        amount: float = None,
        order_id: int = None
    ):
        """Відстежити статус оплати"""
        event_map = {
            'initiated': AnalyticsEventType.PAYMENT_INITIATED,
            'success': AnalyticsEventType.PAYMENT_SUCCESS,
            'failed': AnalyticsEventType.PAYMENT_FAILED,
            'cancelled': AnalyticsEventType.PAYMENT_CANCELLED
        }
        
        event_type = event_map.get(status, AnalyticsEventType.PAYMENT_INITIATED)
        
        self.track(
            event_type,
            user_id,
            doc_type=doc_type,
            event_data={'amount': amount, 'order_id': order_id}
        )
    
    def track_promo_usage(self, user_id: int, promo_code: str, is_valid: bool, discount: float = None):
        """Відстежити використання промокоду"""
        self.track(
            AnalyticsEventType.PROMO_APPLIED if is_valid else AnalyticsEventType.PROMO_INVALID,
            user_id,
            event_data={'promo_code': promo_code, 'discount': discount}
        )
    
    # ==================== REPORTING ====================
    
    def get_funnel_report(self, doc_type: str = None, days: int = 7) -> Dict:
        """
        Отримати звіт по воронці
        
        Returns:
            Словник зі статистикою воронки
        """
        if not self.db:
            return {}
        
        stats = self.db.get_funnel_stats(doc_type=doc_type, days=days)
        
        # Обчислюємо конверсії
        total_starts = stats.get('doc_selected', 0)
        form_completed = stats.get('form_completed', 0)
        payment_init = stats.get('payment_initiated', 0)
        payment_success = stats.get('payment_success', 0)
        
        return {
            'period_days': days,
            'doc_type': doc_type or 'all',
            'funnel': {
                'doc_selected': total_starts,
                'form_completed': form_completed,
                'payment_initiated': payment_init,
                'payment_success': payment_success,
            },
            'conversions': {
                'form_completion_rate': round((form_completed / total_starts * 100) if total_starts > 0 else 0, 1),
                'payment_initiation_rate': round((payment_init / form_completed * 100) if form_completed > 0 else 0, 1),
                'payment_success_rate': round((payment_success / payment_init * 100) if payment_init > 0 else 0, 1),
                'overall_conversion': round((payment_success / total_starts * 100) if total_starts > 0 else 0, 1)
            },
            'raw_stats': stats
        }
    
    def format_funnel_message(self, doc_type: str = None, days: int = 7, lang: str = 'ua') -> str:
        """
        Форматувати звіт воронки для Telegram
        """
        report = self.get_funnel_report(doc_type=doc_type, days=days)
        
        if not report:
            return "❌ Немає даних для звіту" if lang == 'ua' else "❌ Keine Daten verfügbar"
        
        funnel = report['funnel']
        conv = report['conversions']
        
        if lang == 'ua':
            message = f"""
📊 <b>АНАЛІТИКА ВОРОНКИ</b>
{'═' * 30}
📅 Період: {days} днів
📄 Документ: {doc_type or 'Всі'}

<b>ВОРОНКА:</b>
1️⃣ Вибрано документ: {funnel['doc_selected']}
2️⃣ Заповнено форму: {funnel['form_completed']} ({conv['form_completion_rate']}%)
3️⃣ Ініційовано оплату: {funnel['payment_initiated']} ({conv['payment_initiation_rate']}%)
4️⃣ Успішна оплата: {funnel['payment_success']} ({conv['payment_success_rate']}%)

<b>КОНВЕРСІЯ:</b>
🎯 Загальна: {conv['overall_conversion']}%

{'═' * 30}
"""
        else:
            message = f"""
📊 <b>FUNNEL ANALYTICS</b>
{'═' * 30}
📅 Zeitraum: {days} Tage
📄 Dokument: {doc_type or 'Alle'}

<b>FUNNEL:</b>
1️⃣ Dokument ausgewählt: {funnel['doc_selected']}
2️⃣ Formular ausgefüllt: {funnel['form_completed']} ({conv['form_completion_rate']}%)
3️⃣ Zahlung initiiert: {funnel['payment_initiated']} ({conv['payment_initiation_rate']}%)
4️⃣ Zahlung erfolgreich: {funnel['payment_success']} ({conv['payment_success_rate']}%)

<b>CONVERSION:</b>
🎯 Gesamt: {conv['overall_conversion']}%

{'═' * 30}
"""
        
        return message


# Глобальний екземпляр (буде ініціалізовано з db в bot.py)
analytics = AnalyticsTracker()
