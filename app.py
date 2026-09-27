# dashboard.py
# Dashboard Web para monitorar o bot - VERSÃO ULTRA-ROBUSTA PARA CLOUD

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import time
import random
import os
import json

# --- TENTATIVA DE IMPORT COM FALLBACK SEGURO ---
try:
    from analise import buscar_candles, analisar_candles
    from indicadores import analisar_indicadores
    # Tenta importar config, mas se der erro (ex: dotenv faltando no cloud), ignora
    try:
        from config import SIMBOLO, TEMPO_ENTRE_ANALISES
    except ImportError:
        SIMBOLO = "BTCUSDT"
        TEMPO_ENTRE_ANALISES = 60
except ImportError as e:
    st.error(f"Erro ao importar módulos principais: {e}")
    st.stop()

# Configuração da página
st.set_page_config(
    page_title="Luk Bot Trader",
    page_icon="🤖",
    layout="wide"
)

# --- FUNÇÕES DE DADOS COM FALLBACK INTELIGENTE ---

def gerar_dados_simulados():
    """Gera candles fake realistas caso a API falhe"""
    base_price = 84000.0
    data = []
    current_time = int(time.time() * 1000)
    
    for i in range(50):
        open_p = base_price + random.uniform(-50, 50)
        close_p = open_p + random.uniform(-30, 30)
        high_p = max(open_p, close_p) + random.uniform(0, 20)
        low_p = min(open_p, close_p) - random.uniform(0, 20)
        vol = random.uniform(10, 100)
        
        # Formato simplificado: [time, open, high, low, close, volume]
        row = [current_time, str(open_p), str(high_p), str(low_p), str(close_p), str(vol)]
        data.append(row)
        current_time += 60000 
        
    return data

@st.cache_data(ttl=30)
def carregar_dados_seguros():
    """Tenta API real, cai para simulação se falhar"""
    modo = 'SIMULADO'
    dados_reais = None
    
    try:
        # 1. Tenta buscar dados reais
        if 'buscar_candles' in globals():
            dados_reais = buscar_candles()
            
        if dados_reais and len(dados_reais) > 0:
            resultado = analisar_candles(dados_reais)
            indicadores = analisar_indicadores(dados_reais)
            modo = 'REAL'
            return {
                'dados': dados_reais,
                'resultado': resultado,
                'indicadores': indicadores,
                'timestamp': datetime.now(),
                'modo': modo
            }
    except Exception as e:
        print(f"⚠️ Falha na API real ({e}). Usando simulação.")
    
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
    """Cria gráfico de candles adaptativo e seguro"""
    if not dados or len(dados) == 0:
        return None
    
    try:
        num_cols = len(dados[0])
        
        # Define colunas dinamicamente
        if num_cols >= 12:
            columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                       'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
                       'taker_buy_quote', 'ignore'][:num_cols]
        elif num_cols >= 6:
            columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume'][:num_cols]
        else:
            return None

        df = pd.DataFrame(dados, columns=columns)
        
        # Validação Numérica
        required_cols = ['open', 'high', 'low', 'close']
        for col in required_cols:
            if col not in df.columns:
                return None
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        df.dropna(subset=required_cols, inplace=True)
        
        if df.empty:
            return None

        # Eixo X
        if 'timestamp' in df.columns:
            x_axis = pd.to_datetime(df['timestamp'], unit='ms')
        else:
            x_axis = range(len(df))

        fig = go.Figure(data=[go.Candlestick(
            x=x_axis,
            open=df['open'],
            high=df['high'],
            low=df['low'],
            close=df['close'],
            name='Price',
            increasing_line_color='#26a69a',
            decreasing_line_color='#ef5350'
        )])
        
        fig.update_layout(
            title=f"📈 Candlestick Chart - {SIMBOLO}",
            yaxis_title="Preço ($)",
            template="plotly_dark",
            height=400,
            xaxis_rangeslider_visible=False,
            margin=dict(l=20, r=20, t=40, b=20)
        )
        
        return fig
        
    except Exception as e:
        st.error(f"❌ Erro ao processar candles: {str(e)}")
        return None

def criar_gauge_score(score):
    """Cria um medidor visual para o Score"""
    fig = go.Figure(go.Indicator(
        mode = "gauge+number",
        value = score,
        domain = {'x': [0, 1], 'y': [0, 1]},
        title = {'text': "Confiança do Sinal"},
        gauge = {
            'axis': {'range': [None, 100]},
            'bar': {'color': "#ffffff"},
            'steps': [
                {'range': [0, 50], 'color': "#f7b7c2"},
                {'range': [50, 70], 'color': "#ffdac1"},
                {'range': [70, 100], 'color': "#b5ead7"}],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': 70}
        }
    ))
    fig.update_layout(height=250, margin=dict(l=20, r=20, t=20, b=20), paper_bgcolor="#1e1e1e", font={'color': "white"})
    return fig

# --- INTERFACE PRINCIPAL ---

st.title("🤖 Luk Bot Trader Dashboard")

# Carrega dados seguros
dados_info = carregar_dados_seguros()

# Banner de status
if dados_info['modo'] == 'SIMULADO':
    st.warning("⚠️ **MODO DEMONSTRAÇÃO:** A API da Binance está bloqueada neste servidor. Exibindo dados simulados para fins visuais.")
else:
    st.success("✅ **CONEXÃO REAL:** Dados vindos diretamente da Binance.")

st.markdown(f"**Monitorando:** `{SIMBOLO}` | **Intervalo:** `{TEMPO_ENTRE_ANALISES}s`")

# Desempacota os dados
dados = dados_info['dados']
resultado = dados_info['resultado']
indicadores = dados_info['indicadores']

# --- MÉTRICAS PRINCIPAIS ---
st.subheader("📊 Status Atual")

col1, col2, col3, col4 = st.columns(4)

with col1:
    preco_atual = indicadores.get('preco_atual', 0)
    delta_preco = resultado.get('media_variacoes', 0)
    st.metric(label="💰 Preço Atual", value=f"${preco_atual:,.2f}", delta=f"{delta_preco:+.3f}%")

with col2:
    tendencia = indicadores.get('interpretacao', {}).get('tendencia', 'NEUTRA')
    emoji_tend = "" if tendencia == 'ALTA' else ("🔴" if tendencia == 'BAIXA' else "⚪")
    st.metric(label="📈 Tendência", value=f"{emoji_tend} {tendencia}")

with col3:
    rsi_val = indicadores.get('rsi', 50)
    rsi_status = indicadores.get('interpretacao', {}).get('rsi_status', 'NEUTRO')
    st.metric(label="📊 RSI (14)", value=f"{rsi_val:.1f}", delta=rsi_status)

with col4:
    # Calcula score aproximado baseado nos indicadores atuais para o gauge
    # Nota: No backtest real usamos a lógica completa. Aqui é uma estimativa visual rápida.
    score_estimado = 0
    if tendencia != 'NEUTRA': score_estimado += 40
    if rsi_status in ['SOBREVENDIDO', 'SOBRECOMPRADO']: score_estimado += 30
    if indicadores.get('cruzamento'): score_estimado += 30
    score_estimado = min(score_estimado, 100)
    
    st.metric(label="🎯 Score Estimado", value=f"{score_estimado}/100")

st.divider()

# --- GAUGE VISUAL DO SCORE ---
col_gauge, col_text = st.columns([1, 2])
with col_gauge:
    fig_gauge = criar_gauge_score(score_estimado)
    st.plotly_chart(fig_gauge, use_container_width=True)

with col_text:
    st.write("**Interpretação:**")
    if score_estimado >= 70:
        st.success("🟢 **SINAL FORTE:** Condições favoráveis para entrada.")
    elif score_estimado >= 50:
        st.warning("🟡 **ATENÇÃO:** Mercado incerto. Aguardar confirmação.")
    else:
        st.error("🔴 **EVITAR:** Baixa confiança ou tendência indefinida.")
    
    st.caption(f"*Baseado em Tendência, RSI e Cruzamentos.*")

st.divider()

# --- GRÁFICOS ---
st.subheader("📈 Gráficos de Mercado")

tab1, tab2 = st.tabs(["Candles", "Volume"])

with tab1:
    fig_candles = criar_grafico_candles(dados)
    if fig_candles:
        st.plotly_chart(fig_candles, use_container_width=True)
    else:
        st.info("Sem dados suficientes para desenhar candles.")

with tab2:
    # Lógica Adaptativa para Volume
    if dados and len(dados) > 0:
        num_cols = len(dados[0])
        
        # Define as colunas corretamente baseado no tamanho dos dados
        if num_cols >= 12:
            # Formato completo da Binance (usa só as primeiras 6 para o gráfico)
            full_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 
                            'close_time', 'quote_volume', 'trades', 'taker_buy_base', 
                            'taker_buy_quote', 'ignore']
            df_vol = pd.DataFrame(dados, columns=full_columns[:num_cols])
        elif num_cols >= 6:
            # Formato simplificado
            simple_columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
            df_vol = pd.DataFrame(dados, columns=simple_columns[:num_cols])
        else:
            st.info("Dados insuficientes para volume.")
            df_vol = None

        if df_vol is not None and 'volume' in df_vol.columns:
            # Converte tipos para garantir que plotem
            df_vol['volume'] = pd.to_numeric(df_vol['volume'], errors='coerce')
            
            # Garante que o timestamp exista e converta
            if 'timestamp' in df_vol.columns:
                df_vol['timestamp'] = pd.to_datetime(df_vol['timestamp'], unit='ms')
            else:
                # Fallback se não tiver timestamp (não deveria acontecer com dados reais/fakes bem feitos)
                df_vol['timestamp'] = range(len(df_vol))

            fig_vol = go.Figure(data=[go.Bar(
                x=df_vol['timestamp'], 
                y=df_vol['volume'], 
                marker_color='#8884d8',
                name='Volume'
            )])
            
            fig_vol.update_layout(
                title='📊 Volume de Negociação', 
                template="plotly_dark", 
                height=300,
                margin=dict(l=20, r=20, t=40, b=20)
            )
            st.plotly_chart(fig_vol, use_container_width=True)
        else:
            st.info("Coluna de volume não encontrada nos dados.")
    else:
        st.info("Sem dados de volume disponíveis.")

st.divider()

# --- HISTÓRICO LOCAL (SE EXISTIR) ---
st.subheader("💾 Histórico de Operações (Local)")

historico_path = "historico_operacoes.json"

if os.path.exists(historico_path):
    try:
        with open(historico_path, 'r', encoding='utf-8') as f:
            historico = json.load(f)
        
        if historico:
            total_ops = len(historico)
            acertos = sum(1 for op in historico if op.get('lucro_prejuizo', 0) > 0)
            lucro_total = sum(op.get('lucro_prejuizo', 0) for op in historico)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Ops", total_ops)
            c2.metric("Taxa Acerto", f"{(acertos/total_ops*100):.1f}%")
            c3.metric("Lucro Total", f"${lucro_total:+.2f}")
            
            df_hist = pd.DataFrame(historico[-10:])
            cols_display = [c for c in ['data', 'tipo', 'preco_entrada', 'preco_saida', 'lucro_prejuizo', 'motivo_fechamento'] if c in df_hist.columns]
            st.dataframe(df_hist[cols_display], use_container_width=True)
        else:
            st.info("Arquivo histórico vazio.")
            
    except Exception as e:
        st.error(f"Erro lendo histórico: {e}")
else:
    st.info("ℹ️ Nenhum arquivo de histórico encontrado. Execute o bot localmente para gerar registros.")

# --- RODAPÉ ---
st.divider()
st.markdown(f"*Última atualização: {dados_info['timestamp'].strftime('%H:%M:%S')} | Modo: {dados_info['modo']}*")

if st.button("🔄 Forçar Atualização"):
    st.cache_data.clear()
    st.rerun()