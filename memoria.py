# memoria.py
"""
Memória permanente do bot - versão profissional.

Melhorias:
- Escrita atômica (evita corromper JSON)
- Backup automático (.bak)
- Recuperação de arquivo corrompido
- Thread safety
- Suporte a múltiplas posições simultâneas
- Compatibilidade retroativa com posicao_aberta.json
- Sanitização de valores numéricos
- Estatísticas por símbolo
"""

import json
import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional


# ==========================================
# CAMINHOS E CONSTANTES
# ==========================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ARQUIVO = os.path.join(BASE_DIR, "historico_operacoes.json")
POSICOES_ARQUIVO = os.path.join(BASE_DIR, "posicoes_abertas.json")
LEGACY_POSICAO_ARQUIVO = os.path.join(BASE_DIR, "posicao_aberta.json")

MAX_HISTORICO = 5000
SCHEMA_VERSION = 2

_IO_LOCK = threading.RLock()

_NUMERIC_FIELDS_OPERACAO = (
    "preco_entrada",
    "preco_saida",
    "quantidade",
    "valor_investido",
    "variacao_percentual",
    "lucro_prejuizo",
)

_NUMERIC_FIELDS_POSICAO = (
    "quantidade",
    "preco_entrada",
    "valor_investido",
    "stop_loss",
    "take_profit",
)


# ==========================================
# UTILITÁRIOS INTERNOS
# ==========================================
def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _upper_symbol(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace("/", "")


def _atomic_write_json(path: str, data: Any) -> None:
    """
    Escrita atômica:
    1. escreve em arquivo temporário
    2. faz backup do anterior
    3. substitui o original somente se tudo der certo
    """
    tmp_path = path + ".tmp"

    try:
        if os.path.exists(path):
            try:
                shutil.copy2(path, path + ".bak")
            except Exception:
                pass

        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            f.flush()
            try:
                os.fsync(f.fileno())
            except Exception:
                pass

        os.replace(tmp_path, path)

    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        raise


def _read_json(path: str, default: Any) -> Any:
    if not os.path.exists(path):
        return default

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erro ao ler {os.path.basename(path)}: {e}")
        return None


def _load_json_with_backup(path: str, default: Any) -> Any:
    """
    Tenta ler o arquivo principal.
    Se falhar, tenta o backup.
    Se ambos falharem, isola o arquivo corrompido.
    """
    data = _read_json(path, None)
    if data is not None:
        return data

    bak_path = path + ".bak"
    data = _read_json(bak_path, None)
    if data is not None:
        print(f"♻️ Recuperando backup de {os.path.basename(path)}")
        return data

    if os.path.exists(path):
        corrupt_path = f"{path}.corrupt.{int(time.time())}"
        try:
            os.replace(path, corrupt_path)
            print(f"🗑️ Arquivo corrompido movido para {os.path.basename(corrupt_path)}")
        except Exception:
            pass

    return default


# ==========================================
# HISTÓRICO DE OPERAÇÕES
# ==========================================
def _sanitizar_operacao(operacao: Dict[str, Any]) -> Dict[str, Any]:
    op = dict(operacao or {})

    symbol = _upper_symbol(
        op.get("simbolo") or op.get("symbol") or op.get("par")
    )
    if symbol:
        op["simbolo"] = symbol

    op.setdefault("id", uuid.uuid4().hex[:12])
    op.setdefault("data", datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    op.setdefault("criado_em", _now_iso())
    op["schema_version"] = SCHEMA_VERSION

    for field in _NUMERIC_FIELDS_OPERACAO:
        if field in op:
            op[field] = _to_float(op[field], 0.0)

    if "lucro_prejuizo" not in op:
        op["lucro_prejuizo"] = 0.0

    return op


def _load_historico_raw() -> List[Dict[str, Any]]:
    data = _load_json_with_backup(ARQUIVO, [])

    if isinstance(data, dict):
        data = data.get("operacoes", [])

    if not isinstance(data, list):
        return []

    return [item for item in data if isinstance(item, dict)]


def salvar_operacao(operacao: Dict[str, Any]) -> Dict[str, Any]:
    """
    Adiciona uma operação fechada ao histórico.
    Agora com escrita atômica, backup e sanitização.
    """
    with _IO_LOCK:
        historico = _load_historico_raw()
        registro = _sanitizar_operacao(operacao)
        historico.append(registro)

        if len(historico) > MAX_HISTORICO:
            historico = historico[-MAX_HISTORICO:]

        _atomic_write_json(ARQUIVO, historico)

        print(f"   💾 Operação salva em {os.path.basename(ARQUIVO)}")
        return registro


def carregar_historico() -> List[Dict[str, Any]]:
    """Lê o histórico do arquivo com segurança."""
    with _IO_LOCK:
        return _load_historico_raw()


def resumo_historico() -> Optional[Dict[str, Any]]:
    """
    Calcula estatísticas do histórico.
    Mantém compatibilidade com o formato antigo e adiciona métricas extras.
    """
    with _IO_LOCK:
        historico = _load_historico_raw()

    if not historico:
        return None

    total = len(historico)
    acertos = 0
    erros = 0
    neutros = 0

    lucro_total = 0.0
    ganho_bruto = 0.0
    perda_bruta = 0.0

    melhor = None
    pior = None

    for op in historico:
        lucro = _to_float(op.get("lucro_prejuizo", 0), 0.0)
        lucro_total += lucro

        if lucro > 0:
            acertos += 1
            ganho_bruto += lucro
        elif lucro < 0:
            erros += 1
            perda_bruta += abs(lucro)
        else:
            neutros += 1

        if melhor is None or lucro > _to_float(melhor.get("lucro_prejuizo", 0), 0.0):
            melhor = op

        if pior is None or lucro < _to_float(pior.get("lucro_prejuizo", 0), 0.0):
            pior = op

    taxa_acerto = (acertos / total * 100) if total > 0 else 0.0

    trades_validos = acertos + erros
    win_rate_valido = (acertos / trades_validos * 100) if trades_validos > 0 else 0.0

    if perda_bruta > 0:
        profit_factor = ganho_bruto / perda_bruta
    elif ganho_bruto > 0:
        profit_factor = 999.0
    else:
        profit_factor = 0.0

    media_ganho = ganho_bruto / acertos if acertos > 0 else 0.0
    media_perda = perda_bruta / erros if erros > 0 else 0.0

    return {
        "total": total,
        "acertos": acertos,
        "erros": erros,
        "neutros": neutros,
        "lucro_total": lucro_total,
        "taxa_acerto": taxa_acerto,
        "win_rate_valido": win_rate_valido,
        "ganho_bruto": ganho_bruto,
        "perda_bruta": perda_bruta,
        "profit_factor": profit_factor,
        "media_ganho": media_ganho,
        "media_perda": media_perda,
        "melhor_operacao": melhor,
        "pior_operacao": pior,
    }


def resumo_por_simbolo() -> Dict[str, Dict[str, Any]]:
    """
    Retorna estatísticas agrupadas por símbolo.
    Útil para descobrir quais criptos o bot opera melhor.
    """
    with _IO_LOCK:
        historico = _load_historico_raw()

    grupos: Dict[str, List[Dict[str, Any]]] = {}

    for op in historico:
        symbol = _upper_symbol(op.get("simbolo")) or "SEM_SIMBOLO"
        grupos.setdefault(symbol, []).append(op)

    resumo: Dict[str, Dict[str, Any]] = {}

    for symbol, ops in grupos.items():
        total = len(ops)
        acertos = 0
        erros = 0
        lucro_total = 0.0

        for op in ops:
            lucro = _to_float(op.get("lucro_prejuizo", 0), 0.0)
            lucro_total += lucro
            if lucro > 0:
                acertos += 1
            elif lucro < 0:
                erros += 1

        taxa = (acertos / total * 100) if total > 0 else 0.0

        resumo[symbol] = {
            "total": total,
            "acertos": acertos,
            "erros": erros,
            "lucro_total": lucro_total,
            "taxa_acerto": taxa,
        }

    return resumo


# ==========================================
# POSIÇÕES ABERTAS - MULTI-SYMBOL
# ==========================================
def _infer_symbol(posicao: Dict[str, Any]) -> str:
    if not isinstance(posicao, dict):
        return "_default"

    symbol = _upper_symbol(
        posicao.get("simbolo")
        or posicao.get("symbol")
        or posicao.get("par")
    )
    if symbol:
        return symbol

    moeda = _upper_symbol(posicao.get("moeda"))
    if moeda:
        return f"{moeda}USDT"

    return "_default"


def _sanitizar_posicao(posicao: Dict[str, Any], touch: bool = False) -> Dict[str, Any]:
    p = dict(posicao or {})

    symbol = _infer_symbol(p)
    p["simbolo"] = symbol
    p.setdefault("tipo", "COMPRA")
    p.setdefault("aberta_em", _now_iso())

    if touch or "atualizado_em" not in p:
        p["atualizado_em"] = _now_iso()

    for field in _NUMERIC_FIELDS_POSICAO:
        p[field] = _to_float(p.get(field), 0.0)

    return p


def _choose_legacy_position(positions: Dict[str, Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Escolhe uma posição para manter compatibilidade com o arquivo antigo
    posicao_aberta.json.
    """
    if not positions:
        return None

    if "_default" in positions:
        return positions["_default"]

    if len(positions) == 1:
        return next(iter(positions.values()))

    try:
        return max(
            positions.values(),
            key=lambda x: str(x.get("atualizado_em", ""))
        )
    except Exception:
        return next(iter(positions.values()))


def _save_positions_raw(positions: Dict[str, Dict[str, Any]]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "updated_at": _now_iso(),
        "positions": positions,
    }

    _atomic_write_json(POSICOES_ARQUIVO, payload)

    legacy = _choose_legacy_position(positions)

    if legacy is not None:
        try:
            _atomic_write_json(LEGACY_POSICAO_ARQUIVO, legacy)
        except Exception as e:
            print(f"⚠️ Falha ao atualizar arquivo legado de posição: {e}")
    else:
        if os.path.exists(LEGACY_POSICAO_ARQUIVO):
            try:
                os.remove(LEGACY_POSICAO_ARQUIVO)
            except Exception:
                pass


def _load_positions_raw() -> Dict[str, Dict[str, Any]]:
    data = _load_json_with_backup(POSICOES_ARQUIVO, {})
    positions: Dict[str, Any] = {}

    if isinstance(data, dict):
        if isinstance(data.get("positions"), dict):
            positions = data["positions"]
        elif data and all(isinstance(v, dict) for v in data.values()):
            positions = data

    # Migração automática do arquivo antigo, se necessário
    if not positions and os.path.exists(LEGACY_POSICAO_ARQUIVO):
        legacy = _read_json(LEGACY_POSICAO_ARQUIVO, None)
        if isinstance(legacy, dict):
            p = _sanitizar_posicao(legacy, touch=False)
            positions[p["simbolo"]] = p

    clean: Dict[str, Dict[str, Any]] = {}

    for key, value in positions.items():
        if not isinstance(value, dict):
            continue

        p = _sanitizar_posicao(value, touch=False)

        # Se a chave tiver um símbolo melhor que o interno, usa a chave
        if p["simbolo"] == "_default" and key and key != "_default":
            p["simbolo"] = _upper_symbol(key) or "_default"

        clean[p["simbolo"]] = p

    return clean


def salvar_posicao(posicao: Dict[str, Any]) -> Dict[str, Any]:
    """
    Salva/atualiza uma posição aberta.
    Agora suporta múltiplos símbolos simultaneamente.
    """
    with _IO_LOCK:
        p = _sanitizar_posicao(posicao, touch=True)
        positions = _load_positions_raw()
        positions[p["simbolo"]] = p
        _save_positions_raw(positions)

        print(f"   💾 Posição salva: {p['simbolo']}")
        return p


def carregar_posicao(simbolo: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Carrega uma posição específica.
    Se nenhum símbolo for informado, mantém comportamento antigo:
    - retorna _default se existir
    - retorna a única posição se houver só uma
    - retorna a mais recente se houver várias
    """
    with _IO_LOCK:
        positions = _load_positions_raw()

    if not positions:
        return None

    if simbolo is not None:
        sym = _upper_symbol(simbolo)
        return positions.get(sym)

    return _choose_legacy_position(positions)


def carregar_posicoes() -> Dict[str, Dict[str, Any]]:
    """
    Carrega todas as posições abertas.
    Esta é a função correta para o modo multi-symbol.
    """
    with _IO_LOCK:
        return _load_positions_raw()


def limpar_posicao(simbolo: Optional[str] = None) -> bool:
    """
    Remove uma posição aberta do arquivo.

    Importante:
    - Se símbolo for informado, remove só aquela posição.
    - Se símbolo for None:
        * remove '_default', se existir
        * remove a única posição, se houver só uma
        * NÃO apaga todas as posições por segurança
    """
    with _IO_LOCK:
        positions = _load_positions_raw()

        if not positions:
            return False

        removed = False

        if simbolo is not None:
            sym = _upper_symbol(simbolo)
            if sym in positions:
                del positions[sym]
                removed = True
        else:
            if "_default" in positions:
                del positions["_default"]
                removed = True
            elif len(positions) == 1:
                positions.clear()
                removed = True
            else:
                print(
                    "⚠️ limpar_posicao() chamado sem símbolo com múltiplas posições abertas. "
                    "Nenhuma posição foi removida. Use limpar_posicao(simbolo)."
                )
                return False

        _save_positions_raw(positions)

        if removed:
            if simbolo:
                print(f"   🗑️ Posição removida: {simbolo}")
            else:
                print("   🗑️ Posição removida")

        return removed


def limpar_todas_posicoes() -> None:
    """Remove todas as posições abertas. Use com cuidado."""
    with _IO_LOCK:
        _save_positions_raw({})
        print("   🗑️ Todas as posições abertas foram removidas")


def get_posicao(simbolo: str) -> Optional[Dict[str, Any]]:
    """Alias amigável para carregar_posicao(simbolo)."""
    return carregar_posicao(simbolo)