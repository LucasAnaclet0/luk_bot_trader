# dashboard.py
# Dashboard Web para monitorar o bot - VERSÃO ROBUSTA PARA CLOUD

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import random
import os
import json

# Importa nossas funções
try:
    from analise import buscar_candles, analisar_candles
    from indicadores import analisar_indicadores
    from gerenciador import GerenciadorPosicoes
    from config import SIMBOLO, TEMPO_ENTRE_ANALISES
except ImportError as e:
    st.error(f"Erro ao importar módulos: {e}")
    st.stop()

# Configuração da página
st.set_page_config(
    page_title="Luk Bot Trader",
    page_icon="🤖",
    layout="wide"
)

# Inicializa o gerenciador
if 'gerenciador' not in st.session_state:
    st.session_state.gerenciador = GerenciadorPosicoes()

gerenciador = st.session_state.gerenciador

# --- FUNÇÕES DE DADOS COM FALLBACK ---

def gerar_dados_simulados():
    """Gera candles fake caso a API falhe (para o dashboard não quebrar)"""
    base_price = 84000.0
    data = []
    current_time = int(time.time() * 1000)
    
    for i in range(50):
        open_p = base_price + random.uniform(-50, 50)
        close_p = open_p + random.uniform(-30, 30)
        high_p = max(open_p, close_p) + random.uniform(0, 20)
        low_p = min(open_p, close_p) - random.uniform(0, 20)
        vol = random.uniform(10, 100)
        
        # Formato da Binance Klines: [time, open, high, low, close, volume, ...]
        row = [current_time, str(open_p), str(high_p), str(low_p), str(close_p), str(vol)]
        data.append(row)
        current_time += 60000 # +1 minuto
        
    return data

@st.cache_data(ttl=30)  # Cache por 30 segundos
def carregar_dados_seguros():
    """Tenta API real, cai para simulação se falhar"""
    try:
        # 1. Tenta buscar dados reais
        dados_reais = buscar_candles()
        if dados_reais and len(dados_reais) > 0:
            resultado = analisar_candles(dados_reais)
            indicadores = analisar_indicadores(dados_reais)
            return {
                'dados': dados_reais,
                'resultado': resultado,
                'indicadores': indicadores,
                'timestamp': datetime.now(),
                'modo': 'REAL'
            }
    except Exception as e:
        print(f"Erro na API real: {e}")
    
    # 2. Fallback: Gera dados simulados
    dados_fake = gerar_dados_simulados()
    resultado = analisar_candles(dados_fake)
    indicadores = analisar_indicadores(dados_fake)
    
    return {
        'dados': dados_fake,
        'resultado': resultado,
        'indicadores': indicadores,
        'timestamp': datetime.now(),
        'modo': 'SIMULADO'
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
        name=f'{SIMBOLO}'
    )])
    
    fig.update_layout(
        title=f'Gráfico de Candles - {SIMBOLO}',
        yaxis_title='Preço (USDT)',
        xaxis_title='Tempo',
        height=400,
        xaxis_rangeslider_visible=False
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
        yaxis_title='Volume',
        xaxis_title='Tempo',
        height=300
    )
    
    return fig

# --- INTERFACE ---

# Cabeçalho
st.title("🤖 Luk Bot Trader Dashboard")

# Carrega dados seguros
dados_info = carregar_dados_seguros()

# Banner de status
if dados_info['modo'] == 'SIMULADO':
    st.warning("⚠️ **MODO DEMONSTRAÇÃO:** A API da Binance está bloqueada neste servidor. Exibindo dados simulados.")
else:
    st.success("✅ **CONEXÃO REAL:** Dados vindos diretamente da Binance.")

st.markdown(f"**Monitorando:** {SIMBOLO} | **Atualização:** {TEMPO_ENTRE_ANALISES}s")

# Desempacota os dados
dados = dados_info['dados']
resultado = dados_info['resultado']
indicadores = dados_info['indicadores']

# --- MÉTRICAS PRINCIPAIS ---
st.subheader("📊 Status Atual")

col1, col2, col3, col4 = st.columns(4)

with col1:
    preco_atual = indicadores.get('preco_atual', 0)
    st.metric(
        label="💰 Preço Atual",
        value=f"${preco_atual:,.2f}",
        delta=f"{resultado.get('media_variacoes', 0):+.3f}%"
    )

with col2:
    score_estimado = resultado.get('score', 0) # Assumindo que analisar_candles retorna score ou calculamos aqui
    # Nota: Se sua função analisar_candles não retorna score direto, ajuste aqui.
    # Para segurança, vamos usar a interpretação dos indicadores
    tendencia = indicadores.get('interpretacao', {}).get('tendencia', 'NEUTRA')
    st.metric(
        label="📈 Tendência",
        value=tendencia,
        delta="Alta" if tendencia == 'ALTA' else ("Baixa" if tendencia == 'BAIXA' else "Neutra")
    )

with col3:
    rsi_val = indicadores.get('rsi', 50)
    st.metric(
        label="📊 RSI (14)",
        value=f"{rsi_val:.1f}",
        delta=indicadores.get('interpretacao', {}).get('rsi_status', 'NEUTRO')
    )

with col4:
    st.metric(
        label="💵 Capital (Simulado)",
        value=f"${gerenciador.capital:,.2f}",
        delta=f"${gerenciador.lucro_do_dia:+.2f} hoje"
    )

st.divider()

# --- INDICADORES TÉCNICOS ---
st.subheader("📐 Indicadores Técnicos")

col1, col2, col3 = st.columns(3)

with col1:
    st.write("**SMA 20:**")
    sma = indicadores.get('sma_20')
    if sma:
        st.write(f"${sma:,.2f}")
        if preco_atual > sma:
            st.success("🟢 Preço ACIMA da média (Alta)")
        else:
            st.error("🔴 Preço ABAIXO da média (Baixa)")
    else:
        st.write("N/A")

with col2:
    st.write("**RSI (14):**")
    if rsi_val:
        st.write(f"{rsi_val:.2f}")
        if rsi_val >= 70:
            st.warning("⚠️ SOBRECOMPRADO (pode cair)")
        elif rsi_val <= 30:
            st.info("💡 SOBREVENDIDO (pode subir)")
        else:
            st.write("➡️ Neutro")
    else:
        st.write("N/A")

with col3:
    st.write("**Tendência Geral:**")
    if tendencia == 'ALTA':
        st.success(f"📈 {tendencia}")
    elif tendencia == 'BAIXA':
        st.error(f"📉 {tendencia}")
    else:
        st.write(f"⚖️ {tendencia}")

st.divider()

# --- GRÁFICOS ---
st.subheader("📈 Gráficos")

tab1, tab2 = st.tabs(["Candles", "Volume"])

with tab1:
    fig_candles = criar_grafico_candles(dados)
    st.plotly_chart(fig_candles, use_container_width=True)

with tab2:
    fig_volume = criar_grafico_volume(dados)
    st.plotly_chart(fig_volume, use_container_width=True)

st.divider()

# --- MEMÓRIA DO BOT (HISTÓRICO REAL) ---
st.subheader("💾 Histórico de Operações Reais")

# Tenta ler o arquivo histórico local (se rodar localmente) ou JSON commitado
historico_path = "historico_operacoes.json"

if os.path.exists(historico_path):
    try:
        with open(historico_path, 'r', encoding='utf-8') as f:
            historico = json.load(f)
        
        if historico:
            # Resumo simples
            total_ops = len(historico)
            acertos = sum(1 for op in historico if op.get('lucro_prejuizo', 0) > 0)
            lucro_total = sum(op.get('lucro_prejuizo', 0) for op in historico)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Ops", total_ops)
            c2.metric("Acertos", f"{acertos}/{total_ops}")
            c3.metric("Lucro Total", f"${lucro_total:+.2f}")
            
            # Tabela
            df_hist = pd.DataFrame(historico[-10:]) # Últimas 10
            cols_display = [c for c in ['data', 'tipo', 'preco_entrada', 'preco_saida', 'lucro_prejuizo', 'motivo_fechamento'] if c in df_hist.columns]
            st.dataframe(df_hist[cols_display], use_container_width=True)
        else:
            st.info("Arquivo histórico vazio.")
            
    except Exception as e:
        st.error(f"Erro lendo histórico: {e}")
else:
    st.info("ℹ️ Nenhum arquivo de histórico encontrado. O bot precisa operar primeiro para gerar registros.")

# --- BACKTEST (VISUALIZAÇÃO) ---
st.divider()
st.subheader("🔬 Resultados de Backtest")

backtest_path = "curva_backtest.json"

if os.path.exists(backtest_path):
    try:
        with open(backtest_path, 'r', encoding='utf-8') as f:
            curva = json.load(f)
        
        if isinstance(curva, list) and len(curva) > 0:
            col1, col2 = st.columns(2)
            col1.metric("Capital Inicial", f"${curva[0]:.2f}")
            final_cap = curva[-1]
            pct_change = ((final_cap - curva[0]) / curva[0]) * 100
            col2.metric("Capital Final", f"${final_cap:.2f}", 
                        delta=f"{pct_change:+.2f}%")
            
            fig_capital = go.Figure(data=[go.Scatter(
                y=curva,
                mode="lines",
                name="Capital",
                line=dict(color="green", width=2)
            )])
            fig_capital.update_layout(
                title="Curva de Capital (Backtest)",
                yaxis_title="Capital ($)",
                xaxis_title="Iterações",
                height=350
            )
            st.plotly_chart(fig_capital, use_container_width=True)
        else:
            st.warning("Dados de backtest inválidos.")
            
    except Exception as e:
        st.error(f"Erro carregando backtest: {e}")
else:
    st.info("Rodar `python backtest.py` localmente para gerar a curva de capital.")
    
# --- RODAPÉ ---
st.divider()
st.markdown(f"*Última atualização: {dados_info['timestamp'].strftime('%H:%M:%S')} | Modo: {dados_info['modo']}*")

if st.button("🔄 Forçar Atualização"):
    st.cache_data.clear()
    st.rerun()