# -*- coding: utf-8 -*-
"""
Eligibility Advisor - модуль аналізу права на додаткові виплати
Аналізує відповіді користувача та рекомендує додаткові документи
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, date
import re


@dataclass
class BenefitRecommendation:
    """Рекомендація щодо виплати"""
    benefit_code: str           # Код виплати (kinderzuschlag, wohngeld, etc.)
    benefit_name: str           # Назва німецькою
    benefit_name_ua: str        # Назва українською
    description_ua: str         # Опис українською
    description_de: str         # Опис німецькою
    estimated_amount: str       # Приблизна сума
    confidence: float           # Впевненість (0.0-1.0)
    requirements_met: List[str] # Які вимоги виконані
    doc_type: str               # Тип документа для оформлення
    priority: int               # Пріоритет (1 = найвищий)


class EligibilityAdvisor:
    """
    Радник з права на виплати
    Аналізує дані користувача та рекомендує додаткові документи
    """
    
    # Межі доходу для різних виплат (EUR на місяць)
    INCOME_THRESHOLDS = {
        'kinderzuschlag_min': 900,     # Мінімальний дохід для Kinderzuschlag
        'kinderzuschlag_max': 4500,    # Максимальний дохід для Kinderzuschlag
        'wohngeld_single': 1400,       # Межа для Wohngeld (одинак)
        'wohngeld_family': 2200,       # Межа для Wohngeld (сім'я)
        'buergergeld_single': 563,     # Bürgergeld для одинака
        'buergergeld_family': 1800,    # Bürgergeld для сім'ї
    }
    
    # Суми виплат
    BENEFIT_AMOUNTS = {
        'kindergeld': {
            1: 250,  # Перша дитина
            2: 250,  # Друга дитина
            3: 250,  # Третя і далі
        },
        'kinderzuschlag': 292,  # Максимум на дитину
        'elterngeld_min': 300,
        'elterngeld_max': 1800,
    }
    
    def __init__(self):
        self.recommendations: List[BenefitRecommendation] = []
    
    def analyze(
        self,
        user_data: dict,
        current_doc_type: str,
        num_children: int = None,
        monthly_income: float = None,
        is_employed: bool = None,
        has_partner: bool = None,
        rent_amount: float = None
    ) -> List[BenefitRecommendation]:
        """
        Аналізує дані та повертає рекомендації
        
        Args:
            user_data: Дані з документа
            current_doc_type: Поточний тип документа
            num_children: Кількість дітей
            monthly_income: Місячний дохід (EUR)
            is_employed: Чи працевлаштований
            has_partner: Чи є партнер
            rent_amount: Сума оренди (EUR)
            
        Returns:
            Список рекомендацій
        """
        self.recommendations = []
        
        # Витягуємо інформацію з user_data
        if num_children is None:
            num_children = self._estimate_children_count(user_data)
        
        # Аналіз для кожного типу виплати
        self._check_kinderzuschlag(current_doc_type, num_children, monthly_income, is_employed)
        self._check_elterngeld(current_doc_type, user_data, num_children)
        self._check_wohngeld(num_children, monthly_income, rent_amount, has_partner)
        self._check_bildungspaket(num_children, monthly_income)
        self._check_unterhaltsvorschuss(user_data, num_children, has_partner)
        
        # Сортуємо за пріоритетом та впевненістю
        self.recommendations.sort(key=lambda x: (x.priority, -x.confidence))
        
        return self.recommendations
    
    def _estimate_children_count(self, user_data: dict) -> int:
        """Оцінити кількість дітей з даних"""
        count = 0
        if user_data.get('child_name'):
            count = 1
        # Можна розширити для підтримки кількох дітей
        return count
    
    def _check_kinderzuschlag(
        self,
        current_doc_type: str,
        num_children: int,
        monthly_income: float = None,
        is_employed: bool = None
    ):
        """
        Перевірка права на Kinderzuschlag
        Додаткова виплата до Kindergeld для сімей з низьким доходом
        """
        # Не пропонуємо якщо вже оформлюють
        if current_doc_type == 'kinderzuschlag':
            return
        
        requirements_met = []
        confidence = 0.0
        
        # Базова умова - є діти
        if num_children and num_children > 0:
            requirements_met.append(f"✓ Є {num_children} дит.")
            confidence += 0.3
        else:
            return  # Немає дітей - не підходить
        
        # Перевірка доходу
        if monthly_income:
            if self.INCOME_THRESHOLDS['kinderzuschlag_min'] <= monthly_income <= self.INCOME_THRESHOLDS['kinderzuschlag_max']:
                requirements_met.append(f"✓ Дохід {monthly_income}€ в межах норми")
                confidence += 0.4
            else:
                confidence -= 0.2
        else:
            # Якщо дохід невідомий, все одно пропонуємо
            confidence += 0.2
        
        # Якщо оформляють Kindergeld - високий шанс
        if current_doc_type == 'kindergeld':
            requirements_met.append("✓ Оформлюєте Kindergeld")
            confidence += 0.2
        
        if confidence >= 0.3:
            max_amount = self.BENEFIT_AMOUNTS['kinderzuschlag'] * num_children
            
            self.recommendations.append(BenefitRecommendation(
                benefit_code='kinderzuschlag',
                benefit_name='Kinderzuschlag',
                benefit_name_ua='Дитяча надбавка',
                description_ua=(
                    f"Додаткова виплата до Kindergeld для сімей з низьким доходом. "
                    f"Ви можете отримувати до {max_amount}€ на місяць додатково!"
                ),
                description_de=(
                    f"Zusätzliche Leistung zum Kindergeld für Familien mit geringem Einkommen. "
                    f"Sie können bis zu {max_amount}€ pro Monat zusätzlich erhalten!"
                ),
                estimated_amount=f"до {max_amount}€/місяць",
                confidence=min(confidence, 1.0),
                requirements_met=requirements_met,
                doc_type='kinderzuschlag',
                priority=1
            ))
    
    def _check_elterngeld(
        self,
        current_doc_type: str,
        user_data: dict,
        num_children: int
    ):
        """
        Перевірка права на Elterngeld (батьківська допомога)
        """
        if current_doc_type == 'elterngeld':
            return
        
        requirements_met = []
        confidence = 0.0
        
        # Перевіряємо чи є немовля (дата народження дитини)
        child_birth_date = user_data.get('child_birth_date')
        if child_birth_date:
            try:
                birth = datetime.strptime(child_birth_date, '%d.%m.%Y')
                age_months = (datetime.now() - birth).days / 30
                
                if age_months <= 14:  # Дитині менше 14 місяців
                    requirements_met.append(f"✓ Дитині {int(age_months)} міс.")
                    confidence += 0.5
                    
                    if age_months <= 2:
                        requirements_met.append("✓ Терміново! Подайте протягом 3 міс.")
                        confidence += 0.3
                else:
                    return  # Занадто пізно
            except:
                pass
        
        if current_doc_type == 'kindergeld' and num_children > 0:
            confidence += 0.3
        
        if confidence >= 0.3:
            self.recommendations.append(BenefitRecommendation(
                benefit_code='elterngeld',
                benefit_name='Elterngeld',
                benefit_name_ua='Батьківська допомога',
                description_ua=(
                    "Виплата для батьків, які доглядають за дитиною до 14 місяців. "
                    "Від 300€ до 1800€ на місяць залежно від попереднього доходу."
                ),
                description_de=(
                    "Leistung für Eltern, die ihr Kind bis zu 14 Monate betreuen. "
                    "Von 300€ bis 1800€ pro Monat je nach vorherigem Einkommen."
                ),
                estimated_amount="300-1800€/місяць",
                confidence=min(confidence, 1.0),
                requirements_met=requirements_met,
                doc_type='elterngeld',
                priority=1
            ))
    
    def _check_wohngeld(
        self,
        num_children: int,
        monthly_income: float = None,
        rent_amount: float = None,
        has_partner: bool = None
    ):
        """
        Перевірка права на Wohngeld (житлова допомога)
        """
        requirements_met = []
        confidence = 0.0
        
        family_size = 1 + (1 if has_partner else 0) + (num_children or 0)
        
        if family_size > 1:
            requirements_met.append(f"✓ Сім'я з {family_size} осіб")
            confidence += 0.2
        
        if monthly_income:
            threshold = self.INCOME_THRESHOLDS['wohngeld_family'] if family_size > 1 else self.INCOME_THRESHOLDS['wohngeld_single']
            if monthly_income <= threshold:
                requirements_met.append(f"✓ Дохід {monthly_income}€ нижче ліміту")
                confidence += 0.4
        
        if rent_amount and rent_amount > 0:
            requirements_met.append(f"✓ Оренда {rent_amount}€/міс")
            confidence += 0.2
        
        if confidence >= 0.3:
            self.recommendations.append(BenefitRecommendation(
                benefit_code='wohngeld',
                benefit_name='Wohngeld',
                benefit_name_ua='Житлова допомога',
                description_ua=(
                    "Допомога на оплату житла для сімей з низьким доходом. "
                    "Сума залежить від доходу, оренди та розміру сім'ї."
                ),
                description_de=(
                    "Wohnkostenhilfe für Familien mit geringem Einkommen. "
                    "Die Höhe hängt von Einkommen, Miete und Familiengröße ab."
                ),
                estimated_amount="50-400€/місяць",
                confidence=min(confidence, 1.0),
                requirements_met=requirements_met,
                doc_type='wohngeld',
                priority=2
            ))
    
    def _check_bildungspaket(
        self,
        num_children: int,
        monthly_income: float = None
    ):
        """
        Перевірка права на Bildungspaket (освітній пакет)
        """
        if not num_children or num_children == 0:
            return
        
        requirements_met = []
        confidence = 0.3  # Базова впевненість якщо є діти
        
        requirements_met.append(f"✓ Є {num_children} дитина(и)")
        
        if monthly_income and monthly_income < 3000:
            requirements_met.append("✓ Дохід дозволяє")
            confidence += 0.3
        
        if confidence >= 0.3:
            self.recommendations.append(BenefitRecommendation(
                benefit_code='bildungspaket',
                benefit_name='Bildungspaket',
                benefit_name_ua='Освітній пакет',
                description_ua=(
                    "Допомога на шкільне приладдя, харчування, екскурсії. "
                    "Для дітей з малозабезпечених сімей."
                ),
                description_de=(
                    "Unterstützung für Schulmaterial, Verpflegung, Ausflüge. "
                    "Für Kinder aus einkommensschwachen Familien."
                ),
                estimated_amount="195€/рік + додатково",
                confidence=min(confidence, 1.0),
                requirements_met=requirements_met,
                doc_type='bildungspaket',
                priority=3
            ))
    
    def _check_unterhaltsvorschuss(
        self,
        user_data: dict,
        num_children: int,
        has_partner: bool = None
    ):
        """
        Перевірка права на Unterhaltsvorschuss (аліменти від держави)
        Для одиноких батьків
        """
        if has_partner:
            return  # Є партнер - не підходить
        
        if not num_children or num_children == 0:
            return
        
        requirements_met = []
        confidence = 0.2
        
        requirements_met.append(f"✓ Є {num_children} дитина(и)")
        
        # Перевіряємо вік дитини
        child_birth_date = user_data.get('child_birth_date')
        if child_birth_date:
            try:
                birth = datetime.strptime(child_birth_date, '%d.%m.%Y')
                age_years = (datetime.now() - birth).days / 365
                
                if age_years < 18:
                    requirements_met.append(f"✓ Дитині {int(age_years)} років")
                    confidence += 0.3
            except:
                pass
        
        if has_partner is False:
            requirements_met.append("✓ Одинокий батько/мати")
            confidence += 0.3
        
        if confidence >= 0.3:
            self.recommendations.append(BenefitRecommendation(
                benefit_code='unterhaltsvorschuss',
                benefit_name='Unterhaltsvorschuss',
                benefit_name_ua='Аліменти від держави',
                description_ua=(
                    "Якщо другий батько не платить аліменти, держава виплачує їх замість нього. "
                    "Для одиноких батьків з дітьми до 18 років."
                ),
                description_de=(
                    "Wenn der andere Elternteil keinen Unterhalt zahlt, springt der Staat ein. "
                    "Für Alleinerziehende mit Kindern bis 18 Jahre."
                ),
                estimated_amount="187-338€/місяць",
                confidence=min(confidence, 1.0),
                requirements_met=requirements_met,
                doc_type='unterhaltsvorschuss',
                priority=2
            ))
    
    def format_recommendations_message(
        self,
        lang: str = 'ua',
        max_recommendations: int = 3
    ) -> Optional[str]:
        """
        Форматувати рекомендації для відправки користувачу
        
        Args:
            lang: Мова (ua, de, en)
            max_recommendations: Максимум рекомендацій
            
        Returns:
            Відформатоване повідомлення або None
        """
        if not self.recommendations:
            return None
        
        top_recs = self.recommendations[:max_recommendations]
        
        if lang == 'de':
            message = "\n\n💡 <b>WICHTIG! Zusätzliche Leistungen für Sie:</b>\n\n"
            message += "Basierend auf Ihren Angaben könnten Sie auch Anspruch auf folgende Leistungen haben:\n\n"
        else:
            message = "\n\n💡 <b>ВАЖЛИВО! Додаткові виплати для вас:</b>\n\n"
            message += "На основі ваших даних ви можете мати право на такі виплати:\n\n"
        
        for i, rec in enumerate(top_recs, 1):
            confidence_stars = "⭐" * min(int(rec.confidence * 5), 5)
            
            if lang == 'de':
                message += (
                    f"<b>{i}. {rec.benefit_name}</b> {confidence_stars}\n"
                    f"💰 {rec.estimated_amount}\n"
                    f"{rec.description_de}\n\n"
                )
            else:
                message += (
                    f"<b>{i}. {rec.benefit_name_ua}</b> ({rec.benefit_name}) {confidence_stars}\n"
                    f"💰 {rec.estimated_amount}\n"
                    f"{rec.description_ua}\n\n"
                )
        
        if lang == 'de':
            message += "\n<i>Möchten Sie einen dieser Anträge ausfüllen?</i>"
        else:
            message += "\n<i>Бажаєте оформити один з цих документів?</i>"
        
        return message
    
    def get_recommendation_keyboard(self, lang: str = 'ua'):
        """
        Генерує клавіатуру з рекомендаціями
        Повертає список кнопок для InlineKeyboardMarkup
        """
        buttons = []
        
        for rec in self.recommendations[:3]:
            if lang == 'de':
                text = f"📝 {rec.benefit_name} beantragen"
            else:
                text = f"📝 Оформити {rec.benefit_name_ua}"
            
            buttons.append({
                'text': text,
                'callback_data': f"doc_{rec.doc_type}"
            })
        
        return buttons


# Глобальний екземпляр
eligibility_advisor = EligibilityAdvisor()
