# config.py
import os
from dotenv import load_dotenv
from dataclasses import dataclass, field
from typing import Dict, List

# Carrega as variáveis do arquivo .env
load_dotenv()

# --- FUNÇÕES AUXILIARES DE SEGURANÇA (PRESERVADAS) ---
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
# 1. CHAVES SENSÍVEIS (Vêm do .env) - ATUALIZADO PARA OKX
# ==========================================
OKX_API_KEY = get_env_str("OKX_API_KEY")
OKX_SECRET = get_env_str("OKX_SECRET")
OKX_PASSPHRASE = get_env_str("OKX_PASSPHRASE")

# Compatibilidade com código antigo que ainda usa "BINANCE"
BINANCE_API_KEY = OKX_API_KEY
BINANCE_SECRET = OKX_SECRET
BINANCE_API_SECRET = OKX_SECRET

TELEGRAM_TOKEN = get_env_str("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = get_env_str("TELEGRAM_CHAT_ID")

# ==========================================
# 2. CONFIGURAÇÕES GERAIS DO BOT - PRESERVADO + EXPANDIDO
# ==========================================
# ATENÇÃO: OKX usa hífen no símbolo (ex: BTC-USDT)
SIMBOLO = get_env_str("SIMBOLO", "BTC-USDT")  
MODO_TESTE = get_env_bool("MODO_TESTE", True)
USAR_TESTNET = get_env_bool("USAR_TESTNET", True)
TEMPO_ENTRE_ANALISES = get_env_int("TEMPO_ENTRE_ANALISES", 60)
TELEGRAM_ATIVADO = bool(TELEGRAM_TOKEN and TELEGRAM_CHAT_ID)

# ===== NOVO: MULTI-CRYPTO WATCHLIST =====
# Pode ser sobrescrito via .env: WATCHLIST_SYMBOLS=BTC-USDT,ETH-USDT,SOL-USDT
_watchlist_env = get_env_str("WATCHLIST_SYMBOLS", "")
if _watchlist_env:
    # Garante que todos os símbolos tenham o formato com hífen (ex: BTC-USDT)
    _symbols = [s.strip().replace("USDT", "-USDT") if not "-" in s else s.strip() for s in _watchlist_env.split(",") if s.strip()]
else:
    _symbols = [
        "BTC-USDT", "ETH-USDT", "SOL-USDT", "LINK-USDT", "AVAX-USDT",
        "DOT-USDT", "MATIC-USDT", "UNI-USDT", "ATOM-USDT", "NEAR-USDT"
    ]

@dataclass(frozen=True)
class WatchlistConfig:
    """Configuração imutável da watchlist - thread-safe"""
    symbols: tuple = tuple(_symbols)
    coingecko_ids: Dict[str, str] = field(default_factory=lambda: {
        "BTC-USDT": "bitcoin", "ETH-USDT": "ethereum", "SOL-USDT": "solana",
        "LINK-USDT": "chainlink", "AVAX-USDT": "avalanche-2", "DOT-USDT": "polkadot",
        "MATIC-USDT": "matic-network", "UNI-USDT": "uniswap", "ATOM-USDT": "cosmos",
        "NEAR-USDT": "near"
    })

WATCHLIST = WatchlistConfig()

# ==========================================
# 3. PARÂMETROS DE TRADING & RISCO - PRESERVADO
# ==========================================
CAPITAL_INICIAL = get_env_float("CAPITAL_INICIAL", 1000.0)
VALOR_POR_OPERACAO_USDT = get_env_float("VALOR_POR_OPERACAO_USDT", 100.0)
RISCO_POR_OPERACAO = get_env_float("RISCO_POR_OPERACAO", 0.02)
STOP_LOSS_PERCENTUAL = get_env_float("STOP_LOSS_PERCENTUAL", -0.02)
TAKE_PROFIT_PERCENTUAL = get_env_float("TAKE_PROFIT_PERCENTUAL", 0.03)
SCORE_MINIMO_COMPRA = get_env_float("SCORE_MINIMO_COMPRA", 50.0)
SCORE_MINIMO_VENDA = get_env_float("SCORE_MINIMO_VENDA", 50.0)
LIMITE_PERDA_DIARIA = get_env_float("LIMITE_PERDA_DIARIA", -0.05)
MAX_OPERACOES_POR_DIA = get_env_int("MAX_OPERACOES_POR_DIA", 10)

# ===== NOVO: PESOS DO SCORE UNIFICADO =====
PESO_TECNICO = get_env_float("PESO_TECNICO", 0.30)
PESO_VOLUME_LIQUIDEZ = get_env_float("PESO_VOLUME_LIQUIDEZ", 0.20)
PESO_SENTIMENTO = get_env_float("PESO_SENTIMENTO", 0.25)
PESO_ONCHAIN_PROXY = get_env_float("PESO_ONCHAIN_PROXY", 0.15)
PESO_EVENTO_RISCO = get_env_float("PESO_EVENTO_RISCO", 0.10)

# Validação automática dos pesos
_total_pesos = PESO_TECNICO + PESO_VOLUME_LIQUIDEZ + PESO_SENTIMENTO + PESO_ONCHAIN_PROXY + PESO_EVENTO_RISCO
if abs(_total_pesos - 1.0) > 0.01:
    print(f"⚠️ AVISO: Pesos do score somam {_total_pesos:.2f} (deveria ser 1.0). Ajuste no .env!")

# ===== NOVO: THRESHOLDS DO SCANNER MULTI-CRYPTO =====
MIN_VOLUME_USD = get_env_float("MIN_VOLUME_USD", 5_000_000)
MAX_SPREAD_PCT = get_env_float("MAX_SPREAD_PCT", 0.15)
COINGECKO_CACHE_TTL = get_env_int("COINGECKO_CACHE_TTL", 300)
CCXT_RATE_LIMIT_MS = get_env_int("CCXT_RATE_LIMIT_MS", 100)

# ==========================================
# 4. DADOS DE MERCADO - ATUALIZADO PARA CCXT
# ==========================================
INTERVALO = get_env_str("INTERVALO", "1m")
LIMITE_CANDLES = get_env_int("LIMITE_CANDLES", 50)
PERIODO_CANDLES = get_env_int("PERIODO_CANDLES", 50)
JANELA_ANALISE = get_env_int("JANELA_ANALISE", 20)

# URLs diretas removidas pois o CCXT gerencia a conexão automaticamente
# e evita bloqueios de IP na VPS (EUA).
URL_BASE = ""
URL_KLINES = ""
URL_TICKER = ""
URL_BALANCE = ""

# ==========================================
# 5. VALIDAÇÃO FINAL (Debug) - EXPANDIDO
# ==========================================
print(f"✅ Config carregado:")
print(f"   Símbolo principal: {SIMBOLO}")
print(f"   Intervalo: {INTERVALO}")
print(f"   Testnet: {USAR_TESTNET}")
print(f"   Telegram Ativado: {TELEGRAM_ATIVADO}")
print(f"   Pesos Score: Tec={PESO_TECNICO:.0%} Vol={PESO_VOLUME_LIQUIDEZ:.0%} "
      f"Sent={PESO_SENTIMENTO:.0%} OnChain={PESO_ONCHAIN_PROXY:.0%} Event={PESO_EVENTO_RISCO:.0%}")

if MODO_TESTE and not OKX_API_KEY:
    print("⚠️ AVISO CRÍTICO: OKX_API_KEY vazia. Verifique seu arquivo .env!")

# Risk management opcional
MAX_POSICOES_ABERTAS = 5
MAX_COMPRAS_POR_CICLO = 1
EXPOSICAO_MAXIMA_USDT = 500.0
COOLDOWN_STOP_MINUTOS = 30
FECHAR_EM_SINAL_VENDA = False
SCORE_ALTO_TESTNET = 75.0