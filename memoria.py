# memoria.py
# Memória permanente do bot (salva operações em arquivo)

import json
import os
from datetime import datetime

ARQUIVO = "historico_operacoes.json"


def salvar_operacao(operacao):
    """Adiciona uma operação ao arquivo de histórico"""
    historico = carregar_historico()
    
    registro = dict(operacao)
    registro["data"] = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    historico.append(registro)
    
    with open(ARQUIVO, "w", encoding="utf-8") as f:
        json.dump(historico, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 Operação salva em {ARQUIVO}")


def carregar_historico():
    """Lê o histórico do arquivo"""
    if not os.path.exists(ARQUIVO):
        return []
    try:
        with open(ARQUIVO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erro ao ler histórico: {e}")
        return []


def resumo_historico():
    """Calcula estatísticas do histórico"""
    historico = carregar_historico()
    if not historico:
        return None
    
    total = len(historico)
    acertos = sum(1 for op in historico if op["lucro_prejuizo"] > 0)
    lucro_total = sum(op["lucro_prejuizo"] for op in historico)
    taxa = (acertos / total) * 100
    
    return {
        "total": total,
        "acertos": acertos,
        "erros": total - acertos,
        "lucro_total": lucro_total,
        "taxa_acerto": taxa
    }
# === MEMÓRIA DE POSIÇÃO (AULA 10) ===
ARQUIVO_POSICAO = "posicao_aberta.json"


def salvar_posicao(posicao):
    """Salva a posição aberta em arquivo"""
    with open(ARQUIVO_POSICAO, "w", encoding="utf-8") as f:
        json.dump(posicao, f, ensure_ascii=False, indent=2)
    print(f"   💾 Posição aberta salva em {ARQUIVO_POSICAO}")


def carregar_posicao():
    """Carrega a posição aberta, se existir"""
    if not os.path.exists(ARQUIVO_POSICAO):
        return None
    try:
        with open(ARQUIVO_POSICAO, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️ Erro ao carregar posição: {e}")
        return None


def limpar_posicao():
    """Apaga o arquivo de posição (posição fechada)"""
    if os.path.exists(ARQUIVO_POSICAO):
        os.remove(ARQUIVO_POSICAO)
        print(f"   🗑️ Arquivo de posição apagado")