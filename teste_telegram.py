# teste_telegram.py
from notificador import NotificadorTelegram
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

# Cria o notificador
notificador = NotificadorTelegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)

# Envia mensagem de teste
print("Enviando mensagem de teste...")
sucesso = notificador.enviar_mensagem("🤖 *Bot Trader conectado com sucesso!*")

if sucesso:
    print("✅ Mensagem enviada! Verifique seu Telegram.")
else:
    print("❌ Erro ao enviar. Verifique o token e chat ID.")