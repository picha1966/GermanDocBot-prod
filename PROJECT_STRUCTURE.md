
Current Status – 10 March 2026

Main bot:
@CivicAssistBot

Old bot:
@DE_PDF_Assistant_bot deleted.

Current architecture:

Telegram
→ WebApp form
→ Bot receives data
→ Preview PDF
→ Stripe payment
→ Final PDF
→ Termin upsell

Current problem:

After WebApp submit the form closes but the bot does not always receive the payload.

Next debugging step:

1. Check sendData() in WebApp
2. Check server endpoint /webapp-submit
3. Check bot logs for WEB_APP_DATA
