# trader_testnet.py
# Executa ordens reais na OKX Testnet (Adaptado para CCXT)
# Multi-Symbol + cooldown pós-stop + venda parcial segura
# CORRIGIDO: Adicionado Tempo de Graça (Grace Period) para evitar fechamento imediato pós-compra

import time
from datetime import datetime

import config as _cfg

from trading import comprar_mercado, vender_mercado, obter_saldo, obter_preco
from memoria import (
    salvar_operacao,
    salvar_posicao,
    carregar_posicoes,
    limpar_posicao,
)
from logger_bot import log_info, log_erro, log_operacao


# ==========================================
# HELPERS
# ==========================================
def _norm_symbol(value):
    if value is None:
        return ""
    # Normaliza para formato com hífen (ex: BTC-USDT)
    s = str(value).strip().upper().replace("/", "")
    if s.endswith("USDT") and not s.endswith("-USDT"):
        return s[:-4] + "-USDT"
    return s


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


def _normalizar_pct(valor, negativo=False):
    v = _safe_float(valor, 0.0)
    if abs(v) > 1.0:
        v = v / 100.0
    if negativo:
        return -abs(v)
    return abs(v)


STOP_LOSS_PERCENTUAL = getattr(_cfg, "STOP_LOSS_PERCENTUAL", -0.02)
TAKE_PROFIT_PERCENTUAL = getattr(_cfg, "TAKE_PROFIT_PERCENTUAL", 0.02)
COOLDOWN_STOP_MINUTOS = _safe_int(getattr(_cfg, "COOLDOWN_STOP_MINUTOS", 30), 30)

_STOP_LOSS_PCT = _normalizar_pct(STOP_LOSS_PERCENTUAL, negativo=True)
_TAKE_PROFIT_PCT = _normalizar_pct(TAKE_PROFIT_PERCENTUAL, negativo=False)
_COOLDOWN_STOP_SEGUNDOS = COOLDOWN_STOP_MINUTOS * 60

# NOVO: Tempo de graça em segundos para ignorar checks de saída logo após a compra
GRACE_PERIOD_SECONDS = 90 


# ==========================================
# TRADER MULTI-SYMBOL
# ==========================================
class TraderTestnet:
    """
    Executa compras e vendas REAIS na testnet (OKX via CCXT).
    Suporta múltiplos símbolos simultaneamente.
    Regra do spot: só vendemos o que temos.
    """

    def __init__(self, client, symbol_padrao, valor_operacao):
        self.client = client
        self.symbol_padrao = _norm_symbol(symbol_padrao) or "BTC-USDT"
        self.valor_operacao = _safe_float(valor_operacao, 100.0)
        self.historico = []
        self.posicoes = {}
        self._cooldowns = {}

        try:
            posicoes_salvas = carregar_posicoes() or {}
        except Exception as e:
            log_erro(f"Falha ao carregar posições salvas: {e}")
            posicoes_salvas = {}

        for key, pos in posicoes_salvas.items():
            symbol = _norm_symbol(
                key
                or (pos.get("simbolo") if isinstance(pos, dict) else None)
                or (pos.get("symbol") if isinstance(pos, dict) else None)
            )

            if not symbol or symbol == "_DEFAULT":
                symbol = self.symbol_padrao

            pos_normalizada = self._normalizar_posicao(pos, symbol)
            if pos_normalizada:
                self.posicoes[symbol] = pos_normalizada

        if self.posicoes:
            log_info(f"📂 {len(self.posicoes)} posição(ões) recuperada(s) do arquivo:")
            for sym, p in self.posicoes.items():
                base = p.get("base") or sym.replace("-USDT", "").replace("USDT", "")
                log_info(
                    f"   {sym}: {_safe_float(p.get('quantidade'), 0):.6f} {base} "
                    f"@ ${_safe_float(p.get('preco_entrada'), 0):.2f}"
                )

    # ==========================================
    # NORMALIZAÇÃO
    # ==========================================
    @staticmethod
    def _normalizar_posicao(posicao, symbol: str):
        if not isinstance(posicao, dict):
            return None

        symbol = _norm_symbol(symbol)
        if not symbol:
            return None

        p = dict(posicao)
        # Extrai o nome da moeda base (ex: BTC de BTC-USDT)
        base = symbol.replace("-USDT", "").replace("USDT", "")

        qtd = _safe_float(p.get("quantidade"), 0.0)
        entrada = _safe_float(p.get("preco_entrada"), 0.0)
        investido = _safe_float(p.get("valor_investido"), 0.0)

        if qtd <= 0 or entrada <= 0:
            return None

        if investido <= 0:
            investido = qtd * entrada

        stop = _safe_float(p.get("stop_loss"), 0.0)
        tp = _safe_float(p.get("take_profit"), 0.0)

        if stop <= 0:
            stop = entrada * (1 + _STOP_LOSS_PCT)

        if tp <= 0:
            tp = entrada * (1 + _TAKE_PROFIT_PCT)

        p["simbolo"] = symbol
        p["symbol"] = symbol
        p["base"] = base
        p["moeda"] = base
        p.setdefault("tipo", "COMPRA")
        p.setdefault("aberta_em", datetime.now().isoformat(timespec="seconds"))
        p["atualizado_em"] = datetime.now().isoformat(timespec="seconds")

        p["quantidade"] = qtd
        p["preco_entrada"] = entrada
        p["valor_investido"] = investido
        p["stop_loss"] = stop
        p["take_profit"] = tp

        return p

    # ==========================================
    # COMPATIBILIDADE
    # ==========================================
    @property
    def symbol(self):
        return self.symbol_padrao

    @property
    def simbolo(self):
        return self.symbol_padrao

    @property
    def moeda(self):
        base = self.symbol_padrao
        return base.replace("-USDT", "").replace("USDT", "")

    @property
    def posicao(self):
        return self.posicoes.get(self.symbol_padrao)

    def tem_posicao(self, symbol=None):
        sym = _norm_symbol(symbol or self.symbol_padrao)
        return sym in self.posicoes and self.posicoes[sym] is not None

    def get_posicao(self, symbol):
        sym = _norm_symbol(symbol)
        return self.posicoes.get(sym)

    def get_todas_posicoes(self):
        return dict(self.posicoes)

    # ==========================================
    # COOLDOWN
    # ==========================================
    def marcar_cooldown(self, symbol: str):
        sym = _norm_symbol(symbol)
        if not sym or _COOLDOWN_STOP_SEGUNDOS <= 0:
            return

        self._cooldowns[sym] = time.time() + _COOLDOWN_STOP_SEGUNDOS
        log_info(
            f"[{sym}] Cooldown ativado por "
            f"{_COOLDOWN_STOP_SEGUNDOS/60:.0f} minutos após stop."
        )

    def em_cooldown(self, symbol: str) -> bool:
        sym = _norm_symbol(symbol)
        expires = self._cooldowns.get(sym, 0)

        if time.time() < expires:
            return True

        if sym in self._cooldowns:
            del self._cooldowns[sym]

        return False

    # ==========================================
    # COMPRAS
    # ==========================================
    def abrir_compra(self, symbol=None):
        sym = _norm_symbol(symbol or self.symbol_padrao)
        base = sym.replace("-USDT", "").replace("USDT", "")

        if self.tem_posicao(sym):
            log_info(f"[{sym}] Já possui posição aberta, ignorando compra")
            return None

        if self.em_cooldown(sym):
            log_info(f"[{sym}] Em cooldown pós-stop. Compra ignorada.")
            return None

        # 1. Envia a ordem inicial
        try:
            ordem_inicial = comprar_mercado(self.client, sym, self.valor_operacao)
        except Exception as e:
            log_erro(f"[{sym}] Exceção ao enviar ordem de compra: {e}")
            return None
        
        if not ordem_inicial:
            log_erro(f"[{sym}] Falha ao enviar ordem de compra (retornou None)")
            return None

        order_id = ordem_inicial.get('id')
        
        # VERIFICAÇÃO CRÍTICA: Se não houver ID, não podemos rastrear. Aborta com segurança.
        if not order_id:
            log_erro(f"[{sym}] Ordem enviada mas SEM ID válido. Não é possível confirmar execução.")
            return None

        # 2. VERIFICAÇÃO ROBUSTA: Espera a OKX confirmar o preenchimento real
        max_retries = 5
        retry_delay = 1.0 
        
        ordem_final = None
        qtd_executada = 0.0
        custo_executado = 0.0

        for i in range(max_retries):
            try:
                # Tenta buscar o status atualizado
                # Nota: Algumas versões do CCXT podem precisar de 'params' extra, 
                # mas para OKX Spot, id + symbol geralmente basta.
                ordem_atual = self.client.fetch_order(id=order_id, symbol=sym)
                
                if not ordem_atual:
                    raise ValueError("fetch_order retornou None/vazio")

                status = str(ordem_atual.get('status', '')).lower()
                qtd_executada = _safe_float(ordem_atual.get('filled'), 0.0)
                custo_executado = _safe_float(ordem_atual.get('cost'), 0.0)

                # Caso Sucesso Total
                if status == 'closed' and qtd_executada > 0:
                    ordem_final = ordem_atual
                    break
                
                # Caso Cancelado/Rejeitado
                elif status in ['canceled', 'cancelled', 'rejected']:
                    log_erro(f"[{sym}] Ordem cancelada/rejeitada pela exchange. Status: {status}")
                    return None
                
                # Caso Parcialmente Preenchida (aceita se tiver qty > 0)
                elif qtd_executada > 0:
                    ordem_final = ordem_atual
                    break
                    
                # Caso Ainda Pendente ('open' ou vazio)
                else:
                    if i < max_retries - 1:
                        time.sleep(retry_delay)
                        
            except Exception as e:
                # Loga o erro específico da consulta para debug futuro
                log_erro(f"[{sym}] Erro ao consultar status da ordem ({i+1}/{max_retries}): {type(e).__name__}: {e}")
                if i < max_retries - 1:
                    time.sleep(retry_delay)
                continue

        # 3. VALIDAÇÃO FINAL ANTES DE REGISTRAR
        if ordem_final is None or qtd_executada <= 0:
            log_erro(f"[{sym}] FALHA CRÍTICA: Ordem enviada mas NÃO confirmada após tentativas. Saldo pode ter sido debitado indevidamente!")
            return None

        if custo_executado <= 0:
            # Fallback: calcula custo estimado pelo preço médio atual
            preco_ref = _safe_float(obter_preco(self.client, sym), 0.0)
            if preco_ref > 0:
                custo_executado = qtd_executada * preco_ref
            else:
                log_erro(f"[{sym}] Não foi possível determinar custo da execução")
                return None

        preco_medio = custo_executado / qtd_executada

        nova_posicao = {
            "simbolo": sym,
            "symbol": sym,
            "base": base,
            "moeda": base,
            "tipo": "COMPRA",
            "quantidade": qtd_executada,
            "preco_entrada": preco_medio,
            "valor_investido": custo_executado,
            "stop_loss": preco_medio * (1 + _STOP_LOSS_PCT),
            "take_profit": preco_medio * (1 + _TAKE_PROFIT_PCT),
            "aberta_em": datetime.now().isoformat(timespec="seconds"),
            "atualizado_em": datetime.now().isoformat(timespec="seconds"),
        }

        self.posicoes[sym] = nova_posicao

        print(f"\n{'=' * 50}")
        print("🟢 COMPRA REAL CONFIRMADA NA TESTNET!")
        print(f"   Símbolo: {sym}")
        print(f"   Quantidade: {qtd_executada:.6f} {base}")
        print(f"   Preço médio: ${preco_medio:.4f}")
        print(f"   Gasto Real: ${custo_executado:.2f}")
        print(f"   Stop Loss: ${nova_posicao['stop_loss']:.4f}")
        print(f"   Take Profit: ${nova_posicao['take_profit']:.4f}")
        print(f"{'=' * 50}\n")

        salvar_posicao(nova_posicao)
        log_operacao("COMPRA", -custo_executado, f"{sym} @ ${preco_medio:.4f}")

        return nova_posicao
    # ==========================================
    # SAÍDA / STOP / TAKE
    # ==========================================
    def verificar_saida(self, preco_atual, symbol=None):
        sym = _norm_symbol(symbol or self.symbol_padrao)
        pos = self.posicoes.get(sym)

        if not pos:
            return None

        # --- NOVA LÓGICA DE TEMPO DE GRAÇA ---
        aberta_em_str = pos.get("aberta_em")
        if aberta_em_str:
            try:
                aberta_em_dt = datetime.fromisoformat(aberta_em_str.replace('Z', '+00:00'))
                agora = datetime.now(opena_em_dt.tzinfo) if aberta_em_dt.tzinfo else datetime.now()
                
                delta_segundos = (agora - aberta_em_dt).total_seconds()
                
                # Ignora checks de stop/take nos primeiros GRACE_PERIOD_SECONDS
                if delta_segundos < GRACE_PERIOD_SECONDS:
                    # Log opcional para debug (comentado para não poluir)
                    # log_info(f"[{sym}] Dentro do grace period ({delta_segundos:.0f}s/{GRACE_PERIOD_SECONDS}s). Ignorando check de saída.")
                    return None 
            except Exception:
                pass # Se der erro na data, segue normal
        # -------------------------------------------

        entrada = _safe_float(pos.get("preco_entrada"), 0.0)
        preco_atual = _safe_float(preco_atual, 0.0)

        if entrada <= 0 or preco_atual <= 0:
            return None

        stop = _safe_float(pos.get("stop_loss"), 0.0)
        take = _safe_float(pos.get("take_profit"), 0.0)

        if stop <= 0:
            stop = entrada * (1 + _STOP_LOSS_PCT)
        if take <= 0:
            take = entrada * (1 + _TAKE_PROFIT_PCT)

        if preco_atual <= stop:
            return "STOP_LOSS"
        if preco_atual >= take:
            return "TAKE_PROFIT"

        return None

    # ==========================================
    # VENDAS
    # ==========================================
    def fechar_venda(self, motivo, symbol=None):
        sym = _norm_symbol(symbol or self.symbol_padrao)
        pos = self.posicoes.get(sym)

        if not pos:
            return None

        base = pos.get("base") or sym.replace("-USDT", "").replace("USDT", "")

        qtd_posicao = _safe_float(pos.get("quantidade"), 0.0)
        investido_total = _safe_float(pos.get("valor_investido"), 0.0)
        entrada = _safe_float(pos.get("preco_entrada"), 0.0)

        if qtd_posicao <= 0 or entrada <= 0:
            log_erro(f"[{sym}] Posição inválida, removendo do controle")
            self.posicoes.pop(sym, None)
            limpar_posicao(sym)
            return None

        if investido_total <= 0:
            investido_total = qtd_posicao * entrada

        qtd_real = _safe_float(obter_saldo(self.client, base), 0.0)

        if qtd_real <= 0:
            operacao_fantasma = {
                "simbolo": sym, "symbol": sym, "base": base, "moeda": base, "tipo": "COMPRA",
                "preco_entrada": entrada, "preco_saida": 0.0, "quantidade": 0.0,
                "quantidade_original": qtd_posicao, "valor_investido": investido_total,
                "variacao_percentual": 0.0, "lucro_prejuizo": 0.0, "motivo_fechamento": "SALDO_ZERO",
                "parcial": False, "observacao": "Posição fantasma: saldo na exchange era zero.",
                "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            }
            self.historico.append(operacao_fantasma)
            salvar_operacao(operacao_fantasma)
            log_erro(f"[{sym}] SALDO ZERO: posição fantasma removida.")
            self.posicoes.pop(sym, None)
            limpar_posicao(sym)
            return operacao_fantasma

        qtd_solicitada = min(qtd_real, qtd_posicao)

        if qtd_solicitada <= 0:
            operacao_invalida = {
                "simbolo": sym, "symbol": sym, "base": base, "moeda": base, "tipo": "COMPRA",
                "preco_entrada": entrada, "preco_saida": 0.0, "quantidade": 0.0,
                "quantidade_original": qtd_posicao, "valor_investido": investido_total,
                "variacao_percentual": 0.0, "lucro_prejuizo": 0.0, "motivo_fechamento": "QUANTIDADE_INVALIDA",
                "parcial": False, "observacao": "Quantidade solicitada para venda ficou zero.",
                "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            }
            self.historico.append(operacao_invalida)
            salvar_operacao(operacao_invalida)
            log_erro(f"[{sym}] QUANTIDADE INVALIDA: posição removida.")
            self.posicoes.pop(sym, None)
            limpar_posicao(sym)
            return operacao_invalida

        ordem = vender_mercado(self.client, sym, qtd_solicitada)
        if not ordem:
            log_erro(f"[{sym}] Falha ao executar venda")
            return None

        # --- MUDANÇA CRÍTICA PARA CCXT ---
        qtd_executada = _safe_float(ordem.get("filled", qtd_solicitada))
        recebido = _safe_float(ordem.get("cost", 0.0))

        if qtd_executada <= 0:
            log_erro(f"[{sym}] Venda executada com quantidade zero")
            return None

        if recebido <= 0:
            preco_ref = _safe_float(obter_preco(self.client, sym), 0.0)
            if preco_ref > 0:
                recebido = qtd_executada * preco_ref
            else:
                log_erro(f"[{sym}] Não foi possível calcular valor recebido da venda")
                return None

        if qtd_posicao > 0:
            proporcao = min(1.0, qtd_executada / qtd_posicao)
            investido_parcial = investido_total * proporcao
        else:
            proporcao = 1.0
            investido_parcial = investido_total

        if investido_parcial <= 0:
            investido_parcial = qtd_executada * entrada

        lucro = recebido - investido_parcial
        variacao_pct = (lucro / investido_parcial) * 100 if investido_parcial > 0 else 0.0
        preco_saida = recebido / qtd_executada if qtd_executada > 0 else 0.0

        fechamento_parcial = qtd_executada < (qtd_posicao * 0.999)

        operacao = {
            "simbolo": sym, "symbol": sym, "base": base, "moeda": base, "tipo": "COMPRA",
            "preco_entrada": entrada, "preco_saida": preco_saida, "quantidade": qtd_executada,
            "quantidade_original": qtd_posicao, "valor_investido": investido_parcial,
            "variacao_percentual": variacao_pct, "lucro_prejuizo": lucro, "motivo_fechamento": motivo,
            "parcial": fechamento_parcial, "data": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        }

        self.historico.append(operacao)
        salvar_operacao(operacao)

        if fechamento_parcial:
            restante = max(0.0, qtd_posicao - qtd_executada)
            investido_restante = max(0.0, investido_total - investido_parcial)

            if restante <= max(1e-12, qtd_posicao * 0.001):
                self.posicoes.pop(sym, None)
                limpar_posicao(sym)
                log_info(f"[{sym}] Fechamento parcial completou posição por resíduo mínimo")
            else:
                pos["quantidade"] = restante
                pos["valor_investido"] = investido_restante
                pos["atualizado_em"] = datetime.now().isoformat(timespec="seconds")
                self.posicoes[sym] = pos
                salvar_posicao(pos)
                log_info(f"[{sym}] Fechamento parcial: vendeu {qtd_executada:.6f}, sobraram {restante:.6f}")
        else:
            self.posicoes.pop(sym, None)
            limpar_posicao(sym)

        if motivo == "STOP_LOSS":
            self.marcar_cooldown(sym)

        emoji = "🟢" if lucro > 0 else "🔴"
        tipo_fechamento = "PARCIAL" if fechamento_parcial else "TOTAL"

        print(f"\n{'=' * 50}")
        print(f"{emoji} VENDA REAL EXECUTADA: {motivo} ({tipo_fechamento})")
        print(f"   Símbolo: {sym}")
        print(f"   Entrada: ${operacao['preco_entrada']:.2f}")
        print(f"   Saída:   ${preco_saida:.2f}")
        print(f"   Quantidade vendida: {qtd_executada:.6f} {base}")
        print(f"   Resultado: ${lucro:+.2f} ({variacao_pct:+.2f}%)")
        print(f"{'=' * 50}\n")

        log_operacao("VENDA", lucro, f"{sym} {motivo} {tipo_fechamento}")

        return operacao

    # ==========================================
    # MONITORAMENTO MULTI-SYMBOL
    # ==========================================
    def verificar_todas_posicoes(self, precos_atuais: dict):
        operacoes_fechadas = []
        if not isinstance(precos_atuais, dict):
            return operacoes_fechadas

        for sym in list(self.posicoes.keys()):
            preco = precos_atuais.get(sym)
            if preco is None:
                continue
            motivo = self.verificar_saida(preco, symbol=sym)
            if motivo:
                op = self.fechar_venda(motivo, symbol=sym)
                if op:
                    operacoes_fechadas.append(op)
        return operacoes_fechadas

    def mostrar_status_multi(self, precos_atuais: dict = None):
        if not self.posicoes:
            print("   ⏸️ Nenhuma posição aberta")
            return

        print(f"   📊 {len(self.posicoes)} posição(ões) aberta(s):")
        for sym, pos in self.posicoes.items():
            base = pos.get("base") or sym.replace("-USDT", "").replace("USDT", "")
            qtd = _safe_float(pos.get("quantidade"), 0.0)
            entrada = _safe_float(pos.get("preco_entrada"), 0.0)
            linha = f"      🎯 {sym}: {qtd:.6f} {base} @ ${entrada:.2f}"

            if isinstance(precos_atuais, dict):
                preco = _safe_float(precos_atuais.get(sym), 0.0)
                if preco > 0 and entrada > 0 and qtd > 0:
                    variacao = (preco - entrada) / entrada * 100
                    pnl = (preco - entrada) * qtd
                    linha += f" | PnL: ${pnl:+.2f} ({variacao:+.2f}%)"
            print(linha)

    def fechar_todas_posicoes(self, motivo="ENCERRAMENTO"):
        ops = []
        for sym in list(self.posicoes.keys()):
            op = self.fechar_venda(motivo, symbol=sym)
            if op:
                ops.append(op)
        return ops