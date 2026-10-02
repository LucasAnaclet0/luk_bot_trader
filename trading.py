# trading.py
# Conexão e ordens na OKX Testnet via CCXT (Funciona em qualquer IP, incluindo EUA)

import ccxt
import config as cfg


def criar_cliente():
    """Cria a conexão com a OKX Testnet (Demo)"""
    try:
        exchange = ccxt.okx({
            'apiKey': cfg.OKX_API_KEY,
            'secret': cfg.OKX_SECRET,
            'password': cfg.OKX_PASSPHRASE,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',
            }
        })
        
        # Ativa o modo Sandbox (Demo) se USAR_TESTNET for True
        if cfg.USAR_TESTNET:
            exchange.set_sandbox_mode(True)
            
        exchange.load_markets()
        print("✅ Conectado na OKX DEMO (Testnet)!")
        return exchange
    except Exception as e:
        print(f"❌ Erro ao conectar: {e}")
        return None


def obter_saldo(client, ativo):
    """Mostra o saldo de um ativo (USDT, BTC, etc)"""
    try:
        # O CCXT padroniza o retorno do saldo
        balance = client.fetch_balance()
        return float(balance.get(ativo, {}).get('free', 0))
    except Exception as e:
        print(f"❌ Erro ao buscar saldo: {e}")
        return 0.0


def obter_preco(client, simbolo="BTC-USDT"):
    """Busca o preço atual"""
    try:
        ticker = client.fetch_ticker(simbolo)
        return float(ticker['last'])
    except Exception as e:
        print(f"❌ Erro ao buscar preço: {e}")
        return 0.0


def comprar_mercado(client, simbolo, valor_usdt):
    """
    Compra a mercado: gasta X USDT comprando a moeda
    Exemplo: comprar_mercado(client, "BTC-USDT", 100) = compra 100 dólares em BTC
    """
    try:
        # 1. Busca o preço para calcular a quantidade exata
        preco = obter_preco(client, simbolo)
        if preco <= 0:
            print(f"❌ Preço inválido para {simbolo}")
            return None
        
        # 2. Calcula a quantidade
        quantidade = valor_usdt / preco
        
        # 3. Executa a ordem de compra via CCXT
        ordem = client.create_market_order(
            symbol=simbolo,
            type='market',
            side='buy',
            amount=quantidade
        )
        
        print(f"✅ COMPRA executada: {valor_usdt} USDT em {simbolo}")
        return ordem
    except Exception as e:
        print(f"❌ Erro na compra: {e}")
        return None


def vender_mercado(client, simbolo, quantidade):
    """Vende a mercado: vende X quantidade da moeda"""
    try:
        # Executa a ordem de venda via CCXT
        ordem = client.create_market_order(
            symbol=simbolo,
            type='market',
            side='sell',
            amount=quantidade
        )
        print(f"✅ VENDA executada: {quantidade} {simbolo}")
        return ordem
    except Exception as e:
        print(f"❌ Erro na venda: {e}")
        return None