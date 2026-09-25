# analise.py
# Funções de análise de mercado

import requests
from config import SIMBOLO, INTERVALO, LIMITE_CANDLES, URL_KLINES


def buscar_candles():
    """Busca os candles mais recentes da Binance"""
    try:
        params = {
            "symbol": SIMBOLO,
            "interval": INTERVALO,
            "limit": LIMITE_CANDLES
        }
        resposta = requests.get(URL_KLINES, params=params, timeout=10)
        resposta.raise_for_status()
        return resposta.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao buscar candles: {e}")
        return None


def analisar_candles(dados):
    """Analisa os candles e retorna estatísticas"""
    if not dados:
        return None
    
    altas = 0
    baixas = 0
    estaveis = 0   
    soma_variacoes = 0
    soma_volume = 0
    percentual_alta = 0
    percentual_baixa = 0
    volume_acima_media = 0
    volume_abaixo_media = 0

    # Primeiro loop: calcular tudo
    for candle in dados:
        abertura = float(candle[1])
        fechamento = float(candle[4])
        volume = float(candle[5])
        
        soma_volume += volume 

        variacao_percentual = (fechamento - abertura) / abertura * 100
        soma_variacoes += variacao_percentual
        
        if variacao_percentual > percentual_alta:
            percentual_alta = variacao_percentual
        
        if variacao_percentual < percentual_baixa:
            percentual_baixa = variacao_percentual
        
        if fechamento > abertura:  
            altas += 1
        elif fechamento < abertura:   
            baixas += 1
        else:
            estaveis += 1
    
    total = len(dados)
    media_volume = soma_volume / total
    media_variacoes = soma_variacoes / total

    # Segundo loop: analisar volume em relação à média
    for candle in dados:
        volume = float(candle[5])
        if volume > media_volume:
            volume_acima_media += 1
        elif volume < media_volume:
            volume_abaixo_media += 1
    
    return {
        "altas": altas,
        "baixas": baixas,
        "estaveis": estaveis,
        "media_variacoes": media_variacoes,
        "volume_medio": media_volume,
        "percentual_alta": percentual_alta,
        "percentual_baixa": percentual_baixa,
        "volume_acima_media": volume_acima_media,
        "volume_abaixo_media": volume_abaixo_media,
        "total": total
    }


def detectar_tendencia(resultado):
    """Determina a tendência do mercado"""
    if resultado["media_variacoes"] > 0 and resultado["altas"] > resultado["baixas"]:
        return "ALTA"
    elif resultado["media_variacoes"] < 0 and resultado["altas"] < resultado["baixas"]:
        return "BAIXA"
    else:
        return "INDEFINIDA"


def classificar_forca(resultado):
    """Classifica a força da tendência"""
    media = resultado["media_variacoes"]
    
    if media >= 0.1:
        return "FORTE_ALTA"
    elif media > 0:
        return "ALTA"
    elif media < -0.1:
        return "FORTE_BAIXA"
    elif media < 0:
        return "BAIXA"
    else:
        return "ESTAVEL"

def calcular_score(resultado):
    """
    Calcula um score de confiança de 0 a 100
    baseado em vários fatores
    """
    score = 0
    
    # FATOR 1: Tendência (quanto mais clara, melhor)
    tendencia = detectar_tendencia(resultado)
    if tendencia != "INDEFINIDA":
        score += 25  # Base de 25 pontos
    
    # FATOR 2: Força da tendência
    forca = classificar_forca(resultado)
    if forca in ["FORTE_ALTA", "FORTE_BAIXA"]:
        score += 25
    elif forca in ["ALTA", "BAIXA"]:
        score += 15
    
    # FATOR 3: Volume (acima da média confirma movimento)
    if resultado["volume_acima_media"] > resultado["total"] / 2:
        score += 25  # Mais da metade dos candles com volume alto
    
    # FATOR 4: Consistência (mais altas que baixas ou vice-versa)
    total = resultado["total"]
    if tendencia == "ALTA":
        consistencia = resultado["altas"] / total
    elif tendencia == "BAIXA":
        consistencia = resultado["baixas"] / total
    else:
        consistencia = 0.5
    
    score += consistencia * 25  # Até 25 pontos
    
    return round(score, 2)


def gerar_sinal_inteligente(resultado):
    """
    Gera sinal baseado no score de confiança
    Retorna: (sinal, score, explicacao)
    """
    from config import SCORE_MINIMO_COMPRA, SCORE_MINIMO_VENDA
    
    score = calcular_score(resultado)
    tendencia = detectar_tendencia(resultado)
    forca = classificar_forca(resultado)
    
    explicacao = []
    
    # Adiciona explicações
    explicacao.append(f"Tendência: {tendencia}")
    explicacao.append(f"Força: {forca}")
    explicacao.append(f"Score: {score}/100")
    
    # Decisão final
    if tendencia == "ALTA" and score >= SCORE_MINIMO_COMPRA:
        return "COMPRA", score, explicacao
    elif tendencia == "BAIXA" and score >= SCORE_MINIMO_VENDA:
        return "VENDA", score, explicacao
    else:
        return "AGUARDAR", score, explicacao
def gerar_sinal_com_indicadores(resultado, indicadores, dados=None):
    """
    Gera sinal combinando análise de candles + indicadores técnicos.
    
    Args:
        resultado: resultado da análise de candles
        indicadores: resultado dos indicadores técnicos
        dados: dados brutos dos candles (opcional, pra filtro de volatilidade)
    
    Returns:
        tuple: (sinal, score, explicacao)
    """
    from config import SCORE_MINIMO_COMPRA, SCORE_MINIMO_VENDA
    from indicadores import mercado_volatil
    
    score = 0
    explicacao = []
    
    # FATOR 1: Análise de candles (peso 40%)
    score_candles = calcular_score(resultado) * 0.4
    score += score_candles
    explicacao.append(f"Score candles: {score_candles:.1f}")
    
    # FATOR 2: Tendência pelo SMA (peso 20%)
    interpretacao = indicadores.get("interpretacao", {})
    if interpretacao.get("tendencia") == "ALTA":
        score += 20
        explicacao.append("Preço acima da SMA20 (+20)")
    elif interpretacao.get("tendencia") == "BAIXA":
        score += 20
        explicacao.append("Preço abaixo da SMA20 (+20)")
    
    # FATOR 3: RSI (peso 20%)
    rsi_status = interpretacao.get("rsi_status")
    if rsi_status == "SOBREVENDIDO":
        score += 20
        explicacao.append(f"RSI sobrevendido ({indicadores['rsi']}) (+20)")
    elif rsi_status == "SOBRECOMPRADO":
        score += 20
        explicacao.append(f"RSI sobrecomprado ({indicadores['rsi']}) (+20)")
    
    # FATOR 4: Cruzamento de médias (peso 20%)
    cruzamento = interpretacao.get("sinal_cruzamento")
    if cruzamento == "COMPRA":
        score += 20
        explicacao.append("Cruzamento de alta (+20)")
    elif cruzamento == "VENDA":
        score += 20
        explicacao.append("Cruzamento de baixa (+20)")
    
    # Limita score a 100
    score = min(score, 100)
    
    # NOVO: Filtro de volatilidade (AULA 16)
    if dados:
        volatil, atr_pct = mercado_volatil(dados)
        explicacao.append(f"Volatilidade: {atr_pct:.3f}%")
        if not volatil:
            return "AGUARDAR", score, explicacao + ["⚠️ Mercado pouco volátil"]
    
    # Decisão final
    tendencia = detectar_tendencia(resultado)
    
    if tendencia == "ALTA" and score >= SCORE_MINIMO_COMPRA:
        return "COMPRA", score, explicacao
    elif tendencia == "BAIXA" and score >= SCORE_MINIMO_VENDA:
        return "VENDA", score, explicacao
    else:
        return "AGUARDAR", score, explicacao