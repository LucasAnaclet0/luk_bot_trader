# relatorio.py
"""
Relatório profissional de performance do bot.

Métricas:
- operações fechadas
- win rate
- profit factor
- lucro líquido
- maior gain / maior loss
- drawdown realizado
- desempenho por símbolo
- desempenho por motivo de fechamento
- posições abertas
- exposição atual
- PnL não realizado
- cooldowns ativos
- alertas de risco
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from memoria import carregar_historico


# ==========================================
# HELPERS
# ==========================================

def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value == "":
            return int(default)
        return int(float(value))
    except Exception:
        return int(default)


def _norm_symbol(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("/", "")


def _symbol_op(op: Dict[str, Any]) -> str:
    return (
        _norm_symbol(op.get("simbolo"))
        or _norm_symbol(op.get("symbol"))
        or _norm_symbol(op.get("par"))
        or "SEM SIMBOLO"
    )


def _motivo_op(op: Dict[str, Any]) -> str:
    motivo = str(op.get("motivo_fechamento") or "FECHAMENTO").upper()
    return motivo.replace("_", " ")


def _fmt_price(value: Any) -> str:
    v = _safe_float(value, 0.0)

    if v >= 1000:
        return f"{v:,.2f}"
    if v >= 100:
        return f"{v:.2f}"
    if v >= 1:
        return f"{v:.4f}"
    if v > 0:
        return f"{v:.6f}"

    return "0.00"


def _fmt_money(value: Any) -> str:
    v = _safe_float(value, 0.0)
    return f"${v:+,.2f}"


def _fmt_pct(value: Any) -> str:
    v = _safe_float(value, 0.0)
    return f"{v:+.2f}%"


def _parse_dt(op: Dict[str, Any]) -> Optional[datetime]:
    """
    Tenta extrair data/hora da operação.
    Suporta:
    - criado_em ISO
    - data formato dd/mm/YYYY HH:MM:SS
    - timestamp ISO
    """
    for field in ("criado_em", "data", "timestamp"):
        val = op.get(field)
        if not val:
            continue

        txt = str(val).strip()
        if not txt:
            continue

        # ISO
        try:
            return datetime.fromisoformat(txt.replace("Z", "+00:00"))
        except Exception:
            pass

        # dd/mm/YYYY HH:MM:SS
        try:
            return datetime.strptime(txt, "%d/%m/%Y %H:%M:%S")
        except Exception:
            pass

        # YYYY-mm-dd HH:MM:SS
        try:
            return datetime.strptime(txt, "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass

    return None


def _ordenar_por_data(ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        ops,
        key=lambda op: _parse_dt(op) or datetime.min
    )


def _filtrar_periodo(
    ops: List[Dict[str, Any]],
    dias: Optional[int] = None
) -> List[Dict[str, Any]]:
    if not dias:
        return list(ops)

    corte = datetime.now() - timedelta(days=int(dias))
    filtradas = []

    for op in ops:
        dt = _parse_dt(op)

        # Se não tiver data, mantém para não perder operação antiga malformada.
        if dt is None or dt >= corte:
            filtradas.append(op)

    return filtradas


def _get_historico(
    trader: Optional[Any] = None,
    gerenciador: Optional[Any] = None
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Retorna (histórico, origem).
    Prioriza arquivo. Se vazio, usa sessão.
    """
    arquivo: List[Dict[str, Any]] = []

    try:
        arquivo = carregar_historico() or []
    except Exception:
        arquivo = []

    sessao: List[Dict[str, Any]] = []

    if trader is not None:
        sessao = list(getattr(trader, "historico", []) or [])
    elif gerenciador is not None:
        sessao = list(getattr(gerenciador, "historico", []) or [])

    if arquivo:
        return arquivo, "arquivo"

    if sessao:
        return sessao, "sessao atual"

    return [], "nenhum"


def _calcular_stats(ops: List[Dict[str, Any]]) -> Dict[str, Any]:
    total = len(ops)

    wins = 0
    losses = 0
    neutros = 0

    ganho_bruto = 0.0
    perda_bruta = 0.0
    lucro_liquido = 0.0

    melhor: Optional[Dict[str, Any]] = None
    pior: Optional[Dict[str, Any]] = None

    melhor_pnl = None
    pior_pnl = None

    for op in ops:
        pnl = _safe_float(op.get("lucro_prejuizo"), 0.0)
        lucro_liquido += pnl

        if pnl > 0:
            wins += 1
            ganho_bruto += pnl

            if melhor_pnl is None or pnl > melhor_pnl:
                melhor_pnl = pnl
                melhor = op

        elif pnl < 0:
            losses += 1
            perda_bruta += abs(pnl)

            if pior_pnl is None or pnl < pior_pnl:
                pior_pnl = pnl
                pior = op

        else:
            neutros += 1

    trades_validos = wins + losses
    win_rate = (wins / trades_validos * 100) if trades_validos > 0 else 0.0

    if perda_bruta > 0:
        profit_factor = ganho_bruto / perda_bruta
    elif ganho_bruto > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    media_ganho = ganho_bruto / wins if wins > 0 else 0.0
    media_perda = perda_bruta / losses if losses > 0 else 0.0
    expectativa = lucro_liquido / total if total > 0 else 0.0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "neutros": neutros,
        "lucro_liquido": lucro_liquido,
        "ganho_bruto": ganho_bruto,
        "perda_bruta": perda_bruta,
        "win_rate": win_rate,
        "profit_factor": profit_factor,
        "media_ganho": media_ganho,
        "media_perda": media_perda,
        "expectativa": expectativa,
        "melhor_operacao": melhor,
        "pior_operacao": pior,
        "melhor_pnl": melhor_pnl or 0.0,
        "pior_pnl": pior_pnl or 0.0,
    }


def _calcular_drawdown(ops: List[Dict[str, Any]]) -> Tuple[float, float, float, float]:
    """
    Retorna:
    (max_drawdown_usd, max_drawdown_pct, equity_atual, pico_equity)

    Drawdown calculado sobre PnL realizado acumulado.
    """
    ordenadas = _ordenar_por_data(ops)

    equity = 0.0
    pico = 0.0
    max_dd = 0.0
    max_dd_pct = 0.0

    for op in ordenadas:
        pnl = _safe_float(op.get("lucro_prejuizo"), 0.0)
        equity += pnl

        if equity > pico:
            pico = equity

        dd = pico - equity

        if dd > max_dd:
            max_dd = dd

        if pico > 0:
            dd_pct = (dd / pico) * 100
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

    return max_dd, max_dd_pct, equity, pico


def _agrupar_por_chave(
    ops: List[Dict[str, Any]],
    chave_fn,
    nome_grupo: str
) -> List[Dict[str, Any]]:
    grupos: Dict[str, List[Dict[str, Any]]] = {}

    for op in ops:
        key = chave_fn(op) or "OUTRO"
        grupos.setdefault(key, []).append(op)

    resultado = []

    for key, grupo in grupos.items():
        stats = _calcular_stats(grupo)
        stats[nome_grupo] = key
        resultado.append(stats)

    resultado.sort(key=lambda x: x.get("lucro_liquido", 0.0), reverse=True)
    return resultado


def _por_simbolo(ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _agrupar_por_chave(ops, _symbol_op, "simbolo")


def _por_motivo(ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _agrupar_por_chave(ops, _motivo_op, "motivo")


def _posicoes_abertas(trader: Optional[Any]) -> Dict[str, Dict[str, Any]]:
    if trader is None:
        return {}
    return dict(getattr(trader, "posicoes", {}) or {})


def _exposicao_atual(posicoes: Dict[str, Dict[str, Any]]) -> float:
    total = 0.0

    for p in posicoes.values():
        total += _safe_float(p.get("valor_investido"), 0.0)

    return total


def _pnl_nao_realizado(
    posicoes: Dict[str, Dict[str, Any]],
    precos: Dict[str, Any]
) -> Tuple[float, List[str]]:
    total = 0.0
    linhas = []

    precos = precos or {}

    for sym, p in posicoes.items():
        sym = _norm_symbol(sym) or "SEM SIMBOLO"
        base = sym[:-4] if sym.endswith("USDT") else sym.replace("USDT", "")

        qtd = _safe_float(p.get("quantidade"), 0.0)
        entrada = _safe_float(p.get("preco_entrada"), 0.0)
        preco = _safe_float(precos.get(sym), 0.0)

        if qtd <= 0 or entrada <= 0:
            continue

        if preco > 0:
            pnl = (preco - entrada) * qtd
            pct = ((preco - entrada) / entrada) * 100
            total += pnl

            emoji = "🟢" if pnl >= 0 else "🔴"

            linhas.append(
                f"{emoji} {sym}: "
                f"{qtd:.6f} {base} | "
                f"in ${_fmt_price(entrada)} | "
                f"atual ${_fmt_price(preco)} | "
                f"{_fmt_money(pnl)} ({_fmt_pct(pct)})"
            )
        else:
            linhas.append(
                f"⏸️ {sym}: "
                f"{qtd:.6f} {base} | "
                f"in ${_fmt_price(entrada)} | "
                f"sem preço atual"
            )

    return total, linhas


def _cooldowns_ativos(trader: Optional[Any]) -> List[Tuple[str, float]]:
    if trader is None:
        return []

    cooldowns = getattr(trader, "_cooldowns", {}) or {}
    now = time.time()
    ativos = []

    for sym, expires_at in cooldowns.items():
        try:
            expires_at = float(expires_at)
        except Exception:
            continue

        if expires_at > now:
            minutos = (expires_at - now) / 60.0
            ativos.append((_norm_symbol(sym) or "SEM SIMBOLO", minutos))

    ativos.sort(key=lambda x: x[1], reverse=True)
    return ativos


def _limitar_mensagem(texto: str, limite: int = 3500) -> str:
    if len(texto) <= limite:
        return texto

    return texto[:limite - 20].rstrip() + "\n...(relatorio truncado)"


# ==========================================
# RELATORIO PRINCIPAL
# ==========================================

def gerar_relatorio(
    trader: Optional[Any] = None,
    gerenciador: Optional[Any] = None,
    ultimos_precos: Optional[Dict[str, Any]] = None,
    saldo_usdt: Optional[float] = None,
    inicio_sessao: Optional[datetime] = None,
    ciclos: int = 0,
    periodo_dias: Optional[int] = 7,
    limites: Optional[Dict[str, Any]] = None,
    watchlist: Optional[tuple] = None
) -> str:
    """
    Gera relatório em texto pronto para Telegram.

    periodo_dias:
    - 7 = semanal
    - None = completo
    """

    ultimos_precos = ultimos_precos or {}
    limites = limites or {}
    watchlist = tuple(watchlist or ())

    historico, origem = _get_historico(trader, gerenciador)
    ops_periodo = _filtrar_periodo(historico, periodo_dias)
    ops_ordenadas = _ordenar_por_data(ops_periodo)

    stats = _calcular_stats(ops_ordenadas)
    max_dd, max_dd_pct, equity, pico = _calcular_drawdown(ops_ordenadas)

    por_simbolo = _por_simbolo(ops_ordenadas)
    por_motivo = _por_motivo(ops_ordenadas)

    posicoes = _posicoes_abertas(trader)
    exposicao = _exposicao_atual(posicoes)
    pnl_aberto, linhas_pnl = _pnl_nao_realizado(posicoes, ultimos_precos)
    cooldowns = _cooldowns_ativos(trader)

    titulo_periodo = (
        "COMPLETO"
        if periodo_dias is None
        else f"ULTIMOS {periodo_dias} DIAS"
    )

    linhas: List[str] = []

    linhas.append(f"📊 *RELATORIO {titulo_periodo}*")
    linhas.append(f"Gerado: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    linhas.append(f"Fonte: {origem}")

    if inicio_sessao:
        try:
            linhas.append(
                f"Sessao desde: {inicio_sessao.strftime('%d/%m/%Y %H:%M:%S')}"
            )
        except Exception:
            pass

    if ciclos:
        linhas.append(f"Ciclos na sessao: {ciclos}")

    if watchlist:
        linhas.append(f"Watchlist ativa: {len(watchlist)} pares")

    if saldo_usdt is not None:
        linhas.append(f"Saldo USDT: ${_safe_float(saldo_usdt, 0.0):,.2f}")

    linhas.append("")

    # ==========================================
    # RISCO / POSICOES ABERTAS
    # ==========================================
    linhas.append("🛡️ *RISCO ATUAL*")

    max_pos = _safe_int(limites.get("MAX_POSICOES_ABERTAS"), 0)
    max_exp = _safe_float(limites.get("EXPOSICAO_MAXIMA_USDT"), 0.0)
    max_compras = _safe_int(limites.get("MAX_COMPRAS_POR_CICLO"), 0)
    cooldown_min = _safe_int(limites.get("COOLDOWN_STOP_MINUTOS"), 0)

    linhas.append(f"Posicoes abertas: {len(posicoes)}")
    linhas.append(f"Exposicao aberta: ${exposicao:,.2f}")
    linhas.append(f"PnL nao realizado: {_fmt_money(pnl_aberto)}")

    if max_pos:
        linhas.append(f"Limite posicoes: {max_pos}")

        if len(posicoes) > max_pos:
            linhas.append(
                f"⚠️ ALERTA: posicoes abertas {len(posicoes)} acima do limite {max_pos}"
            )

    if max_compras:
        linhas.append(f"Limite compras/ciclo: {max_compras}")

    if max_exp:
        linhas.append(f"Limite exposicao: ${max_exp:,.2f}")

        if exposicao > max_exp:
            linhas.append(
                f"⚠️ ALERTA: exposicao ${exposicao:,.2f} acima do limite ${max_exp:,.2f}"
            )

    if cooldown_min:
        linhas.append(f"Cooldown pos-stop: {cooldown_min} min")

    if cooldowns:
        linhas.append("")
        linhas.append("⏳ *COOLDOWNS ATIVOS*")

        for sym, minutos in cooldowns[:10]:
            linhas.append(f"{sym}: {minutos:.1f} min")

    if linhas_pnl:
        linhas.append("")
        linhas.append("🎯 *POSICOES ABERTAS*")

        for linha in linhas_pnl[:12]:
            linhas.append(linha)

        if len(linhas_pnl) > 12:
            linhas.append(f"... e mais {len(linhas_pnl) - 12} posicoes")

    linhas.append("")

    # ==========================================
    # PERFORMANCE FECHADA
    # ==========================================
    linhas.append("📈 *PERFORMANCE FECHADA*")

    if stats["total"] == 0:
        linhas.append("Nenhuma operacao fechada no periodo.")
    else:
        linhas.append(f"Operacoes: {stats['total']}")
        linhas.append(f"Ganhos: {stats['wins']}")
        linhas.append(f"Perdas: {stats['losses']}")
        linhas.append(f"Neutras: {stats['neutros']}")
        linhas.append(f"Win rate: {stats['win_rate']:.1f}%")
        linhas.append(f"Lucro liquido: {_fmt_money(stats['lucro_liquido'])}")
        linhas.append(f"Ganho bruto: {_fmt_money(stats['ganho_bruto'])}")
        linhas.append(f"Perda bruta: -${stats['perda_bruta']:,.2f}")
        linhas.append(f"Profit factor: {stats['profit_factor']:.2f}")
        linhas.append(f"Media ganho: {_fmt_money(stats['media_ganho'])}")
        linhas.append(f"Media perda: -${stats['media_perda']:,.2f}")
        linhas.append(f"Expectativa por trade: {_fmt_money(stats['expectativa'])}")

        if stats["melhor_operacao"]:
            melhor = stats["melhor_operacao"]
            linhas.append(
                f"Melhor trade: {_symbol_op(melhor)} "
                f"{_fmt_money(stats['melhor_pnl'])} "
                f"({_motivo_op(melhor)})"
            )

        if stats["pior_operacao"]:
            pior = stats["pior_operacao"]
            linhas.append(
                f"Pior trade: {_symbol_op(pior)} "
                f"{_fmt_money(stats['pior_pnl'])} "
                f"({_motivo_op(pior)})"
            )

        linhas.append("")
        linhas.append("📉 *DRAWDOWN REALIZADO*")
        linhas.append(f"Max drawdown: -${max_dd:,.2f}")
        linhas.append(f"Max drawdown %: {max_dd_pct:.2f}%")
        linhas.append(f"Equity realizada atual: {_fmt_money(equity)}")
        linhas.append(f"Pico de equity: {_fmt_money(pico)}")

    linhas.append("")

    # ==========================================
    # DESEMPENHO POR SIMBOLO
    # ==========================================
    if por_simbolo:
        linhas.append("🧩 *DESEMPENHO POR SIMBOLO*")

        for item in por_simbolo[:10]:
            linhas.append(
                f"{item['simbolo']}: "
                f"{item['total']} trades | "
                f"{item['win_rate']:.0f}% win | "
                f"{_fmt_money(item['lucro_liquido'])} | "
                f"PF {item['profit_factor']:.2f}"
            )

        if len(por_simbolo) > 10:
            linhas.append(f"... e mais {len(por_simbolo) - 10} simbolos")

        linhas.append("")

    # ==========================================
    # DESEMPENHO POR MOTIVO
    # ==========================================
    if por_motivo:
        linhas.append("🧾 *DESEMPENHO POR MOTIVO*")

        for item in por_motivo[:10]:
            linhas.append(
                f"{item['motivo']}: "
                f"{item['total']} trades | "
                f"{item['win_rate']:.0f}% win | "
                f"{_fmt_money(item['lucro_liquido'])}"
            )

        linhas.append("")

    # ==========================================
    # ULTIMAS OPERACOES
    # ==========================================
    if ops_ordenadas:
        linhas.append("🕒 *ULTIMAS OPERACOES*")

        for op in ops_ordenadas[-8:]:
            pnl = _safe_float(op.get("lucro_prejuizo"), 0.0)
            emoji = "🟢" if pnl > 0 else ("🔴" if pnl < 0 else "⚪")

            dt = _parse_dt(op)
            data_txt = dt.strftime("%d/%m %H:%M") if dt else "sem data"

            linhas.append(
                f"{emoji} {data_txt} | "
                f"{_symbol_op(op)} | "
                f"{_motivo_op(op)} | "
                f"{_fmt_money(pnl)}"
            )

    msg = "\n".join(linhas)
    return _limitar_mensagem(msg)