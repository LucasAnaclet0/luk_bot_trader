# backtest.py
# Testa a estratégia em dados históricos

import requests
from analise import analisar_candles
from indicadores import analisar_indicadores, calcular_sma, calcular_ema, calcular_rsi, detectar_cruzamento_medias
from config import SIMBOLO, STOP_LOSS_PERCENTUAL, TAKE_PROFIT_PERCENTUAL, SCORE_MINIMO_COMPRA


def baixar_historico(limite=500):
    """Baixa candles históricos da Binance"""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": SIMBOLO, "interval": "1m", "limit": limite}
    
    print(f"📥 Baixando {limite} candles históricos de {SIMBOLO}...")
    try:
        resposta = requests.get(url, params=params, timeout=15)
        resposta.raise_for_status()
        dados = resposta.json()
        print(f"   ✅ {len(dados)} candles carregados!")
        return dados
    except Exception as e:
        print(f"   ❌ Erro: {e}")
        return None


def gerar_sinal_backtest(janela):
    """
    Gera sinal usando EXATAMENTE a mesma lógica do bot,
    mas adaptada pra uma janela histórica.
    """
    resultado = analisar_candles(janela)
    if not resultado:
        return None, 0
    
    # Indicadores na janela
    precos = [float(c[4]) for c in janela]
    indicadores = {
        "preco_atual": precos[-1],
        "sma_20": calcular_sma(precos, 20),
        "ema_9": calcular_ema(precos, 9),
        "ema_21": calcular_ema(precos, 21),
        "rsi": calcular_rsi(precos, 14),
        "cruzamento": detectar_cruzamento_medias(precos)
    }
    indicadores["interpretacao"] = interpretar(indicadores)
    
    # Score combinado (mesma fórmula do bot)
    score = 0
    tendencia = "ALTA" if resultado["media_variacoes"] > 0 and resultado["altas"] > resultado["baixas"] else \
                "BAIXA" if resultado["media_variacoes"] < 0 and resultado["altas"] < resultado["baixas"] else "INDEFINIDA"
    
    # Fator candles (40%)
    score_candles = 0
    if tendencia != "INDEFINIDA": score_candles += 25
    media = resultado["media_variacoes"]
    if abs(media) >= 0.1: score_candles += 25
    elif media != 0: score_candles += 15
    if resultado["volume_acima_media"] > resultado["total"] / 2: score_candles += 25
    consistencia = (resultado["altas"] if tendencia == "ALTA" else resultado["baixas"] if tendencia == "BAIXA" else resultado["total"]/2) / resultado["total"]
    score_candles += consistencia * 25
    score += score_candles * 0.4
    
    # Fator SMA (20%)
    interp = indicadores["interpretacao"]
    if interp.get("tendencia") in ["ALTA", "BAIXA"]: score += 20
    
    # Fator RSI (20%)
    if interp.get("rsi_status") in ["SOBREVENDIDO", "SOBRECOMPRADO"]: score += 20
    
    # Fator cruzamento (20%)
    if interp.get("sinal_cruzamento"): score += 20
    
    score = min(score, 100)
    
    if tendencia == "ALTA" and score >= SCORE_MINIMO_COMPRA:
        return "COMPRA", score
    elif tendencia == "BAIXA" and score >= SCORE_MINIMO_COMPRA:
        return "VENDA", score
    return None, score


def interpretar(indicadores):
    """Mesma interpretação do bot"""
    interp = {"tendencia": "NEUTRA", "rsi_status": "NEUTRO", "sinal_cruzamento": None}
    preco = indicadores["preco_atual"]
    sma = indicadores["sma_20"]
    rsi = indicadores["rsi"]
    
    if sma:
        interp["tendencia"] = "ALTA" if preco > sma else "BAIXA"
    if rsi:
        if rsi >= 70: interp["rsi_status"] = "SOBRECOMPRADO"
        elif rsi <= 30: interp["rsi_status"] = "SOBREVENDIDO"
    if indicadores.get("cruzamento"):
        interp["sinal_cruzamento"] = indicadores["cruzamento"]
    return interp


def rodar_backtest(dados, capital_inicial=1000, valor_operacao=100, janela=50):
    """
    Simula a estratégia candle por candle.
    
    Regras:
    - Só abre COMPRA (spot: não vendemos o que não temos)
    - Fecha por stop loss ou take profit nos candles seguintes
    """
    capital = capital_inicial
    posicao = None      # {"preco": x, "qtd": y, "investido": z}
    operacoes = []
    curva_capital = [capital]
    
    print(f"\n🎞️ Rodando backtest em {len(dados)} candles...")
    
    for i in range(janela, len(dados)):
        janela_atual = dados[i-janela:i]
        preco_atual = float(dados[i][4])
        
        # 1. Se tem posição, verifica stop/take com o preço atual
        if posicao:
            variacao = (preco_atual - posicao["preco"]) / posicao["preco"]
            
            if variacao <= STOP_LOSS_PERCENTUAL:
                lucro = posicao["investido"] * variacao
                capital += posicao["investido"] + lucro
                operacoes.append({"tipo": "STOP_LOSS", "lucro": lucro, "variacao": variacao*100})
                posicao = None
            
            elif variacao >= TAKE_PROFIT_PERCENTUAL:
                lucro = posicao["investido"] * variacao
                capital += posicao["investido"] + lucro
                operacoes.append({"tipo": "TAKE_PROFIT", "lucro": lucro, "variacao": variacao*100})
                posicao = None
        
        # 2. Se não tem posição, busca sinal
        else:
            sinal, score = gerar_sinal_backtest(janela_atual, dados)
            
            if sinal == "COMPRA" and capital >= valor_operacao:
                qtd = valor_operacao / preco_atual
                capital -= valor_operacao
                posicao = {"preco": preco_atual, "qtd": qtd, "investido": valor_operacao}
        
        # Registra capital (com posição aberta, marca a mercado)
        if posicao:
            variacao = (preco_atual - posicao["preco"]) / posicao["preco"]
            capital_marca = capital + posicao["investido"] * (1 + variacao)
            curva_capital.append(capital_marca)
        else:
            curva_capital.append(capital)
    
    # Fecha posição pendente no último preço
    if posicao:
        preco_final = float(dados[-1][4])
        variacao = (preco_final - posicao["preco"]) / posicao["preco"]
        lucro = posicao["investido"] * variacao
        capital += posicao["investido"] + lucro
        operacoes.append({"tipo": "FECHAMENTO_FINAL", "lucro": lucro, "variacao": variacao*100})
    
    return {
        "capital_inicial": capital_inicial,
        "capital_final": capital,
        "operacoes": operacoes,
        "curva_capital": curva_capital
    }


def calcular_drawdown(curva):
    """Calcula a maior queda do capital (risco máximo)"""
    pico = curva[0]
    max_dd = 0
    for valor in curva:
        if valor > pico:
            pico = valor
        dd = (pico - valor) / pico
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def mostrar_resultados(resultado):
    """Mostra o relatório final"""
    ops = resultado["operacoes"]
    capital_i = resultado["capital_inicial"]
    capital_f = resultado["capital_final"]
    lucro_total = capital_f - capital_i
    retorno_pct = (lucro_total / capital_i) * 100
    
    acertos = sum(1 for op in ops if op["lucro"] > 0)
    total = len(ops)
    taxa = (acertos / total * 100) if total > 0 else 0
    
    lucros = [op["lucro"] for op in ops if op["lucro"] > 0]
    prejuizos = [op["lucro"] for op in ops if op["lucro"] <= 0]
    medio_lucro = sum(lucros)/len(lucros) if lucros else 0
    medio_prejuizo = sum(prejuizos)/len(prejuizos) if prejuizos else 0
    
    drawdown = calcular_drawdown(resultado["curva_capital"])
    
    print("\n" + "="*55)
    print("📊 RELATÓRIO DE BACKTEST")
    print("="*55)
    print(f"💵 Capital inicial:   ${capital_i:.2f}")
    print(f"💰 Capital final:     ${capital_f:.2f}")
    print(f"📈 Lucro total:       ${lucro_total:+.2f} ({retorno_pct:+.2f}%)")
    print(f"🔄 Total de operações: {total}")
    print(f"✅ Acertos:           {acertos} ({taxa:.1f}%)")
    print(f"❌ Erros:             {total - acertos}")
    print(f"💚 Lucro médio:       ${medio_lucro:+.2f}")
    print(f"❤️ Prejuízo médio:    ${medio_prejuizo:+.2f}")
    print(f"⚠️ Drawdown máximo:  {drawdown:.2f}%")
    print("="*55)
    
    # Veredito
    if lucro_total > 0 and taxa >= 50:
        print("🟢 VEREDITO: Estratégia LUCRATIVA no período testado!")
    elif lucro_total > 0:
        print("🟡 VEREDITO: Lucrou, mas taxa de acerto baixa (depende de poucos ganhos grandes)")
    else:
        print("🔴 VEREDITO: Estratégia PREJUDICIAL - precisa ajustar parâmetros!")
    
    return resultado


def salvar_curva(resultado):
    """Salva a curva de capital num JSON pro dashboard usar depois"""
    import json
    with open("curva_backtest.json", "w", encoding="utf-8") as f:
        json.dump(resultado["curva_capital"], f)
    print("💾 Curva salva em curva_backtest.json")


if __name__ == "__main__":
    dados = baixar_historico(limite=1000)
    
    if dados:
        resultado = rodar_backtest(dados)
        mostrar_resultados(resultado)
        salvar_curva(resultado)