# gerenciador.py
# Sistema de gerenciamento de posições e risco
from memoria import salvar_operacao
from datetime import datetime
from config import (
    CAPITAL_INICIAL, 
    RISCO_POR_OPERACAO, 
    STOP_LOSS_PERCENTUAL, 
    TAKE_PROFIT_PERCENTUAL,
    LIMITE_PERDA_DIARIA
)


class GerenciadorPosicoes:
    """Simula operações de compra e venda (paper trading)."""
    
    def __init__(self):
        self.capital = CAPITAL_INICIAL
        self.posicao_aberta = None
        self.historico = []
        self.perda_do_dia = 0
        self.lucro_do_dia = 0
        self.data_atual = datetime.now().date()
    
    def resetar_dia(self):
        """Reseta contadores diários"""
        self.perda_do_dia = 0
        self.lucro_do_dia = 0
        self.data_atual = datetime.now().date()
    
    def verificar_novo_dia(self):
        """Verifica se virou o dia e reseta contadores"""
        hoje = datetime.now().date()
        if hoje != self.data_atual:
            print("🌅 Novo dia detectado. Resetando contadores.")
            self.resetar_dia()
    
    def pode_operar(self):
        """Verifica se o bot pode abrir nova posição"""
        if self.posicao_aberta is not None:
            return False, "Já existe uma posição aberta"
        
        if self.perda_do_dia >= LIMITE_PERDA_DIARIA:
            return False, f"Limite de perda diária atingido (${self.perda_do_dia:.2f})"
        
        if self.capital <= 0:
            return False, "Sem capital disponível"
        
        return True, "OK"
    
    def calcular_tamanho_posicao(self, preco):
        """Calcula quanto investir baseado no risco definido"""
        valor_em_risco = self.capital * RISCO_POR_OPERACAO
        tamanho = valor_em_risco / abs(STOP_LOSS_PERCENTUAL)
        
        maximo = self.capital * 0.10
        tamanho = min(tamanho, maximo)
        
        quantidade = tamanho / preco
        
        return {
            "valor_total": tamanho,
            "quantidade": quantidade,
            "preco_entrada": preco
        }
    
    def abrir_posicao(self, tipo, preco):
        """Abre uma posição simulada"""
        self.verificar_novo_dia()
        
        pode, motivo = self.pode_operar()
        if not pode:
            print(f"⚠️ Não pode operar: {motivo}")
            return None
        
        tamanho = self.calcular_tamanho_posicao(preco)
        
        self.posicao_aberta = {
            "tipo": tipo,
            "preco_entrada": preco,
            "quantidade": tamanho["quantidade"],
            "valor_investido": tamanho["valor_total"],
            "data_abertura": datetime.now(),
            "stop_loss": preco * (1 + STOP_LOSS_PERCENTUAL),
            "take_profit": preco * (1 + TAKE_PROFIT_PERCENTUAL)
        }
        
        print(f"\n{'='*50}")
        print(f"🟢 POSIÇÃO ABERTA: {tipo}")
        print(f"   Preço de entrada: ${preco:.2f}")
        print(f"   Quantidade: {tamanho['quantidade']:.6f}")
        print(f"   Valor investido: ${tamanho['valor_total']:.2f}")
        print(f"   Stop Loss: ${self.posicao_aberta['stop_loss']:.2f}")
        print(f"   Take Profit: ${self.posicao_aberta['take_profit']:.2f}")
        print(f"{'='*50}\n")
        
        return self.posicao_aberta
    
    def verificar_posicao(self, preco_atual):
        """Verifica se a posição aberta deve ser fechada"""
        if self.posicao_aberta is None:
            return False, None, 0
        
        posicao = self.posicao_aberta
        preco_entrada = posicao["preco_entrada"]
        
        variacao = (preco_atual - preco_entrada) / preco_entrada
        
        if variacao <= STOP_LOSS_PERCENTUAL:
            lucro = posicao["valor_investido"] * variacao
            return True, "STOP_LOSS", lucro
        
        if variacao >= TAKE_PROFIT_PERCENTUAL:
            lucro = posicao["valor_investido"] * variacao
            return True, "TAKE_PROFIT", lucro
        
        return False, None, 0
    
    def fechar_posicao(self, preco, motivo):
        """Fecha a posição atual e calcula lucro/prejuízo"""
        if self.posicao_aberta is None:
            return None
        
        posicao = self.posicao_aberta
        preco_entrada = posicao["preco_entrada"]
        valor_investido = posicao["valor_investido"]
        
        variacao = (preco - preco_entrada) / preco_entrada
        lucro_prejuizo = valor_investido * variacao
        
        self.capital += lucro_prejuizo
        
        if lucro_prejuizo > 0:
            self.lucro_do_dia += lucro_prejuizo
        else:
            self.perda_do_dia += abs(lucro_prejuizo)
        
        operacao = {
            "tipo": posicao["tipo"],
            "preco_entrada": preco_entrada,
            "preco_saida": preco,
            "quantidade": posicao["quantidade"],
            "valor_investido": valor_investido,
            "variacao_percentual": variacao * 100,
            "lucro_prejuizo": lucro_prejuizo,
            "motivo_fechamento": motivo,
            "data_abertura": posicao["data_abertura"],
            "data_fechamento": datetime.now()
        }
        self.historico.append(operacao)
        salvar_operacao(operacao)        
        
        self.posicao_aberta = None
        
        emoji = "🟢" if lucro_prejuizo > 0 else "🔴"
        print(f"\n{'='*50}")
        print(f"{emoji} POSIÇÃO FECHADA: {motivo}")
        print(f"   Preço de entrada: ${preco_entrada:.2f}")
        print(f"   Preço de saída: ${preco:.2f}")
        print(f"   Variação: {variacao*100:+.2f}%")
        print(f"   Lucro/Prejuízo: ${lucro_prejuizo:+.2f}")
        print(f"   Capital atual: ${self.capital:.2f}")
        print(f"{'='*50}\n")
        
        return operacao
    
    def mostrar_status(self):
        """Mostra status atual do gerenciador"""
        print(f"\n📊 STATUS DO GERENCIADOR:")
        print(f"   💰 Capital: ${self.capital:.2f}")
        print(f"   📈 Lucro hoje: ${self.lucro_do_dia:+.2f}")
        print(f"   📉 Perda hoje: ${self.perda_do_dia:.2f}")
        print(f"   📋 Operações: {len(self.historico)}")
        
        if self.posicao_aberta:
            print(f"   🎯 Posição aberta: {self.posicao_aberta['tipo']} em ${self.posicao_aberta['preco_entrada']:.2f}")
        else:
            print(f"   ⏸️ Nenhuma posição aberta")