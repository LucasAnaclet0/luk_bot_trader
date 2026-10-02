# limpar_dados.py
# Higiene de estado v2: backup + remove fantasmas da Binance (histórico E posições).
# RODE COM O BOT PARADO. Preserva o offset do Telegram.
# Undo point canônico = a PRIMEIRA pasta backup_dados_* criada (tem o estado original).
import json
import shutil
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
KEYS_POSICAO = {"quantidade", "preco_entrada", "simbolo", "symbol", "valor_investido"}
KEYS_HISTORICO = {"lucro_prejuizo", "motivo_fechamento", "variacao_percentual", "preco_saida"}


def _carregar(p: Path):
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Não consegui ler {p.name}: {e}  (preservando)")
        return None


def _eh_dict_posicao(d) -> bool:
    return isinstance(d, dict) and bool(KEYS_POSICAO & set(d))


def _classificar(dado):
    # offset do telegram -> preservar sempre
    if isinstance(dado, dict) and "offset" in dado:
        return "OFFSET"
    if isinstance(dado, int):
        return "OFFSET"

    # container novo: {"schema_version":..,"positions":{symbol:pos,...}}
    if isinstance(dado, dict) and isinstance(dado.get("positions"), dict):
        inner = dado["positions"]
        if not inner or all(_eh_dict_posicao(v) for v in inner.values()):
            return "POSICOES_CONTAINER"

    # posição única legada: dict plano de campos de posição
    if _eh_dict_posicao(dado):
        return "POSICAO_UNICA"

    # posições antigas: dict {symbol: posicao} no nível raiz
    if isinstance(dado, dict) and dado:
        vals = list(dado.values())
        if all(isinstance(v, dict) for v in vals) and any(_eh_dict_posicao(v) for v in vals):
            return "POSICOES_CONTAINER"

    # histórico: lista de dicts de operação fechada
    if isinstance(dado, list) and dado and all(isinstance(x, dict) for x in dado):
        if any(KEYS_HISTORICO & set(x) for x in dado):
            return "HISTORICO"

    return "DESCONHECIDO"


def main():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = RAIZ / f"backup_dados_{ts}"
    backup.mkdir(parents=True, exist_ok=True)

    jsons = sorted(RAIZ.glob("*.json"))
    if not jsons:
        print("ℹ️  Nenhum .json encontrado na raiz. Nada a limpar.")
        return

    print(f"📦 Backup em: {backup.name}/")
    print("─" * 56)

    acoes = {"POSICOES_CONTAINER": 0, "POSICAO_UNICA": 0, "HISTORICO": 0,
             "OFFSET": 0, "DESCONHECIDO": 0}
    fantasmas = set()

    for p in jsons:
        dado = _carregar(p)
        if dado is None:
            continue
        shutil.copy2(p, backup / p.name)   # backup ANTES de qualquer remoção/zero

        tipo = _classificar(dado)
        acoes[tipo] += 1

        if tipo == "HISTORICO":
            n = len(dado) if isinstance(dado, list) else 0
            for x in (dado or []):
                if isinstance(x, dict):
                    s = str(x.get("simbolo") or x.get("symbol") or "").upper()
                    if s:
                        fantasmas.add(s)
            with p.open("w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"🧹 {p.name:<28} -> HISTORICO  ({n} trades arquivados, começa do zero)")

        elif tipo in ("POSICOES_CONTAINER", "POSICAO_UNICA"):
            # coleta símbolos fantasma antes de remover
            if tipo == "POSICOES_CONTAINER":
                inner = dado.get("positions", dado) if isinstance(dado.get("positions"), dict) else dado
                for k, v in (inner.items() if isinstance(inner, dict) else []):
                    fantasmas.add(str(k).upper())
                    if isinstance(v, dict):
                        s = str(v.get("simbolo") or v.get("symbol") or "").upper()
                        if s:
                            fantasmas.add(s)
            else:
                s = str(dado.get("simbolo") or dado.get("symbol") or "").upper()
                if s:
                    fantasmas.add(s)
            p.unlink()   # remove da raiz; loader vê ausência -> estado vazio (seguro)
            print(f"🗑️  {p.name:<28} -> {tipo:<18} (removido da raiz; backup salvo)")

        elif tipo == "OFFSET":
            print(f"🔒 {p.name:<28} -> OFFSET     (preservado, não reprocessa Telegram)")
        else:
            print(f"❓ {p.name:<28} -> DESCONHECIDO (preservado por segurança)")

    print("─" * 56)
    print(f"✅ Resumo: contêiner_pos={acoes['POSICOES_CONTAINER']} | "
          f"pos_unica={acoes['POSICAO_UNICA']} | historico={acoes['HISTORICO']} | "
          f"offset={acoes['OFFSET']} | outros={acoes['DESCONHECIDO']}")
    if fantasmas:
        print(f"👻 Fantasmas da Binance eliminados: {', '.join(sorted(fantasmas))}")
        print("   (note SOLUSDT vs SOL-USDT: a duplicação de convenção morreu aqui)")
    print(f"💾 Undo point = a PRIMEIRA pasta backup_dados_* (estado original completo).")


if __name__ == "__main__":
    main()