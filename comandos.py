# comandos.py
# Escuta comandos do Telegram em segundo plano

import threading
import time


class ListenerComandos:
    """
    Fica ouvindo o Telegram numa thread separada.
    
    🔒 Segurança: SÓ aceita mensagens do SEU chat.
    (imagina alguém de fora mandando /parar no seu bot!)
    """
    
    def __init__(self, notificador, ao_receber):
        self.notificador = notificador
        self.ao_receber = ao_receber
        self.chat_permitido = str(notificador.chat_id)
        self.rodando = True
        self.offset = None
        self._descartar_antigas()
    
    def _descartar_antigas(self):
        """Ignora mensagens enviadas enquanto o bot estava desligado"""
        atualizacoes = self.notificador.ler_atualizacoes()
        if atualizacoes:
            self.offset = atualizacoes[-1]["update_id"] + 1
    
    def iniciar(self):
        """Inicia a escuta em segundo plano"""
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()
        print("📡 Escuta de comandos ativada (Telegram)")
    
    def parar(self):
        self.rodando = False
    
    def _loop(self):
        while self.rodando:
            atualizacoes = self.notificador.ler_atualizacoes(self.offset)
            
            for atual in atualizacoes:
                self.offset = atual["update_id"] + 1
                
                mensagem = atual.get("message", {})
                texto = mensagem.get("text", "")
                chat = str(mensagem.get("chat", {}).get("id", ""))
                
                # 🔒 Só aceita mensagens do dono
                if chat != self.chat_permitido:
                    continue
                
                if texto:
                    self.ao_receber(texto)
            
            time.sleep(3)  # verifica a cada 3 segundos