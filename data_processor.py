import ccxt
import pandas as pd
import talib # Biblioteca padrão da indústria para indicadores técnicos
import time

class DataProcessor:
    def __init__(self):
        # Configurando para usar a Testnet da Binance por segurança
        self.exchange = ccxt.binance({
            'apiKey': 'SUA_API_KEY_TESTNET',
            'secret': 'SUA_SECRET_KEY_TESTNET',
            'enableRateLimit': True,
            'options': {'defaultType': 'future'} # Trabalhando com futuros para alavancagem
        })

    def fetch_ohlcv(self, symbol, timeframe='1h', limit=500):
        """Baixa os candles brutos da exchange"""
        print(f"📥 Baixando dados para {symbol}...")
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"Erro ao buscar dados: {e}")
            return None

    def add_technical_features(self, df):
        """Adiciona 'inteligência' aos dados brutos"""
        if df is None or len(df) < 50:
            return df

        # Indicadores Técnicos Profissionais
        df['RSI'] = talib.RSI(df['close'].values, timeperiod=14)
        df['BB_UPPER'], df['BB_MIDDLE'], df['BB_LOWER'] = talib.BBANDS(df['close'].values, timeperiod=20)
        df['ATR'] = talib.ATR(df['high'].values, df['low'].values, df['close'].values, timeperiod=14)
        
        # Médias Móveis Exponenciais (para identificar tendência)
        df['EMA_9'] = talib.EMA(df['close'].values, timeperiod=9)
        df['EMA_21'] = talib.EMA(df['close'].values, timeperiod=21)

        # Limpeza de dados nulos (as primeiras linhas dos indicadores ficam vazias)
        df.dropna(inplace=True)
        
        return df

# --- Como testar ---
if __name__ == "__main__":
    processor = DataProcessor()
    
    # Vamos testar com BTCUSDT
    raw_data = processor.fetch_ohlcv('BTC/USDT', timeframe='1h')
    
    if raw_data is not None:
        smart_data = processor.add_technical_features(raw_data)
        print("\n🧠 Dados processados com Inteligência Técnica:")
        print(smart_data.tail()) # Mostra as últimas 5 linhas processadas