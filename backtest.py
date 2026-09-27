# backtest.py
# Testa a estratégia em dados históricos com diagnóstico inteligente

import sys
import argparse
import requests
from analise import analisar_candles
from indicadores import calcular_sma, calcular_ema, calcular_rsi, detectar_cruzamento_medias
from config import SIMBOLO, STOP_LOSS_PERCENTUAL, TAKE_PROFIT_PERCENTUAL, SCORE_MINIMO_COMPRA


def baixar_historico(limite=1000):
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


def gerar_sinal_backtest(janela, debug_mode=False):
    """
    Gera sinal usando EXATAMENTE a mesma lógica do bot.
    Retorna: (sinal, score, detalhes_para_debug)
    """
    resultado = analisar_candles(janela)
    if not resultado:
        return None, 0, {}
    
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
    
    # --- CÁLCULO DO SCORE (Idêntico ao main.py) ---
    score = 0
    tendencia = "INDEFINIDA"
    
    if resultado["media_variacoes"] > 0 and resultado["altas"] > resultado["baixas"]:
        tendencia = "ALTA"
    elif resultado["media_variacoes"] < 0 and resultado["altas"] < resultado["baixas"]:
        tendencia = "BAIXA"
    
    # Fator 1: Candles (Peso 40%)
    score_candles = 0
    if tendencia != "INDEFINIDA": 
        score_candles += 25
    
    media = resultado["media_variacoes"]
    if abs(media) >= 0.1: 
        score_candles += 25
    elif media != 0: 
        score_candles += 15
        
    if resultado["volume_acima_media"] > resultado["total"] / 2: 
        score_candles += 25
        
    consistencia = 0.5
    if tendencia == "ALTA":
        consistencia = resultado["altas"] / resultado["total"]
    elif tendencia == "BAIXA":
        consistencia = resultado["baixas"] / resultado["total"]
        
    score_candles += consistencia * 25
    score += score_candles * 0.4
    
    # Fator 2: SMA (Peso 20%)
    interp = indicadores["interpretacao"]
    if interp.get("tendencia") in ["ALTA", "BAIXA"]: 
        score += 20
    
    # Fator 3: RSI (Peso 20%)
    if interp.get("rsi_status") in ["SOBREVENDIDO", "SOBRECOMPRADO"]: 
        score += 20
    
    # Fator 4: Cruzamento (Peso 20%)
    if interp.get("sinal_cruzamento"): 
        score += 20
    
    score = min(score, 100)
    
    # Determina Sinal Final
    sinal_final = None
    if tendencia == "ALTA" and score >= SCORE_MINIMO_COMPRA:
        sinal_final = "COMPRA"
    elif tendencia == "BAIXA" and score >= SCORE_MINIMO_COMPRA:
        sinal_final = "VENDA" # Nota: No spot real ignoramos venda pura, mas aqui registramos p/ análise
        
    detalhes = {
        "tendencia": tendencia,
        "rsi": indicadores['rsi'],
        "sma_trend": interp.get('tendencia'),
        "cross": interp.get('sinal_cruzamento')
    }
    
    return sinal_final, round(score, 2), detalhes


def rodar_backtest(dados, capital_inicial=1000, valor_operacao=100, janela=50, debug=False):
    """
    Simula a estratégia candle por candle.
    Adiciona coleta de estatísticas de score para diagnóstico.
    """
    capital = capital_inicial
    posicao = None      
    operacoes = []
    curva_capital = [capital]
    
    # Estatísticas de diagnóstico
    scores_encontrados = []
    max_score_visto = 0
    sinais_detectados = {"COMPRA": 0, "VENDA": 0, "AGUARDAR": 0}
    
    print(f"\n🎞️ Rodando backtest em {len(dados)} candles...")
    if debug:
        print("🔍 MODO DEBUG ATIVADO: Coletando distribuição de scores...\n")
    
    for i in range(janela, len(dados)):
        janela_atual = dados[i-janela:i]
        preco_atual = float(dados[i][4])
        
        # 1. Gestão de Posição Aberta
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
        
        # 2. Busca de Novo Sinal
        else:
            sinal, score, detalhes = gerar_sinal_backtest(janela_atual, debug)
            
            # Registra histórico de scores para análise posterior
            scores_encontrados.append(score)
            if score > max_score_visto:
                max_score_visto = score
                
            if sinal == "COMPRA":
                sinais_detectados["COMPRA"] += 1
                if capital >= valor_operacao:
                    qtd = valor_operacao / preco_atual
                    capital -= valor_operacao
                    posicao = {"preco": preco_atual, "qtd": qtd, "investido": valor_operacao}
            elif sinal == "VENDA":
                sinais_detectados["VENDA"] += 1
            else:
                sinais_detectados["AGUARDAR"] += 1
        
        # Atualiza Curva de Capital
        if posicao:
            variacao = (preco_atual - posicao["preco"]) / posicao["preco"]
            capital_marca = capital + posicao["investido"] * (1 + variacao)
            curva_capital.append(capital_marca)
        else:
            curva_capital.append(capital)
    
    # Fecha posição pendente no final
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
        "curva_capital": curva_capital,
        "diagnostico": {
            "max_score": max_score_visto,
            "avg_score": sum(scores_encontrados)/len(scores_encontrados) if scores_encontrados else 0,
            "scores_list": scores_encontrados,
            "sinais": sinais_detectados
        }
    }


def mostrar_resultados(resultado, score_minimo_usado):
    """Mostra o relatório final com diagnóstico integrado"""
    ops = resultado["operacoes"]
    diag = resultado["diagnostico"]
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
    
    print("\n" + "="*60)
    print("📊 RELATÓRIO DE BACKTEST & DIAGNÓSTICO")
    print("="*60)
    
    # Performance Financeira
    print(f"💵 Capital inicial:   ${capital_i:.2f}")
    print(f"💰 Capital final:     ${capital_f:.2f}")
    print(f"📈 Lucro total:       ${lucro_total:+.2f} ({retorno_pct:+.2f}%)")
    print(f"⚠️ Drawdown máximo:  {drawdown:.2f}%")
    print("-"*60)
    
    # Operações
    print(f"🔄 Total de operações: {total}")
    print(f"✅ Acertos:           {acertos} ({taxa:.1f}%)")
    print(f"❌ Erros:             {total - acertos}")
    print(f"💚 Lucro médio:       ${medio_lucro:+.2f}")
    print(f"❤️ Prejuízo médio:    ${medio_prejuizo:+.2f}")
    print("-"*60)
    
    # Diagnóstico de Sinais (NOVO!)
    print("🔍 ANÁLISE DE SINAIS GERADOS:")
    print(f"   • Score Mínimo Configurado: {score_minimo_usado}")
    print(f"   • Maior Score Encontrado:   {diag['max_score']:.1f}")
    print(f"   • Média dos Scores:         {diag['avg_score']:.1f}")
    print(f"   • Sinais Compra Detectados: {diag['sinais']['COMPRA']}")
    print(f"   • Sinais Venda Detectados:  {diag['sinais']['VENDA']}")
    print(f"   • Aguardando (Sem sinal):   {diag['sinais']['AGUARDAR']}")
    
    # Veredito Inteligente
    print("="*60)
    if total == 0:
        if diag['max_score'] < score_minimo_usado:
            print(f"🟡 VEREDITO: Nenhuma operação aberta.")
            print(f"   Motivo: O maior score encontrado foi {diag['max_score']:.1f}, abaixo do mínimo {score_minimo_usado}.")
            print(f"   Sugestão: Reduza o SCORE_MINIMO_COMPRA para ~{int(diag['max_score']*0.8)} ou teste outro período.")
        else:
            print("🔴 VEREDITO: Bug Lógico? Score alto mas nenhuma compra.")
    elif lucro_total > 0 and taxa >= 50:
        print("🟢 VEREDITO: Estratégia LUCRATIVA e Consistente!")
    elif lucro_total > 0:
        print("🟡 VEREDITO: Lucrou, mas dependente de poucos ganhos grandes.")
    else:
        print("🔴 VEREDITO: Estratégia PREJUDICIAL neste cenário.")
    print("="*60)
    
    return resultado


def calcular_drawdown(curva):
    pico = curva[0]
    max_dd = 0
    for valor in curva:
        if valor > pico:
            pico = valor
        dd = (pico - valor) / pico
        if dd > max_dd:
            max_dd = dd
    return max_dd * 100


def salvar_curva(resultado):
    import json
    with open("curva_backtest.json", "w", encoding="utf-8") as f:
        json.dump(resultado["curva_capital"], f)
    print("💾 Curva salva em curva_backtest.json")


if __name__ == "__main__":
    # Parser de argumentos para facilitar testes rápidos
    parser = argparse.ArgumentParser(description="Backtester LukBot")
    parser.add_argument("--score", type=int, default=SCORE_MINIMO_COMPRA, help="Score mínimo para operar")
    parser.add_argument("--candles", type=int, default=1000, help="Quantidade de candles históricos")
    args = parser.parse_args()
    
    # Override temporário do score global para este teste
    import config
    original_score = config.SCORE_MINIMO_COMPRA
    config.SCORE_MINIMO_COMPRA = args.score
    
    print(f"⚙️ Configuração do Teste: Score Min={args.score}, Candles={args.candles}")
    
    dados = baixar_historico(limite=args.candles)
    
    if dados:
        resultado = rodar_backtest(dados, debug=True)
        mostrar_resultados(resultado, args.score)
        salvar_curva(resultado)
        
        # Restaura config original (boa prática)
        config.SCORE_MINIMO_COMPRA = original_score