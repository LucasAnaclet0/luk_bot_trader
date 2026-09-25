# main.py
# Arquivo principal - o "cérebro" do bot

import threading
from logger_bot import log_info, log_erro, log_sinal, log_operacao
from datetime import datetime
from gerenciador import GerenciadorPosicoes
from indicadores import analisar_indicadores
from analise import buscar_candles, analisar_candles, gerar_sinal_com_indicadores
from notificador import NotificadorTelegram
from trading import criar_cliente, obter_saldo
from trader_testnet import TraderTestnet
from comandos import ListenerComandos
from memoria import carregar_historico, resumo_historico
from config import (
    SIMBOLO, TEMPO_ENTRE_ANALISES, MODO_TESTE,
    TELEGRAM_ATIVADO, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    USAR_TESTNET, VALOR_POR_OPERACAO_USDT,
    STOP_LOSS_PERCENTUAL, TAKE_PROFIT_PERCENTUAL,
    SCORE_MINIMO_COMPRA, SCORE_MINIMO_VENDA
)

gerenciador = GerenciadorPosicoes()

if TELEGRAM_ATIVADO and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    notificador = NotificadorTelegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
else:
    notificador = None

if USAR_TESTNET:
    client = criar_cliente()
    if client:
        trader = TraderTestnet(client, SIMBOLO, VALOR_POR_OPERACAO_USDT)
        log_info("Conectado na Binance Testnet")
    else:
        trader = None
        log_erro("Falha na testnet. Usando modo simulação.")
else:
    trader = None

# Evento pra o comando /parar desligar o bot na hora
parar_evento = threading.Event()


def mostrar_banner():
    log_info("="*50)
    log_info("🤖 BOT TRADER - INICIANDO")
    log_info("="*50)
    log_info(f"📊 Par: {SIMBOLO}")
    log_info(f"⏱️  Intervalo: {TEMPO_ENTRE_ANALISES} segundos")
    log_info(f"💰 Valor por operação: ${VALOR_POR_OPERACAO_USDT}")
    log_info(f"🌐 Modo: {'TESTNET (ordens reais)' if trader else 'SIMULAÇÃO'}")
    log_info(f"📱 Telegram: {'ATIVADO' if notificador else 'DESATIVADO'}")
    log_info("="*50)


def buscar_preco_atual():
    import requests
    from config import URL_TICKER
    try:
        resposta = requests.get(f"{URL_TICKER}?symbol={SIMBOLO}", timeout=10)
        resposta.raise_for_status()
        return float(resposta.json()["price"])
    except Exception as e:
        log_erro(f"Falha ao buscar preço: {e}")
        return 0


def mostrar_status_testnet():
    usdt = obter_saldo(client, "USDT")
    moeda = SIMBOLO.replace("USDT", "")
    qtd = obter_saldo(client, moeda)
    print(f"\n📊 STATUS TESTNET:")
    print(f"   💵 USDT: {usdt:.2f}")
    print(f"   🪙 {moeda}: {qtd:.6f}")
    if trader.tem_posicao():
        p = trader.posicao
        print(f"   🎯 Posição: {p['quantidade']:.6f} {moeda} @ ${p['preco_entrada']:.2f}")
    else:
        print(f"   ⏸️ Nenhuma posição aberta")


# ===== COMANDOS DO TELEGRAM (AULA 11) =====

def montar_status():
    """Monta a mensagem de /status"""
    if trader:
        usdt = obter_saldo(client, "USDT")
        moeda = SIMBOLO.replace("USDT", "")
        qtd = obter_saldo(client, moeda)
        msg = f"📊 *STATUS DO BOT*\n\n💵 USDT: {usdt:.2f}\n🪙 {moeda}: {qtd:.6f}"
        
        if trader.tem_posicao():
            p = trader.posicao
            msg += (f"\n\n🎯 *Posição aberta:*\n"
                    f"Entrada: ${p['preco_entrada']:.2f}\n"
                    f"Stop: ${p['stop_loss']:.2f}\n"
                    f"Alvo: ${p['take_profit']:.2f}")
        else:
            msg += "\n\n⏸️ Nenhuma posição aberta"
        
        resumo = resumo_historico()
        if resumo:
            msg += (f"\n\n💰 Lucro total: ${resumo['lucro_total']:+.2f}\n"
                    f"📈 Acerto: {resumo['taxa_acerto']:.0f}% "
                    f"({resumo['acertos']}/{resumo['total']})")
        return msg
    return f"💵 Capital (simulação): ${gerenciador.capital:.2f}"


def montar_historico():
    """Monta a mensagem de /historico"""
    historico = carregar_historico()
    if not historico:
        return "📋 Nenhuma operação ainda."
    linhas = []
    for op in historico[-5:]:
        emoji = "🟢" if op["lucro_prejuizo"] > 0 else "🔴"
        linhas.append(f"{emoji} {op['motivo_fechamento']}: ${op['lucro_prejuizo']:+.2f}")
    return "📋 *Últimas operações:*\n" + "\n".join(linhas)


def tratar_comando(texto):
    """Processa os comandos recebidos do Telegram"""
    comando = texto.strip().lower()
    
    if comando == "/status":
        notificador.enviar_mensagem(montar_status())
        log_info("Comando /status executado")
    elif comando == "/historico":
        notificador.enviar_mensagem(montar_historico())
        log_info("Comando /historico executado")
    elif comando == "/parar":
        notificador.enviar_mensagem("🛑 *Encerrando o bot com segurança...*")
        log_info("Comando /parar recebido - encerrando bot")
        parar_evento.set()
    elif comando == "/ajuda":
        notificador.enviar_mensagem(
            "📖 *Comandos disponíveis:*\n"
            "/status - saldo e posição\n"
            "/historico - últimas operações\n"
            "/parar - desligar o bot\n"
            "/ajuda - este menu"
        )
    else:
        notificador.enviar_mensagem("❓ Comando desconhecido. Use /ajuda")


# ===== ANÁLISE =====

def executar_analise():
    print(f"\n🔍 Analisando mercado em {datetime.now().strftime('%H:%M:%S')}...")
    
    dados = buscar_candles()
    if not dados:
        log_erro("Falha ao buscar candles")
        return None
    
    resultado = analisar_candles(dados)
    if not resultado:
        log_erro("Falha na análise de candles")
        return None
    
    indicadores = analisar_indicadores(dados)
    sinal, score, explicacao = gerar_sinal_com_indicadores(resultado, indicadores, dados)
    
    preco_atual = buscar_preco_atual()
    if preco_atual == 0:
        return None
    
    print("\n📊 RESULTADO DA ANÁLISE:")
    print(f"   📈 Altas: {resultado['altas']} | 📉 Baixas: {resultado['baixas']}")
    print(f"   Média variações: {resultado['media_variacoes']:+.3f}%")
    print(f"   Preço atual: ${preco_atual:.2f}")
    
    print("\n📐 INDICADORES TÉCNICOS:")
    if indicadores["sma_20"]: print(f"   SMA20: ${indicadores['sma_20']:.2f}")
    if indicadores["rsi"]: print(f"   RSI:   {indicadores['rsi']}")
    
    interpretacao = indicadores.get("interpretacao", {})
    print("\n🧠 INTERPRETAÇÃO:")
    print(f"   Tendência: {interpretacao.get('tendencia')} | RSI: {interpretacao.get('rsi_status')}")
    
    print(f"\n🎯 SCORE: {score:.1f}/100")
    barra = "█" * int(score / 10) + "░" * (10 - int(score / 10))
    print(f"   [{barra}] {score:.1f}%")
    
    if trader:
        if trader.tem_posicao():
            motivo = trader.verificar_saida(preco_atual)
            if motivo:
                operacao = trader.fechar_venda(motivo)
                if operacao:
                    log_operacao("VENDA", operacao["lucro_prejuizo"], motivo)
                if notificador and operacao:
                    notificador.notificar_posicao_fechada(operacao)
            else:
                variacao = (preco_atual - trader.posicao["preco_entrada"]) / trader.posicao["preco_entrada"] * 100
                print(f"\n   🎯 Posição REAL aberta: {variacao:+.2f}% no momento")
        
        elif sinal == "COMPRA" and score >= SCORE_MINIMO_COMPRA:
            log_sinal("COMPRA", score, preco_atual)
            if notificador:
                notificador.notificar_sinal(sinal, score, preco_atual)
            pos = trader.abrir_compra()
            if pos and notificador:
                notificador.notificar_posicao_aberta(pos)
        
        elif sinal == "VENDA" and score >= SCORE_MINIMO_VENDA:
            log_info(f"Sinal de VENDA sem posição - ignorado (spot)")
        
        else:
            print(f"\n⏸️ Aguardando sinais mais claros...")
    
    else:
        if gerenciador.posicao_aberta:
            deve_fechar, motivo, lucro = gerenciador.verificar_posicao(preco_atual)
            if deve_fechar:
                operacao = gerenciador.fechar_posicao(preco_atual, motivo)
                if operacao:
                    log_operacao("VENDA (sim)", operacao["lucro_prejuizo"], motivo)
                if notificador and operacao:
                    notificador.notificar_posicao_fechada(operacao)
            else:
                print(f"\n   🎯 Posição simulada sendo monitorada...")
        elif (sinal == "COMPRA" and score >= SCORE_MINIMO_COMPRA) or (sinal == "VENDA" and score >= SCORE_MINIMO_VENDA):
            log_sinal(sinal, score, preco_atual)
            if notificador:
                notificador.notificar_sinal(sinal, score, preco_atual)
            posicao = gerenciador.abrir_posicao(sinal, preco_atual)
            if notificador and posicao:
                notificador.notificar_posicao_aberta(posicao)
        else:
            print(f"\n⏸️ Aguardando sinais mais claros...")
    
    return {"sinal": sinal, "score": score, "preco": preco_atual}


def main():
    mostrar_banner()
    
    listener = None
    if notificador:
        notificador.enviar_mensagem(f"🤖 *Bot iniciado!*\n📊 {SIMBOLO} | Modo: {'TESTNET' if trader else 'SIMULAÇÃO'}")
        log_info("Bot iniciado e conectado ao Telegram")
        listener = ListenerComandos(notificador, tratar_comando)
        listener.iniciar()
    
    ciclos = 0
    
    try:
        while not parar_evento.is_set():
            ciclos += 1
            print(f"\n{'─'*50}")
            print(f"🔄 Ciclo #{ciclos}")
            
            executar_analise()
            
            if trader:
                mostrar_status_testnet()
            else:
                gerenciador.mostrar_status()
            
            print(f"\n⏳ Próxima análise em {TEMPO_ENTRE_ANALISES} segundos...")
            parar_evento.wait(TEMPO_ENTRE_ANALISES)
            
    except KeyboardInterrupt:
        log_info("Bot interrompido por Ctrl+C")
    finally:
        if listener:
            listener.parar()
    
    # Resumo final
    log_info("="*50)
    log_info("📊 RESUMO FINAL")
    log_info(f"Ciclos: {ciclos}")
    historico = trader.historico if trader else gerenciador.historico
    log_info(f"Operações na sessão: {len(historico)}")
    log_info("="*50)
    
    if notificador:
        notificador.enviar_mensagem("👋 *Bot desligado.* Até a próxima!")


if __name__ == "__main__":
    main()