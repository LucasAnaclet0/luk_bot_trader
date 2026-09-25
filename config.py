# config.py
# Arquivo de configurações do bot

# === CONFIGURAÇÕES DA BINANCE ===
SIMBOLO = "BTCUSDT"              # Par que vamos operar
INTERVALO = "1m"                  # Intervalo dos candles (1 minuto)
LIMITE_CANDLES = 50               # Quantos candles analisar

# === CONFIGURAÇÕES DO BOT ===
TEMPO_ENTRE_ANALISES = 60         # Segundos entre cada análise
MODO_TESTE = True                 # True = não executa ordens reais

# === LIMITES DE RISCO (vamos usar depois) ===
CAPITAL_INICIAL = 1000            # USD (simulado)
RISCO_POR_OPERACAO = 0.02         # 2% do capital por trade
STOP_LOSS_PERCENTUAL = -0.006     # -2% (sai da operação se cair 2%)
TAKE_PROFIT_PERCENTUAL = 0.018     # +3% (sai da operação se subir 3%)

# === URLs DA API ===
URL_BASE = "https://api.binance.com/api/v3"
URL_KLINES = f"{URL_BASE}/klines"
URL_TICKER = f"{URL_BASE}/ticker/price"

# Usamos letras MAIÚSCULAS pra constantes (valores que não mudam durante o programa)
# Assim você não precisa caçar números perdidos no código

# === CONFIGURAÇÕES DE SINAIS (AULA 2) ===
SCORE_MINIMO_COMPRA = 50      # Score mínimo pra gerar sinal de COMPRA
SCORE_MINIMO_VENDA = 50       # Score mínimo pra gerar sinal de VENDA

# Pesos de cada indicador (quanto cada um influencia)
PESOS = {
    "tendencia": 0.3,           # 30% de peso
    "forca": 0.25,              # 25% de peso
    "volume": 0.25,             # 25% de peso
    "consistencia": 0.20        # 20% de peso
}
# === LIMITE DIÁRIO (AULA 3) ===
LIMITE_PERDA_DIARIA = 50          # Se perder $50 no dia, para de operar

# === CONFIGURAÇÕES DO TELEGRAM (AULA 5) ===
TELEGRAM_ATIVADO = True                    # True = envia notificações
TELEGRAM_TOKEN = "8704023216:AAEHyaxVPXWdwjjeOf6e5tLgS0xIWZQL2ic"         # ← COLE SEU TOKEN AQUI
TELEGRAM_CHAT_ID = "8736929823"      # ← COLE SEU ID AQUI

# === BINANCE TESTNET (AULA 7) ===
BINANCE_API_KEY = "CTZRh5UnzAYfvz4wFaViw493u7G85KYGLKzlgii6mD8cLUj3VKj3UIdLZtXQcaA6"
BINANCE_API_SECRET = "HrWpbBi9V401Sf1EADtZmy69SeIzaTWNSbR4XmONKdDOZaA378LYCpAec0s6gWHe"

# === MODO TESTNET (AULA 8) ===
USAR_TESTNET = True                  # True = ordens reais na testnet
VALOR_POR_OPERACAO_USDT = 100        # Quanto USDT usar por compra