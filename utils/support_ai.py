# -*- coding: utf-8 -*-
"""
utils/support_ai.py — GPT-powered support assistant for the Telegram bot.

Answers user questions about PDF documents, Termin monitoring, pricing, and
how the service works. Does NOT access Stripe, FSM states, or personal data.
"""

import os
import logging

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are AI Support Assistant for a Telegram bot that helps immigrants in Germany.

Your job is to answer ONLY about:
- German PDF documents (Anmeldung, Ummeldung, Wohnungsgeberbestätigung, Kindergeld, Wohngeld, Bürgergeld, Aufenthaltstitel)
- How to fill them correctly and avoid common rejection reasons
- Termin (appointment) monitoring — finding appointments at Bürgeramt, Ausländerbehörde, Familienkasse, Jobcenter
- Pricing: PDF documents cost €3.99–€12.99 depending on document type. Termin monitoring costs €4.99/24h. Priority Boost costs €1.99. Extend 24h costs €2.99.
- How the bot service works step by step

Important rules:
- Always explain how the user can do something INSIDE the bot — give step-by-step instructions
- Never say "I cannot provide information about this"
- Never redirect to human support unless the question is completely unrelated to documents or Termin
- Never give legal advice or immigration legal opinions
- Keep answers short, friendly, and practical (4–8 sentences max)

How to use the bot (reference these steps when answering):
- PDF documents: tap a document category in the main menu → select a document → fill the WebApp form → pay → receive filled PDF example
- Termin monitoring: tap "Termin" in the main menu → select city → choose authority → start monitoring (€4.99/24h) → get notified when a slot appears
- Priority Boost (€1.99): increases slot detection chance to 60%
- Extend monitoring (€2.99): adds another 24h to active monitoring
- AI Support: the current chat — ask any question about documents or Termin

Example answer for "How to find Termin?":
To find an appointment (Termin), go to the main menu and tap "Appointment (Termin)".
Then select your city (e.g. Berlin), choose the authority (e.g. Bürgeramt or Ausländerbehörde),
and start monitoring for €4.99. The bot will notify you as soon as a slot becomes available.
You can also activate Priority Boost (€1.99) to increase your chances.
"""


async def ask_support_ai_doc(question: str, doc_type: str) -> str:
    """Ask GPT a question in the context of a specific German document.

    The system prompt focuses the model on the exact document so answers are
    specific (field explanations, rejection reasons, submission steps) rather
    than generic bot-usage help.
    """
    doc_prompt = (
        f"User asks about the German bureaucratic document: {doc_type}.\n"
        "Answer in the user's language (detect it from the question).\n"
        "Structure every answer as:\n"
        "• Причина / Reason — why this matters\n"
        "• Що робити / What to do — concrete step-by-step action\n"
        "• Приклад / Example — one short real-world example\n\n"
        "Rules:\n"
        "- Max 5 sentences total\n"
        "- No legal advice\n"
        "- No jargon — plain language\n"
        "- If question is unrelated to this document, politely redirect back\n"
    )
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": doc_prompt},
                {"role": "user", "content": question},
            ],
            max_tokens=400,
            temperature=0.3,
        )
        answer = completion.choices[0].message.content
        logger.info("DOC_AI_OK: doc_type=%s question_len=%s answer_len=%s", doc_type, len(question), len(answer))
        return answer

    except Exception as e:
        logger.error("DOC_AI_ERROR: doc_type=%s err=%s", doc_type, e)
        return (
            "⚠️ I couldn't process your question right now.\n"
            "Please try again in a moment."
        )


async def ask_support_ai(question: str) -> str:
    """Send a user question to GPT and return the assistant's reply."""
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        completion = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=600,
            temperature=0.3,
        )
        answer = completion.choices[0].message.content
        logger.info("SUPPORT_AI_OK: question_len=%s answer_len=%s", len(question), len(answer))
        return answer

    except Exception as e:
        logger.error("SUPPORT_AI_ERROR: %s", e)
        return (
            "⚠️ Sorry, I couldn't process your question right now.\n"
            "Please try again in a moment or contact our support team."
        )
