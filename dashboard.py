# dashboard.py
# Dashboard Web para monitorar o bot

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time

# Importa nossas funções
from analise import buscar_candles, analisar_candles
from indicadores import analisar_indicadores
from gerenciador import GerenciadorPosicoes
from config import SIMBOLO, TEMPO_ENTRE_ANALISES

# Configuração da página
st.set_page_config(
    page_title="Bot Trader Dashboard",
    page_icon="🤖",
    layout="wide"
)

# Inicializa o gerenciador
if 'gerenciador' not in st.session_state:
    st.session_state.gerenciador = GerenciadorPosicoes()

gerenciador = st.session_state.gerenciador

# --- FUNÇÕES DE DADOS ---

@st.cache_data(ttl=30)  # Cache por 30 segundos
def carregar_dados():
    """Carrega e analisa dados do mercado"""
    dados = buscar_candles()
    if not dados:
        return None
    
    resultado = analisar_candles(dados)
    indicadores = analisar_indicadores(dados)
    
    return {
        'dados': dados,
        'resultado': resultado,
        'indicadores': indicadores,
        'timestamp': datetime.now()
    }

def criar_grafico_candles(dados):
    """Cria gráfico de candlestick"""
    df = pd.DataFrame(dados, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    # Converte tipos
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)
    
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'],
        high=df['high'],
        low=df['low'],
        close=df['close'],
        name='BTC/USDT'
    )])
    
    fig.update_layout(
        title=f'Gráfico de Candles - {SIMBOLO}',
        yaxis_title='Preço (USDT)',
        xaxis_title='Tempo',
        height=400
    )
    
    return fig

def criar_grafico_volume(dados):
    """Cria gráfico de volume"""
    df = pd.DataFrame(dados, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['volume'] = df['volume'].astype(float)
    
    fig = go.Figure(data=[go.Bar(
        x=df['timestamp'],
        y=df['volume'],
        name='Volume'
    )])
    
    fig.update_layout(
        title='Volume de Negociação',
        yaxis_title='Volume (BTC)',
        xaxis_title='Tempo',
        height=300
    )
    
    return fig

# --- INTERFACE ---

# Cabeçalho
st.title("🤖 Bot Trader Dashboard")
st.markdown(f"**Monitorando:** {SIMBOLO} | **Atualização:** {TEMPO_ENTRE_ANALISES}s")

# Carrega dados
dados = carregar_dados()

if dados is None:
    st.error("❌ Erro ao carregar dados da API. Verifique sua conexão.")
    st.stop()

resultado = dados['resultado']
indicadores = dados['indicadores']

# --- MÉTRICAS PRINCIPAIS ---
st.subheader("📊 Status Atual")

col1, col2, col3, col4 = st.columns(4)

with col1:
    preco_atual = indicadores['preco_atual']
    st.metric(
        label="💰 Preço Atual",
        value=f"${preco_atual:,.2f}",
        delta=f"{resultado['media_variacoes']:+.3f}%"
    )

with col2:
    st.metric(
        label="📈 Score de Confiança",
        value=f"{indicadores['interpretacao']['forca_sinal']}/100",
        delta="Alta" if indicadores['interpretacao']['tendencia'] == 'ALTA' else "Baixa"
    )

with col3:
    st.metric(
        label="📊 RSI",
        value=f"{indicadores['rsi']:.1f}",
        delta=indicadores['interpretacao']['rsi_status']
    )

with col4:
    st.metric(
        label="💵 Capital",
        value=f"${gerenciador.capital:,.2f}",
        delta=f"${gerenciador.lucro_do_dia:+.2f} hoje"
    )

st.divider()

# --- INDICADORES TÉCNICOS ---
st.subheader("📐 Indicadores Técnicos")

col1, col2, col3 = st.columns(3)

with col1:
    st.write("**SMA 20:**")
    if indicadores['sma_20']:
        st.write(f"${indicadores['sma_20']:,.2f}")
        if preco_atual > indicadores['sma_20']:
            st.success("🟢 Preço ACIMA da média (Alta)")
        else:
            st.error("🔴 Preço ABAIXO da média (Baixa)")
    else:
        st.write("N/A")

with col2:
    st.write("**RSI (14):**")
    if indicadores['rsi']:
        st.write(f"{indicadores['rsi']:.2f}")
        if indicadores['rsi'] >= 70:
            st.warning("⚠️ SOBRECOMPRADO (pode cair)")
        elif indicadores['rsi'] <= 30:
            st.info("💡 SOBREVENDIDO (pode subir)")
        else:
            st.write("➡️ Neutro")
    else:
        st.write("N/A")

with col3:
    st.write("**Tendência:**")
    tendencia = indicadores['interpretacao']['tendencia']
    if tendencia == 'ALTA':
        st.success(f"📈 {tendencia}")
    elif tendencia == 'BAIXA':
        st.error(f"📉 {tendencia}")
    else:
        st.write(f"⚖️ {tendencia}")

st.divider()

# --- ANÁLISE DE CANDLES ---
st.subheader("🕯️ Análise de Candles")

col1, col2, col3 = st.columns(3)

with col1:
    st.write(f"**Altas:** {resultado['altas']}")
    st.progress(resultado['altas'] / resultado['total'])

with col2:
    st.write(f"**Baixas:** {resultado['baixas']}")
    st.progress(resultado['baixas'] / resultado['total'])

with col3:
    st.write(f"**Estáveis:** {resultado['estaveis']}")
    st.progress(resultado['estaveis'] / resultado['total'])

st.divider()

# --- GRÁFICOS ---
st.subheader("📈 Gráficos")

tab1, tab2 = st.tabs(["Candles", "Volume"])

with tab1:
    fig_candles = criar_grafico_candles(dados['dados'])
    st.plotly_chart(fig_candles, use_container_width=True)

with tab2:
    fig_volume = criar_grafico_volume(dados['dados'])
    st.plotly_chart(fig_volume, use_container_width=True)

st.divider()

# --- STATUS DO GERENCIADOR ---
st.subheader("🎯 Status de Operações")

if gerenciador.posicao_aberta:
    st.warning("⚠️ POSIÇÃO ABERTA")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.write(f"**Tipo:** {gerenciador.posicao_aberta['tipo']}")
    with col2:
        st.write(f"**Entrada:** ${gerenciador.posicao_aberta['preco_entrada']:,.2f}")
    with col3:
        st.write(f"**Valor:** ${gerenciador.posicao_aberta['valor_investido']:,.2f}")
else:
    st.info("ℹ️ Nenhuma posição aberta no momento")

if gerenciador.historico:
    st.write("**Últimas Operações:**")
    df_hist = pd.DataFrame(gerenciador.historico[-10:])
    st.dataframe(df_hist, use_container_width=True)

# --- MEMÓRIA DO BOT (AULA 9) ---
st.divider()
st.subheader("💾 Operações do Bot")

from memoria import carregar_historico, resumo_historico

historico = carregar_historico()

if historico:
    resumo = resumo_historico()
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Operações", resumo["total"])
    col2.metric("Acertos", resumo["acertos"])
    col3.metric("Taxa de acerto", f"{resumo['taxa_acerto']:.1f}%")
    col4.metric("Lucro acumulado", f"${resumo['lucro_total']:+.2f}")
    
    # Curva de lucro acumulado
    acumulado = []
    total_acum = 0
    for op in historico:
        total_acum += op["lucro_prejuizo"]
        acumulado.append(total_acum)
    
    fig_pnl = go.Figure(data=[go.Scatter(
        y=acumulado,
        mode="lines+markers",
        name="Lucro acumulado"
    )])
    fig_pnl.update_layout(title="Curva de Lucro Acumulado", height=300)
    st.plotly_chart(fig_pnl, use_container_width=True)
    
    # Tabela de operações
    df_ops = pd.DataFrame(historico)
    colunas = ["data", "tipo", "preco_entrada", "preco_saida", "lucro_prejuizo", "motivo_fechamento"]
    colunas = [c for c in colunas if c in df_ops.columns]
    st.dataframe(df_ops[colunas], use_container_width=True)
else:
    st.info("Nenhuma operação registrada ainda. Quando o bot executar ordens, elas aparecem aqui!")
# --- BACKTEST (AULA 15) ---
st.divider()
st.subheader("🔬 Backtest")

import json
import os

if os.path.exists("curva_backtest.json"):
    with open("curva_backtest.json", "r") as f:
        curva = json.load(f)
    
    col1, col2 = st.columns(2)
    col1.metric("Capital Inicial", f"${curva[0]:.2f}")
    col2.metric("Capital Final", f"${curva[-1]:.2f}", 
                delta=f"{((curva[-1]-curva[0])/curva[0]*100):+.2f}%")
    
    fig_capital = go.Figure(data=[go.Scatter(
        y=curva,
        mode="lines",
        name="Capital",
        line=dict(color="green", width=2)
    )])
    fig_capital.update_layout(
        title="Curva de Capital (Backtest)",
        yaxis_title="Capital ($)",
        xaxis_title="Candles",
        height=350
    )
    st.plotly_chart(fig_capital, use_container_width=True)
else:
    st.info("Rodar `python backtest.py` primeiro para gerar a curva.")
    
# --- RODAPÉ ---
st.divider()
st.markdown(f"*Última atualização: {dados['timestamp'].strftime('%H:%M:%S')}*")

# Botão de atualização
if st.button("🔄 Atualizar Agora"):
    st.cache_data.clear()
    st.rerun()