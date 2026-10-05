# trading.py
# Conexão e ordens na OKX Testnet via CCXT (Funciona em qualquer IP, incluindo EUA)

import ccxt
import config as cfg
from logger_bot import log_info, log_erro

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
    """Compra a mercado gastando X USDT"""
    try:
        # Obtém preço atual para calcular quantidade
        ticker = client.fetch_ticker(simbolo)
        preco = float(ticker['last'])
        if preco <= 0: 
            return None
            
        quantidade = valor_usdt / preco
        
        # CORREÇÃO: amount=qtd NÃO recebe 'type'. 
        # Apenas symbol, side e amount.
        ordem = client.amount=qtd(
            symbol=simbolo,
            side='buy',
            amount=quantidade
        )
        
        log_info(f"✅ COMPRA executada: {valor_usdt} USDT em {simbolo}")
        return ordem
        
    except Exception as e:
        log_erro(f"❌ Erro na compra: {e}")
        return None

def vender_mercado(client, simbolo, quantidade):
    """Vende a mercado X quantidade da moeda, com confirmacao robusta (fetch_order)."""
    import time
    try:
        # GUARDIAO DE POEIRA: valida quantidade antes de enviar
        try:
            qtd = float(client.amount_to_precision(simbolo, float(quantidade)))
            _mkt = client.market(simbolo)
            _min = float(((_mkt.get('limits') or {}).get('amount') or {}).get('min') or 0)
            if qtd <= 0 or (_min and qtd < _min):
                log_erro(f"❌ Venda abortada: {qtd} {simbolo} abaixo do mínimo {_min}")
                return None
        except Exception as e:
            log_erro(f"⚠️ Falha ao validar quantidade: {e}")
            qtd = float(quantidade)

        log_info(f"📤 Enviando venda: {qtd} {simbolo}")

        # CORRECAO CRITICA: create_order padrao CCXT (nao create_market_order)
        ordem = client.create_order(
            symbol=simbolo,
            type='market',
            side='sell',
            amount=qtd
        )

        if not ordem or not ordem.get('id'):
            log_erro(f"❌ Venda sem ID de ordem: {simbolo}")
            return None

        # CONFIRMACAO: loop fetch_order ate filled > 0 (igual ao lado da compra)
        ordem_final = ordem
        for i in range(5):
            status = str(ordem_final.get('status', '')).lower()
            filled = float(ordem_final.get('filled') or 0.0)

            if status == 'closed' and filled > 0:
                break
            if status in ('canceled', 'cancelled', 'rejected', 'expired'):
                log_erro(f"❌ Venda cancelada/rejeitada: {simbolo} ({status})")
                return None

            time.sleep(1.0)
            try:
                ordem_final = client.fetch_order(ordem['id'], simbolo)
            except Exception as e:
                log_erro(f"⚠️ Falha ao consultar venda ({i+1}/5): {e}")

        filled = float(ordem_final.get('filled') or 0.0)
        if filled <= 0:
            log_erro(f"❌ Venda NAO confirmada (filled=0): {simbolo}")
            return None

        log_info(f"✅ VENDA CONFIRMADA: {filled} {simbolo}")
        return ordem_final

    except Exception as e:
        log_erro(f"❌ Erro na venda: {e}")
        return None