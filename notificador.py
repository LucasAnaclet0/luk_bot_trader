# notificador.py
# Sistema de notificações via Telegram

import requests


class NotificadorTelegram:
    """
    Envia notificações pro Telegram quando o bot detecta sinais.
    
    📱 Como funciona:
    - Bot detecta sinal de COMPRA → te avisa no celular
    - Bot detecta sinal de VENDA → te avisa no celular
    - Bot abre/fecha posição → te avisa no celular
    """
    
    def __init__(self, token, chat_id):
        """
        Inicializa o notificador.
        
        Args:
            token: token do bot (pegou do @BotFather)
            chat_id: seu ID no Telegram (pegou do @userinfobot)
        """
        self.token = token
        self.chat_id = chat_id
        self.url_base = f"https://api.telegram.org/bot{token}"
        self.ativado = True  # Pode desativar se quiser
    
    def enviar_mensagem(self, mensagem):
        """
        Envia uma mensagem pro seu Telegram.
        
        Args:
            mensagem: texto da mensagem
        
        Returns:
            bool: True se enviou, False se deu erro
        """
        if not self.ativado:
            return False
        
        url = f"{self.url_base}/sendMessage"
        dados = {
            "chat_id": self.chat_id,
            "text": mensagem,
            "parse_mode": "Markdown"  # Permite negrito, etc
        }
        
        try:
            resposta = requests.post(url, json=dados, timeout=10)
            if resposta.status_code == 200:
                print("   📱 Notificação enviada pro Telegram")
                return True
            else:
                print(f"   ⚠️ Erro ao enviar notificação: {resposta.text}")
                return False
        except Exception as e:
            print(f"   ⚠️ Erro de conexão com Telegram: {e}")
            return False
    
    def notificar_sinal(self, sinal, score, preco):
        """
        Notifica quando detecta um sinal de compra/venda.
        
        Args:
            sinal: "COMPRA" ou "VENDA"
            score: score de confiança
            preco: preço atual
        """
        if sinal == "COMPRA":
            emoji = "🟢"
            texto = "SINAL DE COMPRA DETECTADO!"
        elif sinal == "VENDA":
            emoji = "🔴"
            texto = "SINAL DE VENDA DETECTADO!"
        else:
            return False
        
        mensagem = f"""
{emoji} *{texto}*

📊 Par: *BTCUSDT*
💰 Preço: *${preco:.2f}*
🎯 Score: *{score:.1f}/100*

_O bot está monitorando a posição._
        """
        
        return self.enviar_mensagem(mensagem)
    
    def notificar_posicao_aberta(self, posicao):
        """
        Notifica quando abre uma posição.
        
        Args:
            posicao: dicionário com dados da posição
        """
        tipo = posicao["tipo"]
        preco = posicao["preco_entrada"]
        valor = posicao["valor_investido"]
        stop = posicao["stop_loss"]
        profit = posicao["take_profit"]
        
        emoji = "🟢" if tipo == "COMPRA" else "🔴"
        
        mensagem = f"""
{emoji} *POSIÇÃO ABERTA: {tipo}*

💰 Preço de entrada: *${preco:.2f}*
💵 Valor investido: *${valor:.2f}*

🛑 Stop Loss: *${stop:.2f}*
🎯 Take Profit: *${profit:.2f}*

_Bot monitorando automaticamente._
        """
        
        return self.enviar_mensagem(mensagem)
    
    def notificar_posicao_fechada(self, operacao):
        """
        Notifica quando fecha uma posição.
        
        Args:
            operacao: dicionário com dados da operação
        """
        lucro = operacao["lucro_prejuizo"]
        variacao = operacao["variacao_percentual"]
        motivo = operacao["motivo_fechamento"]
        preco_entrada = operacao["preco_entrada"]
        preco_saida = operacao["preco_saida"]
        
        emoji = "🟢" if lucro > 0 else "🔴"
        
        if motivo == "STOP_LOSS":
            motivo_texto = "🛑 Stop Loss atingido"
        elif motivo == "TAKE_PROFIT":
            motivo_texto = "🎯 Take Profit atingido"
        else:
            motivo_texto = motivo
        
        mensagem = f"""
{emoji} *POSIÇÃO FECHADA*

{motivo_texto}

📥 Entrada: *${preco_entrada:.2f}*
📤 Saída: *${preco_saida:.2f}*
📊 Variação: *{variacao:+.2f}%*
💰 Resultado: *${lucro:+.2f}*
        """
        
        return self.enviar_mensagem(mensagem)
    
    def notificar_erro(self, erro):
        """
        Notifica quando ocorre um erro grave.
        
        Args:
            erro: descrição do erro
        """
        mensagem = f"""
⚠️ *ERRO NO BOT*

❌ {erro}

_O bot pode precisar de atenção._
        """
        
        return self.enviar_mensagem(mensagem)
    
    def notificar_resumo_diario(self, stats):
        """
        Envia resumo do dia.
        
        Args:
            stats: dicionário com estatísticas
        """
        mensagem = f"""
📋 *RESUMO DIÁRIO*

💼 Operações: {stats.get('total_operacoes', 0)}
✅ Acertos: {stats.get('acertos', 0)}
❌ Erros: {stats.get('erros', 0)}
💰 Lucro do dia: *{stats.get('lucro', 0):+.2f}*
📊 Taxa de acerto: *{stats.get('taxa_acerto', 0):.1f}%*
💵 Capital atual: *${stats.get('capital', 0):.2f}*
        """
        
        return self.enviar_mensagem(mensagem)

    def ler_atualizacoes(self, offset=None):
        """Lê mensagens novas que chegaram no bot"""
        url = f"{self.url_base}/getUpdates"
        params = {"timeout": 5}
        if offset:
            params["offset"] = offset
        try:
            resposta = requests.get(url, params=params, timeout=15)
            dados = resposta.json()
            if dados.get("ok"):
                return dados.get("result", [])
            return []
        except Exception as e:
            print(f"   ⚠️ Erro ao ler mensagens: {e}")
            return []