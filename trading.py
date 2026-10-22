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
    """Retorna o saldo livre; None indica falha na consulta."""
    try:
        balance = client.fetch_balance()
        return float(balance.get(ativo, {}).get('free', 0))
    except Exception as e:
        print(f"❌ Erro ao buscar saldo de {ativo}: {e}")
        return None


def obter_preco(client, simbolo="BTC-USDT"):
    """Busca o preço atual"""
    try:
        ticker = client.fetch_ticker(simbolo)
        return float(ticker['last'])
    except Exception as e:
        print(f"❌ Erro ao buscar preço: {e}")
        return 0.0

def _confirmar_ordem(client, simbolo, ordem, lado):
    """
    Confirma uma ordem sem reutilizar dados antigos após falha de consulta.
    Retorna a ordem somente quando o status final é closed e filled > 0.
    Retorna None quando não é possível confirmar com segurança.
    """
    import time

    if not isinstance(ordem, dict) or not ordem.get("id"):
        log_erro(f"❌ {lado}: resposta sem ID de ordem para {simbolo}.")
        return None

    ordem_id = ordem["id"]
    ordem_atual = ordem

    for tentativa in range(6):
        status = str(ordem_atual.get("status") or "").lower()
        try:
            filled = float(ordem_atual.get("filled") or 0.0)
        except (TypeError, ValueError):
            filled = 0.0

        if status == "closed":
            if filled > 0:
                log_info(f"✅ {lado} confirmada: {filled} {simbolo}")
                return ordem_atual
            log_erro(f"❌ {lado} encerrada sem quantidade executada: {simbolo}")
            return None

        if status in ("canceled", "cancelled", "rejected", "expired"):
            log_erro(f"❌ {lado} cancelada/rejeitada: {simbolo} ({status})")
            return None

        if tentativa == 5:
            break

        time.sleep(1.0)

        try:
            consultada = client.fetch_order(ordem_id, simbolo)
            if not isinstance(consultada, dict):
                log_erro(
                    f"⚠️ {lado}: resposta inválida ao consultar ordem "
                    f"{ordem_id}; estado permanece incerto."
                )
                return None
            ordem_atual = consultada
        except Exception as e:
            log_erro(
                f"⚠️ {lado}: consulta {tentativa + 1}/5 falhou para "
                f"{ordem_id}: {e}. Execução permanece incerta."
            )
            # Não usar a resposta anterior para declarar a ordem confirmada.
            return None

    log_erro(
        f"⚠️ {lado}: não foi possível confirmar o estado final da ordem "
        f"{ordem_id} ({simbolo}). Não reenviar automaticamente."
    )
    return None


def comprar_mercado(client, simbolo, valor_usdt):
    """Compra a mercado e retorna somente uma ordem final confirmada."""
    try:
        valor = float(valor_usdt)
        if valor <= 0:
            log_erro(f"❌ Compra abortada: valor inválido ({valor_usdt}).")
            return None

        preco = obter_preco(client, simbolo)
        if not preco or preco <= 0:
            log_erro(f"❌ Preço inválido para {simbolo}: {preco}")
            return None

        qtd = valor / preco

        try:
            qtd = float(client.amount_to_precision(simbolo, qtd))
        except Exception as e:
            log_erro(f"❌ Falha ao ajustar precisão de {simbolo}: {e}")
            return None

        try:
            mercado = client.market(simbolo)
            minimo = float(
                ((mercado.get("limits") or {}).get("amount") or {}).get("min") or 0
            )
        except Exception as e:
            log_erro(f"❌ Não foi possível validar o mínimo de {simbolo}: {e}")
            return None

        if qtd <= 0 or (minimo and qtd < minimo):
            log_erro(f"❌ Compra abortada: {qtd} {simbolo} abaixo do mínimo {minimo}")
            return None

        log_info(f"📤 Enviando compra: {qtd} {simbolo} (~${valor:.2f})")

        try:
            ordem = client.create_order(
                symbol=simbolo,
                type="market",
                side="buy",
                amount=qtd,
            )
        except Exception as e:
            log_erro(
                f"⚠️ Erro ao enviar compra de {simbolo}: {e}. "
                "Não repetir automaticamente; verificar ordens na exchange."
            )
            return None

        return _confirmar_ordem(client, simbolo, ordem, "COMPRA")

    except Exception as e:
        log_erro(f"❌ Erro na compra: {e}")
        return None


def vender_mercado(client, simbolo, quantidade):
    """Vende a mercado e retorna somente uma ordem final confirmada."""
    try:
        try:
            qtd = float(client.amount_to_precision(simbolo, float(quantidade)))
            mercado = client.market(simbolo)
            minimo = float(
                ((mercado.get("limits") or {}).get("amount") or {}).get("min") or 0
            )
        except Exception as e:
            log_erro(
                f"❌ Venda abortada: não foi possível validar quantidade "
                f"e mercado de {simbolo}: {e}"
            )
            return None

        if qtd <= 0 or (minimo and qtd < minimo):
            log_erro(f"❌ Venda abortada: {qtd} {simbolo} abaixo do mínimo {minimo}")
            return None

        log_info(f"📤 Enviando venda: {qtd} {simbolo}")

        try:
            ordem = client.create_order(
                symbol=simbolo,
                type="market",
                side="sell",
                amount=qtd,
            )
        except Exception as e:
            log_erro(
                f"⚠️ Erro ao enviar venda de {simbolo}: {e}. "
                "Não repetir automaticamente; verificar ordens na exchange."
            )
            return None

        return _confirmar_ordem(client, simbolo, ordem, "VENDA")

    except Exception as e:
        log_erro(f"❌ Erro na venda: {e}")
        return None
