# trading.py
# Conexão e ordens na Binance Testnet

from binance.client import Client
from config import BINANCE_API_KEY, BINANCE_API_SECRET


def criar_cliente():
    """Cria a conexão com a Binance Testnet"""
    try:
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)
        client.ping()  # Testa se a conexão está viva
        print("✅ Conectado na Binance Testnet!")
        return client
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return None


def obter_saldo(client, ativo):
    """Mostra o saldo de um ativo (USDT, BTC, etc)"""
    try:
        saldo = client.get_asset_balance(asset=ativo)
        return float(saldo['free'])
    except Exception as e:
        print(f"❌ Erro ao buscar saldo: {e}")
        return 0.0


def obter_preco(client, simbolo="BTCUSDT"):
    """Busca o preço atual"""
    try:
        ticker = client.get_symbol_ticker(symbol=simbolo)
        return float(ticker['price'])
    except Exception as e:
        print(f"❌ Erro ao buscar preço: {e}")
        return 0.0


def comprar_mercado(client, simbolo, valor_usdt):
    """
    Compra a mercado: gasta X USDT comprando a moeda
    Exemplo: comprar_mercado(client, "BTCUSDT", 100) = compra 100 dólares em BTC
    """
    try:
        ordem = client.order_market_buy(symbol=simbolo, quoteOrderQty=valor_usdt)
        print(f"✅ COMPRA executada: {valor_usdt} USDT em {simbolo}")
        return ordem
    except Exception as e:
        print(f"❌ Erro na compra: {e}")
        return None


def vender_mercado(client, simbolo, quantidade):
    """Vende a mercado: vende X quantidade da moeda"""
    try:
        ordem = client.order_market_sell(symbol=simbolo, quantity=quantidade)
        print(f"✅ VENDA executada: {quantidade} {simbolo}")
        return ordem
    except Exception as e:
        print(f"❌ Erro na venda: {e}")
        return None