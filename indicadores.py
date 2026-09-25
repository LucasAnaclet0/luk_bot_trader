# indicadores.py
# Indicadores técnicos para análise de mercado


def calcular_sma(precos, periodo):
    """
    SMA = Simple Moving Average (Média Móvel Simples)
    
    Calcula a média dos últimos X preços.
    
    Exemplo com periodo=5:
    Preços: [10, 12, 11, 13, 14]
    SMA = (10+12+11+13+14) / 5 = 12
    
    📖 Pra que serve:
    - Preço ACIMA da média = tendência de alta
    - Preço ABAIXO da média = tendência de baixa
    
    Args:
        precos: lista de preços de fechamento
        periodo: quantos candles usar na média
    
    Returns:
        float: valor da média móvel
    """
    if len(precos) < periodo:
        return None
    
    # Pega os últimos X preços e calcula a média
    ultimos_precos = precos[-periodo:]
    return sum(ultimos_precos) / periodo


def calcular_ema(precos, periodo):
    """
    EMA = Exponential Moving Average (Média Móvel Exponencial)
    
    Parecido com SMA, mas dá MAIS PESO pros preços recentes.
    
    📖 Pra que serve:
    - Reage mais rápido às mudanças de preço
    - Melhor pra detectar tendências novas
    
    Args:
        precos: lista de preços de fechamento
        periodo: quantos candles usar na média
    
    Returns:
        float: valor da média móvel exponencial
    """
    if len(precos) < periodo:
        return None
    
    # Fator de suavização (quanto peso pros preços novos)
    multiplicador = 2 / (periodo + 1)
    
    # Começa com a média simples dos primeiros X preços
    ema = sum(precos[:periodo]) / periodo
    
    # Aplica o fator exponencial pro resto dos preços
    for preco in precos[periodo:]:
        ema = (preco - ema) * multiplicador + ema
    
    return ema


def calcular_rsi(precos, periodo=14):
    """
    RSI = Relative Strength Index (Índice de Força Relativa)
    
    Mede se o ativo tá "sobrecomprado" ou "sobrevendido".
    
    📖 Como funciona:
    - RSI acima de 70 = SOBRECOMPRADO (tá caro, pode cair)
    - RSI abaixo de 30 = SOBREVENDIDO (tá barato, pode subir)
    - RSI entre 30-70 = zona neutra
    
    🧠 Analogia:
    É como um termômetro:
    - 90° = fervendo (vai esfriar = cair)
    - 10° = congelando (vai esquentar = subir)
    
    Args:
        precos: lista de preços de fechamento
        periodo: quantos candles usar (padrão 14)
    
    Returns:
        float: valor do RSI (0 a 100)
    """
    if len(precos) < periodo + 1:
        return None
    
    # Calcula as variações entre candles consecutivos
    variacoes = []
    for i in range(1, len(precos)):
        variacao = precos[i] - precos[i-1]
        variacoes.append(variacao)
    
    # Separa ganhos e perdas
    ganhos = []
    perdas = []
    
    for variacao in variacoes:
        if variacao > 0:
            ganhos.append(variacao)
            perdas.append(0)
        else:
            ganhos.append(0)
            perdas.append(abs(variacao))
    
    # Calcula médias dos ganhos e perdas
    media_ganhos = sum(ganhos[:periodo]) / periodo
    media_perdas = sum(perdas[:periodo]) / periodo
    
    # Aplica suavização exponencial pro resto
    for i in range(periodo, len(ganhos)):
        media_ganhos = (media_ganhos * (periodo - 1) + ganhos[i]) / periodo
        media_perdas = (media_perdas * (periodo - 1) + perdas[i]) / periodo
    
    # Evita divisão por zero
    if media_perdas == 0:
        return 100
    
    # Calcula RS (força relativa)
    rs = media_ganhos / media_perdas
    
    # Calcula RSI
    rsi = 100 - (100 / (1 + rs))
    
    return round(rsi, 2)

def calcular_atr(precos_high, precos_low, precos_close, periodo=14):
    """
    ATR = Average True Range (mede volatilidade)
    
    📖 Pra que serve:
    - ATR alto = mercado volátil (bom pra operar)
    - ATR baixo = mercado parado (evitar)
    """
    if len(precos_close) < periodo + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(precos_close)):
        high_low = precos_high[i] - precos_low[i]
        high_close = abs(precos_high[i] - precos_close[i-1])
        low_close = abs(precos_low[i] - precos_close[i-1])
        true_range = max(high_low, high_close, low_close)
        true_ranges.append(true_range)
    
    atr = sum(true_ranges[:periodo]) / periodo
    for tr in true_ranges[periodo:]:
        atr = (atr * (periodo - 1) + tr) / periodo
    
    return atr


def mercado_volatil(dados, periodo=14, threshold_pct=0.05):
    """
    Verifica se o mercado está volátil o suficiente pra operar.
    
    threshold_pct: 0.05 = 0.05% de movimento médio mínimo
    """
    precos_high = [float(c[2]) for c in dados]
    precos_low = [float(c[3]) for c in dados]
    precos_close = [float(c[4]) for c in dados]
    
    atr = calcular_atr(precos_high, precos_low, precos_close, periodo)
    if not atr or precos_close[-1] == 0:
        return False, 0
    
    atr_pct = (atr / precos_close[-1]) * 100
    return atr_pct >= threshold_pct, atr_pct

def detectar_cruzamento_medias(precos, periodo_curto=9, periodo_longo=21):
    """
    Detecta cruzamento de médias móveis.
    
    📖 Como funciona:
    - Média curta CRUZANDO PRA CIMA da longa = COMPRA 🟢
    - Média curta CRUZANDO PRA BAIXO da longa = VENDA 🔴
    
    🧠 Analogia:
    É como dois carros numa pista:
    - Carro rápido (média curta) ultrapassa o lento = aceleração (compra)
    - Carro rápido fica pra trás = desaceleração (venda)
    
    Args:
        precos: lista de preços de fechamento
        periodo_curto: média rápida (padrão 9)
        periodo_longo: média lenta (padrão 21)
    
    Returns:
        str: "COMPRA", "VENDA" ou None
    """
    if len(precos) < periodo_longo + 1:
        return None
    
    # Calcula médias AGORA
    ema_curta_agora = calcular_ema(precos, periodo_curto)
    ema_longa_agora = calcular_ema(precos, periodo_longo)
    
    # Calcula médias ANTES (sem o último preço)
    precos_anteriores = precos[:-1]
    ema_curta_antes = calcular_ema(precos_anteriores, periodo_curto)
    ema_longa_antes = calcular_ema(precos_anteriores, periodo_longo)
    
    # Verifica se não deu erro
    if None in [ema_curta_agora, ema_longa_agora, ema_curta_antes, ema_longa_antes]:
        return None
    
    # Detecta cruzamento
    if ema_curta_antes <= ema_longa_antes and ema_curta_agora > ema_longa_agora:
        return "COMPRA"  # Cruzou pra cima
    
    if ema_curta_antes >= ema_longa_antes and ema_curta_agora < ema_longa_agora:
        return "VENDA"  # Cruzou pra baixo
    
    return None


def analisar_indicadores(dados):
    """
    Função principal que junta todos os indicadores.
    
    Args:
        dados: lista de candles da Binance
    
    Returns:
        dict: dicionário com todos os indicadores
    """
    # Extrai os preços de fechamento
    precos_fechamento = [float(candle[4]) for candle in dados]
    
    # Calcula indicadores
    resultado = {
        "preco_atual": precos_fechamento[-1] if precos_fechamento else 0,
        "sma_20": calcular_sma(precos_fechamento, 20),
        "ema_9": calcular_ema(precos_fechamento, 9),
        "ema_21": calcular_ema(precos_fechamento, 21),
        "rsi": calcular_rsi(precos_fechamento, 14),
        "cruzamento": detectar_cruzamento_medias(precos_fechamento)
    }
    
    # Interpreta os indicadores
    resultado["interpretacao"] = interpretar_indicadores(resultado)
    
    return resultado


def interpretar_indicadores(indicadores):
    """
    Interpreta os indicadores e gera uma análise textual.
    
    Returns:
        dict: interpretação de cada indicador
    """
    interpretacao = {
        "tendencia": "NEUTRA",
        "rsi_status": "NEUTRO",
        "sinal_cruzamento": None,
        "forca_sinal": 0
    }
    
    preco = indicadores["preco_atual"]
    sma = indicadores["sma_20"]
    rsi = indicadores["rsi"]
    cruzamento = indicadores["cruzamento"]
    
    # Análise de tendência (preço vs SMA)
    if sma:
        if preco > sma:
            interpretacao["tendencia"] = "ALTA"
            interpretacao["forca_sinal"] += 20
        elif preco < sma:
            interpretacao["tendencia"] = "BAIXA"
            interpretacao["forca_sinal"] += 20
    
    # Análise de RSI
    if rsi:
        if rsi >= 70:
            interpretacao["rsi_status"] = "SOBRECOMPRADO"
            interpretacao["forca_sinal"] += 15
        elif rsi <= 30:
            interpretacao["rsi_status"] = "SOBREVENDIDO"
            interpretacao["forca_sinal"] += 15
        else:
            interpretacao["rsi_status"] = "NEUTRO"
    
    # Análise de cruzamento
    if cruzamento:
        interpretacao["sinal_cruzamento"] = cruzamento
        interpretacao["forca_sinal"] += 30
    
    return interpretacao
def calcular_atr(precos_high, precos_low, precos_close, periodo=14):
    """
    ATR = Average True Range (mede volatilidade)
    """
    if len(precos_close) < periodo + 1:
        return None
    
    true_ranges = []
    for i in range(1, len(precos_close)):
        high_low = precos_high[i] - precos_low[i]
        high_close = abs(precos_high[i] - precos_close[i-1])
        low_close = abs(precos_low[i] - precos_close[i-1])
        true_range = max(high_low, high_close, low_close)
        true_ranges.append(true_range)
    
    atr = sum(true_ranges[:periodo]) / periodo
    for tr in true_ranges[periodo:]:
        atr = (atr * (periodo - 1) + tr) / periodo
    
    return atr


def mercado_volatil(dados, periodo=14, threshold_pct=0.05):
    """
    Verifica se o mercado está volátil o suficiente pra operar.
    """
    precos_high = [float(c[2]) for c in dados]
    precos_low = [float(c[3]) for c in dados]
    precos_close = [float(c[4]) for c in dados]
    
    atr = calcular_atr(precos_high, precos_low, precos_close, periodo)
    if not atr or precos_close[-1] == 0:
        return False, 0
    
    atr_pct = (atr / precos_close[-1]) * 100
    return atr_pct >= threshold_pct, atr_pct