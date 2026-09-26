import os
from dotenv import load_dotenv

# Carrega as variáveis do arquivo .env
load_dotenv()

# --- FUNÇÕES AUXILIARES DE SEGURANÇA ---
def get_env_str(key, default=""):
    return os.getenv(key, default)

def get_env_float(key, default=0.0):
    try:
        return float(os.getenv(key, str(default)))
    except ValueError:
        return default

def get_env_int(key, default=0):
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default

def get_env_bool(key, default=True):
    val = os.getenv(key, str(default)).lower()
    return val in ["true", "1", "yes"]

# ==========================================
# 1. CHAVES SENSÍVEIS (Vêm do .env)
# ==========================================
BINANCE_API_KEY = get_env_str("BINANCE_API_KEY")
BINANCE_SECRET = get_env_str("BINANCE_SECRET")
# Alias para compatibilidade com trading.py antigo
BINANCE_API_SECRET = BINANCE_SECRET 

TELEGRAM_TOKEN = get_env_str("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_env_str("TELEGRAM_CHAT_ID")

# ==========================================
# 2. CONFIGURAÇÕES GERAIS DO BOT
# ==========================================
SIMBOLO = get_env_str("SIMBOLO", "BTCUSDT")
MODO_TESTE = get_env_bool("MODO_TESTE", True)
USAR_TESTNET = get_env_bool("USAR_TESTNET", True)
TEMPO_ENTRE_ANALISES = get_env_int("TEMPO_ENTRE_ANALISES", 60)

# Variável derivada crucial para o main.py
TELEGRAM_ATIVADO = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# ==========================================
# 3. PARÂMETROS DE TRADING & RISCO
# ==========================================
CAPITAL_INICIAL = get_env_float("CAPITAL_INICIAL", 1000.0)
VALOR_POR_OPERACAO_USDT = get_env_float("VALOR_POR_OPERACAO_USDT", 100.0)
RISCO_POR_OPERACAO = get_env_float("RISCO_POR_OPERACAO", 0.02) # 2%
STOP_LOSS_PERCENTUAL = get_env_float("STOP_LOSS_PERCENTUAL", -0.02) # -0.6%
TAKE_PROFIT_PERCENTUAL = get_env_float("TAKE_PROFIT_PERCENTUAL", 0.03) # +1.8%
SCORE_MINIMO_COMPRA = get_env_float("SCORE_MINIMO_COMPRA", 70.0)
SCORE_MINIMO_VENDA = get_env_float("SCORE_MINIMO_VENDA", 70.0)
LIMITE_PERDA_DIARIA = get_env_float("LIMITE_PERDA_DIARIA", -0.05) # -5%
MAX_OPERACOES_POR_DIA = get_env_int("MAX_OPERACOES_POR_DIA", 10)

# ==========================================
# 4. DADOS DE MERCADO (CANDLES/KLINES)
# ==========================================
INTERVALO = get_env_str("INTERVALO", "1m")
LIMITE_CANDLES = get_env_int("LIMITE_CANDLES", 50)
PERIODO_CANDLES = get_env_int("PERIODO_CANDLES", 50)
JANELA_ANALISE = get_env_int("JANELA_ANALISE", 20)

# URLs da API Binance
URL_BASE = "https://testnet.binance.vision" if USAR_TESTNET else "https://api.binance.com"
URL_KLINES = f"{URL_BASE}/api/v3/klines"
URL_TICKER = f"{URL_BASE}/api/v3/ticker/price"
URL_BALANCE = f"{URL_BASE}/api/v3/account"

# ==========================================
# 5. VALIDAÇÃO FINAL (Debug)
# ==========================================
print(f"✅ Config carregado:")
print(f"   Símbolo: {SIMBOLO}")
print(f"   Intervalo: {INTERVALO}")
print(f"   Testnet: {USAR_TESTNET}")
print(f"   Telegram Ativado: {TELEGRAM_ATIVADO}")
if MODO_TESTE and not BINANCE_API_KEY:
    print("⚠️ AVISO CRÍTICO: BINANCE_API_KEY vazia. Verifique seu arquivo .env!")