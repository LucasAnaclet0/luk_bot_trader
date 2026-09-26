import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

# --- FUNÇÃO AUXILIAR PARA CONVERTER TIPOS ---
def get_env(key, default=None, cast=str):
    """Busca variável no ambiente e converte tipo se necessário"""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return cast(value)
    except ValueError:
        return default

# --- CHAVES SENSÍVEIS (Vêm do .env) ---
BINANCE_API_KEY = os.getenv("BINANCE_API_KEY")
BINANCE_SECRET = os.getenv("BINANCE_SECRET")
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# --- CONFIGURAÇÕES DO BOT ---
SIMBOLO = os.getenv("SIMBOLO", "BTCUSDT")
TEMPO_ENTRE_ANALISES = int(os.getenv("TEMPO_ENTRE_ANALISES", 60))
VALOR_POR_OPERACAO_USDT = float(os.getenv("VALOR_POR_OPERACAO_USDT", 100))
STOP_LOSS_PERCENTUAL = float(os.getenv("STOP_LOSS_PERCENTUAL", -0.006))
TAKE_PROFIT_PERCENTUAL = float(os.getenv("TAKE_PROFIT_PERCENTUAL", 0.018))
SCORE_MINIMO_COMPRA = float(os.getenv("SCORE_MINIMO_COMPRA", 50))
SCORE_MINIMO_VENDA = float(os.getenv("SCORE_MINIMO_VENDA", 50))

# --- FLAGS BOOLEANAS ---
USAR_TESTNET = os.getenv("USAR_TESTNET", "True").lower() == "true"
MODO_TESTE = os.getenv("MODO_TESTE", "True").lower() == "true"
TELEGRAM_ATIVADO = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# --- URL DA API ---
URL_TICKER = "https://api.binance.com/api/v3/ticker/price"

# --- VALIDAÇÃO SEGURA ---
if USAR_TESTNET and not BINANCE_API_KEY:
    print("⚠️ AVISO: BINANCE_API_KEY não encontrada no .env. Bot pode falhar.")