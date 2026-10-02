# main.py
# Arquivo principal - o "cérebro" do bot
# ATUALIZADO: Multi-Crypto + Auto-Discovery + Risk Management + PnL no status

import asyncio
import threading
import inspect

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

from relatorio import gerar_relatorio

import config as _cfg
from config import (
    SIMBOLO, TEMPO_ENTRE_ANALISES, MODO_TESTE,
    TELEGRAM_ATIVADO, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    USAR_TESTNET, VALOR_POR_OPERACAO_USDT,
    STOP_LOSS_PERCENTUAL, TAKE_PROFIT_PERCENTUAL,
    SCORE_MINIMO_COMPRA, SCORE_MINIMO_VENDA,
    WATCHLIST
)

# Import do scanner profissional
try:
    from scanner_multi_crypto import MultiCryptoScanner
    MULTI_CRYPTO_ATIVO = len(WATCHLIST.symbols) > 1
except ImportError as e:
    log_erro(f"Scanner multi-crypto não disponível: {e}. Usando modo single-symbol.")
    MULTI_CRYPTO_ATIVO = False

# Import do Auto-Discovery seguro
try:
    from auto_discovery import AutoDiscovery, atualizar_watchlist_se_necessario
    AUTO_DISCOVERY_ATIVO = MULTI_CRYPTO_ATIVO
except ImportError as e:
    log_erro(f"Auto-discovery não disponível: {e}. Usando watchlist fixa.")
    AUTO_DISCOVERY_ATIVO = False


# ==========================================
# HELPERS DE CONFIGURAÇÃO OPCIONAL
# ==========================================
def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value, default=0):
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _safe_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "sim", "on", "verdadeiro"):
        return True
    if s in ("0", "false", "no", "nao", "não", "off", "falso"):
        return False
    return default


def _cfg_float(name, default):
    return _safe_float(getattr(_cfg, name, default), default)


def _cfg_int(name, default):
    return _safe_int(getattr(_cfg, name, default), default)


def _cfg_bool(name, default):
    return _safe_bool(getattr(_cfg, name, default), default)


# Defaults seguros. Se você não colocar nada no config.py, funciona assim mesmo.
MAX_POSICOES_ABERTAS = _cfg_int("MAX_POSICOES_ABERTAS", 5)
MAX_COMPRAS_POR_CICLO = _cfg_int("MAX_COMPRAS_POR_CICLO", 2)
EXPOSICAO_MAXIMA_USDT = _cfg_float("EXPOSICAO_MAXIMA_USDT", 500.0)
COOLDOWN_STOP_MINUTOS = _cfg_int("COOLDOWN_STOP_MINUTOS", 30)
FECHAR_EM_SINAL_VENDA = _cfg_bool("FECHAR_EM_SINAL_VENDA", False)


# ==========================================
# OBJETOS GLOBAIS
# ==========================================
gerenciador = GerenciadorPosicoes()

if TELEGRAM_ATIVADO and TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
    notificador = NotificadorTelegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID)
else:
    notificador = None
# ==========================================
# HOTFIX TELEGRAM MARKDOWN
# Evita erro por underscores em STOP_LOSS, TAKE_PROFIT, SINAL_VENDA etc.
# ==========================================
if notificador and hasattr(notificador, "enviar_mensagem"):
    _original_enviar_mensagem = notificador.enviar_mensagem

    def _enviar_mensagem_seguro(texto, *args, **kwargs):
        texto = str(texto)

        # Converte termos técnicos com underline para versão legível
        texto = texto.replace("STOP_LOSS", "STOP LOSS")
        texto = texto.replace("TAKE_PROFIT", "TAKE PROFIT")
        texto = texto.replace("SINAL_VENDA", "SINAL VENDA")
        texto = texto.replace("STOP_WATCHDOG", "STOP WATCHDOG")
        texto = texto.replace("ENCERRAMENTO", "ENCERRAMENTO")

        # Segurança extra: remove qualquer underline restante que possa quebrar Markdown
        texto = texto.replace("_", " ")

        return _original_enviar_mensagem(texto, *args, **kwargs)

    notificador.enviar_mensagem = _enviar_mensagem_seguro

if USAR_TESTNET:
    client = criar_cliente()
    if client:
        trader = TraderTestnet(client, SIMBOLO, VALOR_POR_OPERACAO_USDT)
        log_info("Conectado na OKX DEMO (Testnet)")
    else:
        trader = None
        log_erro("Falha na testnet. Usando modo simulação.")
else:
    client = None
    trader = None

scanner = MultiCryptoScanner() if MULTI_CRYPTO_ATIVO else None
discovery = AutoDiscovery() if AUTO_DISCOVERY_ATIVO else None

# Alerta de risco no startup
if trader:
    _posicoes_iniciais = len(getattr(trader, "posicoes", {}) or {})
    _exposicao_inicial = sum(
        _safe_float(p.get("valor_investido"), 0.0)
        for p in (getattr(trader, "posicoes", {}) or {}).values()
    )

    if _posicoes_iniciais > MAX_POSICOES_ABERTAS:
        log_erro(
            f"⚠️ RISCO: {_posicoes_iniciais} posições recuperadas excedem "
            f"MAX_POSICOES_ABERTAS={MAX_POSICOES_ABERTAS}. "
            "Novas compras serão bloqueadas até reduzir manualmente."
        )

    if _exposicao_inicial > EXPOSICAO_MAXIMA_USDT:
        log_erro(
            f"⚠️ RISCO: exposição recuperada ${_exposicao_inicial:.2f} excede "
            f"EXPOSICAO_MAXIMA_USDT=${EXPOSICAO_MAXIMA_USDT:.2f}."
        )

parar_evento = threading.Event()

# Event loop persistente para multi-crypto
_loop_multi = None
_ultimos_precos_scan = {}
_inicio_sessao = None
_ciclos_sessao = 0

# ==========================================
# EVENT LOOP PERSISTENTE
# ==========================================
def _get_loop():
    global _loop_multi
    if _loop_multi is None or _loop_multi.is_closed():
        _loop_multi = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop_multi)
    return _loop_multi

async def _verificar_stops_com_precos_reais():
    """
    Stop watchdog: busca preço atual direto da exchange para todas as posições abertas
    e fecha stop/take imediatamente.
    """
    if not trader or not scanner:
        return []

    posicoes = getattr(trader, "posicoes", {}) or {}
    if not posicoes:
        return []

    precos = {}

    for sym in list(posicoes.keys()):
        try:
            ticker = await scanner.ccxt.fetch_ticker_ccxt(sym)
            if ticker and ticker.get("price", 0) > 0:
                precos[sym] = float(ticker["price"])
        except Exception as e:
            log_erro(f"[STOP-WATCHDOG] Falha ao buscar preço {sym}: {type(e).__name__}: {e}")

    if not precos:
        return []

    ops_fechadas = []

    try:
        ops_fechadas = trader.verificar_todas_posicoes(precos)
    except Exception as e:
        log_erro(f"[STOP-WATCHDOG] Erro ao verificar posições: {type(e).__name__}: {e}")
        return []

    for op in ops_fechadas:
        motivo = op.get("motivo_fechamento", "STOP_WATCHDOG")
        lucro = _safe_float(op.get("lucro_prejuizo"), 0.0)
        symbol = op.get("symbol") or op.get("simbolo") or "?"

        log_operacao("VENDA", lucro, f"{symbol} {motivo} WATCHDOG")

        if notificador:
            notificador.notificar_posicao_fechada(op)

        log_info(
            f"[STOP-WATCHDOG] Posição fechada: {symbol} | "
            f"Motivo: {motivo} | Resultado: ${lucro:+.2f}"
        )

    return ops_fechadas

# ==========================================
# HELPERS INTERNOS
# ==========================================
def _norm_symbol(value):
    if value is None:
        return ""
    return str(value).strip().upper().replace("/", "")


def _watchlist_atual():
    if scanner is not None:
        symbols = getattr(scanner, "_symbols", None)
        if symbols:
            return tuple(_norm_symbol(s) for s in symbols if _norm_symbol(s))
    return tuple(_norm_symbol(s) for s in getattr(WATCHLIST, "symbols", ()) if _norm_symbol(s))


def _posicoes_abertas_dict():
    if trader:
        return dict(getattr(trader, "posicoes", {}) or {})
    return {}


def _historico_sessao():
    if trader:
        return list(getattr(trader, "historico", []) or [])
    return list(getattr(gerenciador, "historico", []) or [])


def _exposicao_atual():
    posicoes = _posicoes_abertas_dict()
    if not posicoes:
        return 0.0
    return sum(_safe_float(p.get("valor_investido"), 0.0) for p in posicoes.values())

def _extrair_base(symbol):
    """Extrai a moeda base de um símbolo (ex: BTC de BTC-USDT ou BTCUSDT)"""
    s = str(symbol or "").upper()
    if s.endswith("-USDT"):
        return s[:-5]
    if s.endswith("USDT"):
        return s[:-4]
    return s.replace("USDT", "")

def _fmt_preco(value):
    v = _safe_float(value, 0.0)
    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 100:
        return f"{v:.2f}"
    if v >= 1:
        return f"{v:.4f}"
    return f"{v:.6f}"


def _fmt_money(value):
    v = _safe_float(value, 0.0)
    return f"${v:+,.2f}"


def _resumo_de_lista(historico):
    if not historico:
        return None

    total = len(historico)
    acertos = 0
    lucro_total = 0.0

    for op in historico:
        lucro = _safe_float(op.get("lucro_prejuizo"), 0.0)
        lucro_total += lucro
        if lucro > 0:
            acertos += 1

    taxa_acerto = (acertos / total * 100) if total > 0 else 0.0

    return {
        "lucro_total": lucro_total,
        "taxa_acerto": taxa_acerto,
        "acertos": acertos,
        "total": total,
    }


def _resumo_historico_seguro():
    try:
        resumo = resumo_historico()
    except Exception as e:
        log_erro(f"Erro ao ler resumo do arquivo: {e}")
        resumo = None

    if resumo:
        return resumo

    hist = _historico_sessao()
    if hist:
        return _resumo_de_lista(hist)

    return None


def _carregar_historico_seguro():
    try:
        arquivo = carregar_historico() or []
    except Exception as e:
        log_erro(f"Erro ao carregar histórico do arquivo: {e}")
        arquivo = []

    sessao = _historico_sessao()
    abertas = _posicoes_abertas_dict()

    log_info(
        f"HIST_DEBUG: arquivo={len(arquivo)} | "
        f"sessao={len(sessao)} | "
        f"posicoes_abertas={len(abertas)}"
    )

    if arquivo:
        return arquivo, "arquivo"

    if sessao:
        return sessao, "sessão atual"

    return [], "nenhum"


def _abrir_compra_compat(trader_obj, symbol):
    """
    Abre compra compatível com versões antigas e novas do TraderTestnet.
    """
    try:
        sig = inspect.signature(trader_obj.abrir_compra)
        params = sig.parameters

        for name, param in params.items():
            if name == "self":
                continue
            if param.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            ):
                return trader_obj.abrir_compra(symbol)

        for name in ("symbol", "simbolo"):
            if name in params and params[name].kind == inspect.Parameter.KEYWORD_ONLY:
                return trader_obj.abrir_compra(**{name: symbol})

        return trader_obj.abrir_compra()

    except Exception:
        try:
            return trader_obj.abrir_compra(symbol)
        except TypeError:
            try:
                return trader_obj.abrir_compra(simbolo=symbol)
            except TypeError:
                return trader_obj.abrir_compra()


def _fechar_venda_compat(trader_obj, motivo, symbol):
    """
    Fecha venda compatível com versões antigas e novas do TraderTestnet.
    """
    try:
        sig = inspect.signature(trader_obj.fechar_venda)
        params = sig.parameters

        for name in ("symbol", "simbolo"):
            if name in params:
                return trader_obj.fechar_venda(motivo, **{name: symbol})

        positional = [
            p for p in params.values()
            if p.name != "self"
            and p.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        if len(positional) >= 2:
            return trader_obj.fechar_venda(motivo, symbol)

        return trader_obj.fechar_venda(motivo)

    except Exception:
        try:
            return trader_obj.fechar_venda(motivo, symbol=symbol)
        except TypeError:
            try:
                return trader_obj.fechar_venda(motivo, symbol)
            except TypeError:
                try:
                    return trader_obj.fechar_venda(motivo, simbolo=symbol)
                except TypeError:
                    return trader_obj.fechar_venda(motivo)


def _garantir_posicoes_na_watchlist():
    """
    Garante que nenhum símbolo com posição aberta saia do scan.
    """
    if not scanner or not hasattr(scanner, "atualizar_watchlist"):
        return

    posicoes = _posicoes_abertas_dict()
    if not posicoes:
        return

    current = [_norm_symbol(s) for s in getattr(scanner, "_symbols", ()) if _norm_symbol(s)]
    missing = [sym for sym in posicoes.keys() if sym not in current]

    if missing:
        new_symbols = current + missing
        scanner.atualizar_watchlist(
            new_symbols,
            getattr(scanner, "_coingecko_ids", {}) or {}
        )
        log_info(
            "⚠️ Símbolos com posição aberta reintegrados à watchlist: "
            f"{', '.join(missing)}"
        )


def _aplicar_watchlist(watchlist, coingecko_map=None):
    """
    Aplica watchlist no scanner e força inclusão de símbolos com posição aberta.
    """
    if not scanner or not hasattr(scanner, "atualizar_watchlist"):
        return [_norm_symbol(s) for s in (watchlist or []) if _norm_symbol(s)]

    symbols = []
    for s in (watchlist or []):
        su = _norm_symbol(s)
        if su and su not in symbols:
            symbols.append(su)

    posicoes = _posicoes_abertas_dict()
    for su in posicoes.keys():
        su = _norm_symbol(su)
        if su and su not in symbols:
            symbols.append(su)

    mapa = dict(getattr(scanner, "_coingecko_ids", {}) or {})
    if coingecko_map:
        mapa.update(coingecko_map)

    mapa.setdefault("BTC-USDT", "bitcoin")
    mapa.setdefault("ETH-USDT", "ethereum")

    scanner.atualizar_watchlist(symbols, mapa)
    return symbols


# ==========================================
# BANNER / STATUS TERMINAL
# ==========================================
def mostrar_banner():
    atual = _watchlist_atual()

    log_info("=" * 50)
    log_info("🤖 BOT TRADER - INICIANDO")
    log_info("=" * 50)

    if MULTI_CRYPTO_ATIVO:
        if AUTO_DISCOVERY_ATIVO:
            log_info("📊 Modo: MULTI-CRYPTO + AUTO-DISCOVERY")
            log_info(f"   Watchlist inicial: {len(atual)} pares")
            log_info("   Watchlist final será definida pelo Auto-Discovery no primeiro ciclo.")
        else:
            log_info(f"📊 Modo: MULTI-CRYPTO ({len(atual)} pares)")
    else:
        log_info(f"📊 Par: {SIMBOLO}")

    log_info(f"⏱️  Intervalo: {TEMPO_ENTRE_ANALISES} segundos")
    log_info(f"💰 Valor por operação: ${_safe_float(VALOR_POR_OPERACAO_USDT, 0):.2f}")
    log_info(f"🛡️ Max posições abertas: {MAX_POSICOES_ABERTAS}")
    log_info(f"🛡️ Max compras por ciclo: {MAX_COMPRAS_POR_CICLO}")
    log_info(f"🛡️ Exposição máxima: ${EXPOSICAO_MAXIMA_USDT:.2f}")
    log_info(f"🛡️ Cooldown pós-stop: {COOLDOWN_STOP_MINUTOS} min")
    log_info(f"🌐 Modo: {'TESTNET (ordens reais)' if trader else 'SIMULAÇÃO'}")
    log_info(f"📱 Telegram: {'ATIVADO' if notificador else 'DESATIVADO'}")
    log_info("=" * 50)


def buscar_preco_atual():
    """Busca preço atual via CCXT (compatível com OKX)"""
    try:
        ticker = client.fetch_ticker(SIMBOLO)
        return float(ticker['last'])
    except Exception as e:
        log_erro(f"Falha ao buscar preço: {e}")
        return 0


def mostrar_status_testnet():
    if not trader or not client:
        return

    usdt = obter_saldo(client, "USDT")
    print(f"\n📊 STATUS TESTNET:")
    print(f"   💵 USDT: {_safe_float(usdt, 0):.2f}")

    if MULTI_CRYPTO_ATIVO and hasattr(trader, "mostrar_status_multi"):
        trader.mostrar_status_multi(_ultimos_precos_scan)
    elif trader.tem_posicao():
        moeda = _extrair_base(SIMBOLO)
        qtd = obter_saldo(client, moeda)
        p = trader.posicao
        print(f"   🪙 {moeda}: {_safe_float(qtd, 0):.6f}")
        print(
            f"   🎯 Posição: {_safe_float(p.get('quantidade'), 0):.6f} {moeda} "
            f"@ ${_safe_float(p.get('preco_entrada'), 0):.2f}"
        )
    else:
        print("   ⏸️ Nenhuma posição aberta")


# ==========================================
# COMANDOS DO TELEGRAM
# ==========================================
def montar_status():
    atual = _watchlist_atual()

    if trader and client:
        usdt = obter_saldo(client, "USDT")
        msg = f"📊 *STATUS DO BOT*\n\n💵 USDT: {_safe_float(usdt, 0):.2f}"

        posicoes = _posicoes_abertas_dict()

        if MULTI_CRYPTO_ATIVO and posicoes:
            msg += f"\n\n📊 *{len(posicoes)} posição(ões) aberta(s):*"

            for sym, p in posicoes.items():
                moeda = _extrair_base(sym)
                qtd = _safe_float(p.get("quantidade"), 0.0)
                entrada = _safe_float(p.get("preco_entrada"), 0.0)
                stop = _safe_float(p.get("stop_loss"), 0.0)
                alvo = _safe_float(p.get("take_profit"), 0.0)
                preco_atual = _safe_float(_ultimos_precos_scan.get(sym), 0.0)

                msg += (
                    f"\n\n🎯 *{sym}:*\n"
                    f"Qtd: {qtd:.6f} {moeda}\n"
                    f"Entrada: ${_fmt_preco(entrada)}\n"
                    f"Stop: ${_fmt_preco(stop)}\n"
                    f"Alvo: ${_fmt_preco(alvo)}"
                )

                if preco_atual > 0 and entrada > 0:
                    pnl = (preco_atual - entrada) * qtd
                    pct = ((preco_atual - entrada) / entrada) * 100
                    emoji = "🟢" if pnl >= 0 else "🔴"
                    msg += (
                        f"\nAtual: ${_fmt_preco(preco_atual)}\n"
                        f"{emoji} PnL: {_fmt_money(pnl)} ({pct:+.2f}%)"
                    )

        elif trader.tem_posicao():
            moeda = _extrair_base(SIMBOLO)
            qtd = obter_saldo(client, moeda)
            p = trader.posicao
            msg += f"\n🪙 {moeda}: {_safe_float(qtd, 0):.6f}"
            msg += (
                f"\n\n🎯 *Posição aberta:*\n"
                f"Entrada: ${_safe_float(p.get('preco_entrada'), 0):.2f}\n"
                f"Stop: ${_safe_float(p.get('stop_loss'), 0):.2f}\n"
                f"Alvo: ${_safe_float(p.get('take_profit'), 0):.2f}"
            )
        else:
            msg += "\n\n⏸️ Nenhuma posição aberta"

        resumo = _resumo_historico_seguro()
        if resumo:
            msg += (
                f"\n\n💰 Lucro total: {_fmt_money(resumo['lucro_total'])}\n"
                f"📈 Acerto: {resumo['taxa_acerto']:.0f}% "
                f"({resumo['acertos']}/{resumo['total']})"
            )
        else:
            msg += "\n\n📋 Nenhuma operação fechada registrada ainda."

        if MULTI_CRYPTO_ATIVO:
            msg += f"\n\n🔍 Monitorando {len(atual)} criptos"
            if AUTO_DISCOVERY_ATIVO:
                msg += " (auto-discovery ativo)"

        msg += (
            f"\n\n🛡️ Risco: max {MAX_POSICOES_ABERTAS} posições | "
            f"max {MAX_COMPRAS_POR_CICLO} compras/ciclo | "
            f"exposição ${EXPOSICAO_MAXIMA_USDT:.0f}"
        )

        return msg

    return f"💵 Capital (simulação): ${gerenciador.capital:.2f}"


def montar_posicoes():
    if not trader:
        if getattr(gerenciador, "posicao_aberta", False):
            return "🎯 *Posição simulada aberta.*"
        return "⏸️ Nenhuma posição aberta."

    posicoes = _posicoes_abertas_dict()

    if not posicoes:
        if trader.tem_posicao():
            p = trader.posicao
            moeda = _extrair_base(SIMBOLO)
            return (
                f"🎯 *{SIMBOLO}:*\n"
                f"Qtd: {_safe_float(p.get('quantidade'), 0):.6f} {moeda}\n"
                f"Entrada: ${_safe_float(p.get('preco_entrada'), 0):.2f}\n"
                f"Stop: ${_safe_float(p.get('stop_loss'), 0):.2f}\n"
                f"Alvo: ${_safe_float(p.get('take_profit'), 0):.2f}"
            )
        return "⏸️ Nenhuma posição aberta."

    msg = f"🎯 *POSIÇÕES ABERTAS ({len(posicoes)}):*\n"

    for sym, p in posicoes.items():
        moeda = _extrair_base(sym)
        qtd = _safe_float(p.get("quantidade"), 0.0)
        entrada = _safe_float(p.get("preco_entrada"), 0.0)
        stop = _safe_float(p.get("stop_loss"), 0.0)
        alvo = _safe_float(p.get("take_profit"), 0.0)
        preco_atual = _safe_float(_ultimos_precos_scan.get(sym), 0.0)

        msg += (
            f"\n`{sym}`\n"
            f"Qtd: {qtd:.6f} {moeda}\n"
            f"Entrada: ${_fmt_preco(entrada)}\n"
            f"Stop: ${_fmt_preco(stop)}\n"
            f"Alvo: ${_fmt_preco(alvo)}"
        )

        if preco_atual > 0 and entrada > 0:
            pnl = (preco_atual - entrada) * qtd
            pct = ((preco_atual - entrada) / entrada) * 100
            emoji = "🟢" if pnl >= 0 else "🔴"
            msg += f"\nAtual: ${_fmt_preco(preco_atual)}\n{emoji} PnL: {_fmt_money(pnl)} ({pct:+.2f}%)"

    return msg


def montar_historico():
    historico, origem = _carregar_historico_seguro()

    if not historico:
        posicoes = _posicoes_abertas_dict()

        if posicoes:
            msg = "📋 *Nenhuma operação FECHADA ainda.*\n\n"
            msg += "🎯 *Posições abertas no momento:*\n"

            for sym, p in posicoes.items():
                moeda = _extrair_base(sym)
                msg += (
                    f"\n`{sym}`\n"
                    f"Qtd: {_safe_float(p.get('quantidade'), 0):.6f} {moeda}\n"
                    f"Entrada: ${_safe_float(p.get('preco_entrada'), 0):.2f}\n"
                    f"Stop: ${_safe_float(p.get('stop_loss'), 0):.2f}\n"
                    f"Alvo: ${_safe_float(p.get('take_profit'), 0):.2f}"
                )

            msg += "\n\nℹ️ O `/historico` mostra apenas vendas realizadas."
            msg += "\nUse `/posicoes` para ver posições abertas."
            return msg

        return (
            "📋 Nenhuma operação fechada ainda.\n\n"
            "ℹ️ O histórico mostra apenas vendas realizadas "
            "(take profit, stop loss ou sinal de venda)."
        )

    linhas = []
    for op in historico[-5:]:
        lucro = _safe_float(op.get("lucro_prejuizo"), 0.0)
        emoji = "🟢" if lucro > 0 else "🔴"
        simbolo_str = f" ({op.get('simbolo', SIMBOLO)})" if MULTI_CRYPTO_ATIVO else ""
        motivo = op.get("motivo_fechamento", "FECHAMENTO")
        linhas.append(f"{emoji} {motivo}{simbolo_str}: {_fmt_money(lucro)}")

    msg = f"📋 *Últimas operações fechadas ({origem}):*\n"
    msg += "\n".join(linhas)

    posicoes = _posicoes_abertas_dict()
    if posicoes:
        msg += f"\n\n🎯 Posições abertas agora: {len(posicoes)}"
        msg += "\nUse `/posicoes` para detalhes."

    return msg


def montar_watchlist():
    atual = _watchlist_atual()
    msg = "📋 *WATCHLIST ATUAL*\n\n"

    if not atual:
        msg += "Nenhuma cripto na watchlist."
        return msg

    for i, sym in enumerate(atual, 1):
        msg += f"{i}. `{sym}`\n"

    if AUTO_DISCOVERY_ATIVO:
        msg += "\n🔄 Auto-Discovery ativo"
        msg += "\nUse `/discovery` para forçar atualização."

    msg += (
        f"\n\n🛡️ Risco: max {MAX_POSICOES_ABERTAS} posições | "
        f"max {MAX_COMPRAS_POR_CICLO} compras/ciclo"
    )

    return msg

def montar_relatorio(periodo_dias: int = 7):
    """
    Monta relatório de performance.
    periodo_dias=7 -> semanal
    periodo_dias=None -> completo
    """
    saldo = None

    if trader and client:
        try:
            saldo = obter_saldo(client, "USDT")
        except Exception as e:
            log_erro(f"Erro ao buscar saldo para relatorio: {e}")
            saldo = None

    limites = {
        "MAX_POSICOES_ABERTAS": MAX_POSICOES_ABERTAS,
        "MAX_COMPRAS_POR_CICLO": MAX_COMPRAS_POR_CICLO,
        "EXPOSICAO_MAXIMA_USDT": EXPOSICAO_MAXIMA_USDT,
        "COOLDOWN_STOP_MINUTOS": COOLDOWN_STOP_MINUTOS,
    }

    return gerar_relatorio(
        trader=trader,
        gerenciador=gerenciador,
        ultimos_precos=_ultimos_precos_scan,
        saldo_usdt=saldo,
        inicio_sessao=_inicio_sessao,
        ciclos=_ciclos_sessao,
        periodo_dias=periodo_dias,
        limites=limites,
        watchlist=_watchlist_atual(),
    )

def tratar_comando(texto):
    comando = texto.strip().lower()

    if comando == "/status":
        notificador.enviar_mensagem(montar_status())
        log_info("Comando /status executado")

    elif comando == "/posicoes":
        notificador.enviar_mensagem(montar_posicoes())
        log_info("Comando /posicoes executado")

    elif comando == "/historico":
        notificador.enviar_mensagem(montar_historico())
        log_info("Comando /historico executado")

    elif comando == "/watchlist":
        notificador.enviar_mensagem(montar_watchlist())
        log_info("Comando /watchlist executado")

    elif comando == "/parar":
        notificador.enviar_mensagem("🛑 *Encerrando o bot com segurança...*")
        log_info("Comando /parar recebido - encerrando bot")
        parar_evento.set()

    elif comando == "/ajuda":
        atual = _watchlist_atual()
        ajuda = (
            "📖 *Comandos disponíveis:*\n"
            "/status - saldo, posição e PnL\n"
            "/posicoes - posições abertas detalhadas\n"
            "/historico - últimas operações fechadas\n"
            "/watchlist - criptos sendo monitoradas\n"
            "/relatorio - performance dos últimos 7 dias\n"
            "/relatorio_all - performance completa\n"
            "/fechar_all - fecha todas as posições na testnet\n"        
            "/parar - desligar o bot\n"
            "/ajuda - este menu"
        )

        if MULTI_CRYPTO_ATIVO:
            ajuda += f"\n\n🔍 *Multi-Crypto:* {len(atual)} pares"
            if AUTO_DISCOVERY_ATIVO:
                ajuda += "\n🔄 *Auto-Discovery:* ativo (24h)\n/discovery - forçar atualização"

        ajuda += (
            f"\n\n🛡️ *Risk management:*\n"
            f"Max posições: {MAX_POSICOES_ABERTAS}\n"
            f"Max compras/ciclo: {MAX_COMPRAS_POR_CICLO}\n"
            f"Exposição máxima: ${EXPOSICAO_MAXIMA_USDT:.0f}\n"
            f"Cooldown pós-stop: {COOLDOWN_STOP_MINUTOS} min"
        )

        notificador.enviar_mensagem(ajuda)

    elif comando == "/discovery" and AUTO_DISCOVERY_ATIVO:
        notificador.enviar_mensagem("🔍 *Forçando atualização da watchlist...*")
        loop = _get_loop()

        try:
            resultado = loop.run_until_complete(discovery.descobrir_melhores_criptos())

            # Compatibilidade caso retorne só lista
            if isinstance(resultado, list):
                resultado = {
                    "watchlist": resultado,
                    "coingecko_map": {},
                    "candidates": [],
                    "total_avaliadas": 0,
                    "seguras": 0,
                }

            final_wl = _aplicar_watchlist(
                resultado.get("watchlist", _watchlist_atual()),
                resultado.get("coingecko_map", {})
            )

            msg = "✅ *Watchlist atualizada!*\n\n"
            msg += (
                f"📊 {resultado.get('total_avaliadas', 0)} avaliadas | "
                f"{resultado.get('seguras', 0)} seguras | "
                f"{len(final_wl)} selecionadas\n\n"
            )
            msg += "*Nova watchlist:*\n"

            for i, sym in enumerate(final_wl, 1):
                candidate = next(
                    (c for c in resultado.get("candidates", []) if c.get("symbol") == sym),
                    None
                )
                if candidate:
                    msg += f"{i}. `{sym}` — Potencial: {_safe_float(candidate.get('potencial'), 0):.1f}%\n"
                else:
                    msg += f"{i}. `{sym}`\n"

            msg += "\n🛡️ Símbolos com posição aberta foram mantidos no scan."

            notificador.enviar_mensagem(msg)

        except Exception as e:
            notificador.enviar_mensagem(f"❌ Erro no discovery: {e}")
            log_erro(f"Erro no comando /discovery: {e}")

        log_info("Comando /discovery executado")

    elif comando in ("/relatorio", "/relatorio7", "/relatorio_semana"):
        notificador.enviar_mensagem(montar_relatorio(periodo_dias=7))
        log_info("Comando /relatorio executado")

    elif comando in ("/relatorio_all", "/relatorio_tudo", "/relatorio_completo"):
        notificador.enviar_mensagem(montar_relatorio(periodo_dias=None))
        log_info("Comando /relatorio_all executado")

    elif comando == "/fechar_all":
        if not trader:
            notificador.enviar_mensagem("⚠️ Modo simulação: fechamento manual não disponível neste contexto.")
            log_info("Comando /fechar_all ignorado: trader indisponível")
            return

        notificador.enviar_mensagem("🛑 *Fechando todas as posições na testnet...*")

        fechadas = 0
        falhas = []

        posicoes = dict(getattr(trader, "posicoes", {}) or {})

        for sym in list(posicoes.keys()):
            try:
                op = trader.fechar_venda("ENCERRAMENTO_MANUAL", symbol=sym)

                if op:
                    fechadas += 1

                    if notificador:
                        notificador.notificar_posicao_fechada(op)
                else:
                    falhas.append(sym)

            except Exception as e:
                falhas.append(f"{sym}: {type(e).__name__}: {e}")
                log_erro(f"[FECHAR_ALL] Erro ao fechar {sym}: {e}")

        msg = "✅ *Fechamento manual concluído*\n\n"
        msg += f"Posições fechadas: {fechadas}\n"

        if falhas:
            msg += f"⚠️ Falhas: {', '.join(map(str, falhas))}"
        else:
            msg += "Nenhuma falha registrada."

        notificador.enviar_mensagem(msg)
        log_info(f"Comando /fechar_all executado: fechadas={fechadas}, falhas={len(falhas)}")

    else:
        notificador.enviar_mensagem("❓ Comando desconhecido. Use /ajuda")


# ==========================================
# ANÁLISE SINGLE-SYMBOL (FALLBACK)
# ==========================================
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
    if indicadores.get("sma_20"):
        print(f"   SMA20: ${indicadores['sma_20']:.2f}")
    if indicadores.get("rsi"):
        print(f"   RSI:   {indicadores['rsi']}")

    interpretacao = indicadores.get("interpretacao", {})
    print("\n🧠 INTERPRETAÇÃO:")
    print(f"   Tendência: {interpretacao.get('tendencia')} | RSI: {interpretacao.get('rsi_status')}")

    score = _safe_float(score, 0.0)
    print(f"\n🎯 SCORE: {score:.1f}/100")
    barra = "█" * int(score / 10) + "░" * (10 - int(score / 10))
    print(f"   [{barra}] {score:.1f}%")

    if trader:
        if trader.tem_posicao():
            motivo = trader.verificar_saida(preco_atual)
            if motivo:
                operacao = _fechar_venda_compat(trader, motivo, SIMBOLO)
                if operacao:
                    log_operacao("VENDA", operacao.get("lucro_prejuizo", 0), motivo)
                if notificador and operacao:
                    notificador.notificar_posicao_fechada(operacao)
            else:
                entrada = _safe_float(trader.posicao.get("preco_entrada"), 0.0)
                if entrada > 0:
                    variacao = (preco_atual - entrada) / entrada * 100
                    print(f"\n   🎯 Posição REAL aberta: {variacao:+.2f}% no momento")

        elif sinal == "COMPRA" and score >= SCORE_MINIMO_COMPRA:
            log_sinal("COMPRA", score, preco_atual)
            if notificador:
                notificador.notificar_sinal(sinal, score, preco_atual)
            pos = _abrir_compra_compat(trader, SIMBOLO)
            if pos and notificador:
                notificador.notificar_posicao_aberta(pos)

        elif sinal == "VENDA" and score >= SCORE_MINIMO_VENDA:
            log_info("Sinal de VENDA sem posição - ignorado (spot)")

        else:
            print("\n⏸️ Aguardando sinais mais claros...")

    else:
        if gerenciador.posicao_aberta:
            deve_fechar, motivo, lucro = gerenciador.verificar_posicao(preco_atual)
            if deve_fechar:
                operacao = gerenciador.fechar_posicao(preco_atual, motivo)
                if operacao:
                    log_operacao("VENDA (sim)", operacao.get("lucro_prejuizo", 0), motivo)
                if notificador and operacao:
                    notificador.notificar_posicao_fechada(operacao)
            else:
                print("\n   🎯 Posição simulada sendo monitorada...")

        elif (
            (sinal == "COMPRA" and score >= SCORE_MINIMO_COMPRA)
            or (sinal == "VENDA" and score >= SCORE_MINIMO_VENDA)
        ):
            log_sinal(sinal, score, preco_atual)
            if notificador:
                notificador.notificar_sinal(sinal, score, preco_atual)
            posicao = gerenciador.abrir_posicao(sinal, preco_atual)
            if notificador and posicao:
                notificador.notificar_posicao_aberta(posicao)
        else:
            print("\n⏸️ Aguardando sinais mais claros...")

    return {"sinal": sinal, "score": score, "preco": preco_atual}


# ==========================================
# ANÁLISE MULTI-CRYPTO PROFISSIONAL
# ==========================================
def executar_analise_multi():
    global _ultimos_precos_scan

    if not scanner:
        return executar_analise()

    # Garantia crítica: posição aberta nunca sai do scan
    _garantir_posicoes_na_watchlist()

    print(f"\n🔍 Scan Multi-Crypto em {datetime.now().strftime('%H:%M:%S')}...")

    loop = _get_loop()

    try:
        resultados = loop.run_until_complete(scanner.scan_completo())
    except Exception as e:
        log_erro(f"Falha no scan multi-crypto: {e}. Usando fallback single-symbol.")
        return executar_analise()

    if not resultados:
        log_erro("Scan retornou vazio. Usando fallback single-symbol.")
        return executar_analise()

    _ultimos_precos_scan = {
        res["symbol"]: _safe_float(res.get("preco"), 0.0)
        for res in resultados
        if res.get("preco", 0) > 0
    }

    # 1) Verifica saída de TODAS as posições abertas primeiro
    posicoes = _posicoes_abertas_dict()
    if trader and posicoes and hasattr(trader, "verificar_todas_posicoes"):
        try:
            ops_fechadas = trader.verificar_todas_posicoes(_ultimos_precos_scan)
            for op in ops_fechadas:
                if notificador:
                    notificador.notificar_posicao_fechada(op)
        except Exception as e:
            log_erro(f"Erro ao verificar saídas das posições: {e}")

    # 2) Exibe resumo do scan
    print(f"\n📊 RESULTADO DO SCAN ({len(resultados)} criptos):")
    print(f"{'─' * 60}")
    print(f"{'Símbolo':<12} {'Score':>7} {'Ação':<10} {'Preço':>14}")
    print(f"{'─' * 60}")

    sinais_compra = []
    sinais_venda = []

    for res in resultados:
        symbol = res["symbol"]
        score = _safe_float(res.get("score_unificado"), 0.0)
        acao = res.get("acao", "AGUARDAR")
        preco = _safe_float(res.get("preco"), 0.0)

        barra = "█" * int(score / 10) + "░" * (10 - int(score / 10))
        emoji = "🟢" if acao == "COMPRA" else ("🔴" if acao == "VENDA" else "⏸️")
        print(f"{emoji} {symbol:<10} [{barra}] {score:>5.1f}%  {acao:<10} ${_fmt_preco(preco):>12}")

        if acao == "COMPRA":
            sinais_compra.append(res)
        elif acao == "VENDA":
            sinais_venda.append(res)

    print(f"{'─' * 60}")
    print(
        f"🟢 Compras: {len(sinais_compra)} | "
        f"🔴 Vendas: {len(sinais_venda)} | "
        f"⏸️ Aguardando: {len(resultados) - len(sinais_compra) - len(sinais_venda)}"
    )

    # 3) Fecha posições em sinal de VENDA, se habilitado
    if trader and FECHAR_EM_SINAL_VENDA:
        for res in sinais_venda:
            symbol = res["symbol"]
            if trader.tem_posicao(symbol):
                op = _fechar_venda_compat(trader, "SINAL_VENDA", symbol)
                if op:
                    log_operacao("VENDA", op.get("lucro_prejuizo", 0), "SINAL_VENDA")
                    if notificador:
                        notificador.notificar_posicao_fechada(op)

    # 4) Execução real multi-symbol com risk management
    novas_compras = 0
    exposicao_atual = _exposicao_atual()

    for res in sinais_compra:
        symbol = res["symbol"]
        score = _safe_float(res.get("score_unificado"), 0.0)
        preco = _safe_float(res.get("preco"), 0.0)
        razoes_top3 = [str(r) for r in res.get("razoes", [])[:3]]

        log_sinal(symbol, score, preco)
        print(f"\n🎯 [{symbol}] SINAL DE COMPRA CONFIRMADO")
        print(f"   Score Unificado: {score:.1f}%")
        print(
            f"   Breakdown: Tec={res['breakdown']['tecnico']:.1f} | "
            f"Vol={res['breakdown']['volume_liq']:.1f} | "
            f"Sent={res['breakdown']['sentimento']:.1f}"
        )
        print(f"   Top razões: {', '.join(razoes_top3)}")

        if notificador:
            msg = (
                f"🎯 *SINAL COMPRA* `{symbol}`\n\n"
                f"📊 Score Unificado: *{score:.1f}%*\n"
                f"💰 Preço: ${_fmt_preco(preco)}\n\n"
                f"📐 *Breakdown:*\n"
                f"• Técnico: {res['breakdown']['tecnico']:.1f}\n"
                f"• Volume/Liq: {res['breakdown']['volume_liq']:.1f}\n"
                f"• Sentimento: {res['breakdown']['sentimento']:.1f}\n"
                f"• On-chain: {res['breakdown']['onchain']:.1f}\n\n"
                f"💡 *Motivos:* {', '.join(razoes_top3)}"
            )
            notificador.enviar_mensagem(msg)

        if trader:
            posicoes = _posicoes_abertas_dict()

            if len(posicoes) >= MAX_POSICOES_ABERTAS:
                log_info(f"[{symbol}] Limite de posições abertas atingido ({MAX_POSICOES_ABERTAS}).")
                continue

            if novas_compras >= MAX_COMPRAS_POR_CICLO:
                log_info(f"[{symbol}] Limite de compras por ciclo atingido ({MAX_COMPRAS_POR_CICLO}).")
                continue

            valor_operacao = _safe_float(VALOR_POR_OPERACAO_USDT, 0.0)
            if exposicao_atual + valor_operacao > EXPOSICAO_MAXIMA_USDT:
                log_info(
                    f"[{symbol}] Limite de exposição atingido. "
                    f"Atual: ${exposicao_atual:.2f}, máxima: ${EXPOSICAO_MAXIMA_USDT:.2f}."
                )
                continue

            if hasattr(trader, "em_cooldown") and trader.em_cooldown(symbol):
                log_info(f"[{symbol}] Em cooldown pós-stop. Compra ignorada.")
                continue

            pos = _abrir_compra_compat(trader, symbol)
            if pos:
                novas_compras += 1
                exposicao_atual += _safe_float(pos.get("valor_investido"), valor_operacao)
                if notificador:
                    notificador.notificar_posicao_aberta(pos)
        else:
            posicao = gerenciador.abrir_posicao("COMPRA", preco)
            if notificador and posicao:
                notificador.notificar_posicao_aberta(posicao)

    # 5) Log de vendas não executadas (se não tinha posição)
    for res in sinais_venda:
        symbol = res["symbol"]
        if not trader or not trader.tem_posicao(symbol):
            log_info(f"[{symbol}] Sinal VENDA sem posição | Score: {_safe_float(res.get('score_unificado'), 0):.1f}%")

    return resultados


# ==========================================
# LOOP PRINCIPAL
# ==========================================
def main():
    global _inicio_sessao, _ciclos_sessao

    mostrar_banner()
    _inicio_sessao = datetime.now()

    listener = None
    if notificador:
        atual = _watchlist_atual()
        modo_str = "MULTI-CRYPTO" if MULTI_CRYPTO_ATIVO else ("TESTNET" if trader else "SIMULAÇÃO")
        discovery_str = " + Auto-Discovery" if AUTO_DISCOVERY_ATIVO else ""

        notificador.enviar_mensagem(
            f"🤖 *Bot iniciado!*\n"
            f"Modo: {modo_str}{discovery_str}\n"
            f"Pares iniciais: {len(atual)}"
        )
        log_info("Bot iniciado e conectado ao Telegram")

        listener = ListenerComandos(notificador, tratar_comando)
        listener.iniciar()

    ciclos = 0

    try:
        while not parar_evento.is_set():
            ciclos += 1
            _ciclos_sessao = ciclos

            print(f"\n{'─' * 50}")
            print(f"🔄 Ciclo #{ciclos}")

            # STOP WATCHDOG: verifica stop/take com preço atual antes de qualquer outra coisa
            if trader and getattr(trader, "posicoes", None):
                try:
                    loop = _get_loop()
                    loop.run_until_complete(_verificar_stops_com_precos_reais())
                except Exception as e:
                    log_erro(f"Erro no stop watchdog: {type(e).__name__}: {e}")

            # Auto-Discovery: atualiza watchlist e APLICA no scanner
            if discovery:
                loop = _get_loop()
                try:
                    update = loop.run_until_complete(
                        atualizar_watchlist_se_necessario(discovery, notificador)
                    )

                    if update:
                        if isinstance(update, dict):
                            watchlist = update.get("watchlist") or []
                            coingecko_map = update.get("coingecko_map") or {}
                        else:
                            watchlist = update
                            coingecko_map = {}

                        if watchlist:
                            final_wl = _aplicar_watchlist(watchlist, coingecko_map)
                            log_info(
                                "🔄 Watchlist aplicada no scanner: "
                                f"{', '.join(final_wl)}"
                            )

                except Exception as e:
                    log_erro(f"Erro no Auto-Discovery: {e}")

            if MULTI_CRYPTO_ATIVO:
                executar_analise_multi()
            else:
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
        loop = _get_loop()

        if discovery:
            try:
                loop.run_until_complete(discovery.close())
                log_info("Auto-Discovery finalizado.")
            except Exception as e:
                log_erro(f"Erro ao fechar discovery: {e}")

        if scanner:
            try:
                loop.run_until_complete(scanner.fechar())
                log_info("Scanner multi-crypto finalizado.")
            except Exception as e:
                log_erro(f"Erro ao fechar scanner: {e}")

        try:
            if not loop.is_closed():
                loop.close()
        except Exception:
            pass

        if listener:
            listener.parar()

    atual = _watchlist_atual()

    log_info("=" * 50)
    log_info("📊 RESUMO FINAL")
    log_info(f"Ciclos: {ciclos}")

    historico = _historico_sessao()
    log_info(f"Operações fechadas na sessão: {len(historico)}")

    posicoes = _posicoes_abertas_dict()
    log_info(f"Posições abertas no encerramento: {len(posicoes)}")

    if MULTI_CRYPTO_ATIVO:
        log_info(f"Modo: Multi-Crypto ({len(atual)} pares)")
        if AUTO_DISCOVERY_ATIVO:
            log_info("Auto-Discovery: ativo")

    log_info("=" * 50)

    if notificador:
        notificador.enviar_mensagem("👋 *Bot desligado.* Até a próxima!")


if __name__ == "__main__":
    main()