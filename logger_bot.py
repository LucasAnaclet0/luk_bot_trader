# logger_bot.py
import logging
from datetime import datetime
import os

# Cria pasta de logs se não existir
os.makedirs("logs", exist_ok=True)

# Configura o logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(message)s',
    datefmt='%d/%m/%Y %H:%M:%S',
    handlers=[
        logging.FileHandler(f"logs/bot_{datetime.now().strftime('%Y%m%d')}.log", encoding='utf-8'),
        logging.StreamHandler()  # Também mostra no terminal
    ]
)

logger = logging.getLogger("BotTrader")

def log_info(msg):
    logger.info(msg)

def log_erro(msg):
    logger.error(msg)

def log_sinal(tipo, score, preco):
    logger.info(f" SINAL {tipo} | Score: {score:.1f} | Preço: ${preco:.2f}")

def log_operacao(tipo, lucro, motivo):
    emoji = "🟢" if lucro > 0 else "🔴"
    logger.info(f"{emoji} {tipo} | ${lucro:+.2f} | {motivo}")