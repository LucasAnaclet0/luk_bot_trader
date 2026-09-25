# trader_testnet.py
# Executa ordens reais na Binance Testnet

from trading import comprar_mercado, vender_mercado, obter_saldo, obter_preco
from memoria import salvar_operacao, salvar_posicao, carregar_posicao, limpar_posicao
from config import STOP_LOSS_PERCENTUAL, TAKE_PROFIT_PERCENTUAL


class TraderTestnet:
    """
    Executa compras e vendas REAIS na testnet.
    Regra do spot: só vendemos o que temos.
    """
    
    def __init__(self, client, simbolo, valor_operacao):
        self.client = client
        self.simbolo = simbolo
        self.valor_operacao = valor_operacao
        self.moeda = simbolo.replace("USDT", "")
        self.posicao = None
        self.historico = []
        
        # AULA 10: recupera posição se o bot foi reiniciado
        posicao_salva = carregar_posicao()
        if posicao_salva:
            self.posicao = posicao_salva
            print(f"\n📂 POSIÇÃO RECUPERADA DO ARQUIVO:")
            print(f"   {posicao_salva['quantidade']:.6f} @ ${posicao_salva['preco_entrada']:.2f}")
    
    def tem_posicao(self):
        """Verifica se tem posição aberta"""
        return self.posicao is not None
    
    def abrir_compra(self):
        """Executa compra real na testnet"""
        if self.tem_posicao():
            return None
        
        ordem = comprar_mercado(self.client, self.simbolo, self.valor_operacao)
        if not ordem:
            return None
        
        qtd = float(ordem.get('executedQty', 0))
        gasto = float(ordem.get('cummulativeQuoteQty', 0))
        
        if qtd <= 0:
            print("⚠️ Ordem executada com quantidade zero.")
            return None
        
        if gasto <= 0:
            gasto = self.valor_operacao
        
        preco_medio = gasto / qtd
        
        self.posicao = {
            "tipo": "COMPRA",
            "quantidade": qtd,
            "preco_entrada": preco_medio,
            "valor_investido": gasto,
            "stop_loss": preco_medio * (1 + STOP_LOSS_PERCENTUAL),
            "take_profit": preco_medio * (1 + TAKE_PROFIT_PERCENTUAL)
        }
        
        print(f"\n{'='*50}")
        print(f"🟢 COMPRA REAL EXECUTADA NA TESTNET!")
        print(f"   Quantidade: {qtd:.6f} {self.moeda}")
        print(f"   Preço médio: ${preco_medio:.2f}")
        print(f"   Gasto: ${gasto:.2f}")
        print(f"   Stop Loss: ${self.posicao['stop_loss']:.2f}")
        print(f"   Take Profit: ${self.posicao['take_profit']:.2f}")
        print(f"{'='*50}\n")
        
        salvar_posicao(self.posicao)
        
        return self.posicao
    
    def verificar_saida(self, preco_atual):
        """Verifica se deve fechar por stop loss ou take profit"""
        if not self.tem_posicao():
            return None
        
        variacao = (preco_atual - self.posicao["preco_entrada"]) / self.posicao["preco_entrada"]
        
        if variacao <= STOP_LOSS_PERCENTUAL:
            return "STOP_LOSS"
        if variacao >= TAKE_PROFIT_PERCENTUAL:
            return "TAKE_PROFIT"
        return None
    
    def fechar_venda(self, motivo):
        """Vende TUDO que tem e registra o resultado"""
        if not self.tem_posicao():
            return None
        
        qtd_real = obter_saldo(self.client, self.moeda)
        if qtd_real <= 0:
            self.posicao = None
            limpar_posicao()
            return None
        
        ordem = vender_mercado(self.client, self.simbolo, qtd_real)
        if not ordem:
            return None
        
        recebido = float(ordem.get('cummulativeQuoteQty', 0))
        if recebido <= 0:
            recebido = qtd_real * obter_preco(self.client, self.simbolo)
        
        investido = self.posicao["valor_investido"]
        lucro = recebido - investido
        variacao_pct = (lucro / investido) * 100 if investido > 0 else 0
        preco_saida = recebido / qtd_real if qtd_real > 0 else 0
        
        operacao = {
            "tipo": "COMPRA",
            "preco_entrada": self.posicao["preco_entrada"],
            "preco_saida": preco_saida,
            "quantidade": qtd_real,
            "valor_investido": investido,
            "variacao_percentual": variacao_pct,
            "lucro_prejuizo": lucro,
            "motivo_fechamento": motivo
        }
        self.historico.append(operacao)
        salvar_operacao(operacao)
        self.posicao = None
        limpar_posicao()
        
        emoji = "🟢" if lucro > 0 else "🔴"
        print(f"\n{'='*50}")
        print(f"{emoji} VENDA REAL EXECUTADA: {motivo}")
        print(f"   Entrada: ${operacao['preco_entrada']:.2f}")
        print(f"   Saída:   ${preco_saida:.2f}")
        print(f"   Resultado: ${lucro:+.2f} ({variacao_pct:+.2f}%)")
        print(f"{'='*50}\n")
        
        return operacao