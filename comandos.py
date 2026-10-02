# comandos.py
# Escuta comandos do Telegram em segundo plano
# ATUALIZADO: Persistência de offset + descarte robusto de mensagens antigas

import json
import os
import threading
import time

from logger_bot import log_info, log_erro


OFFSET_FILE = "telegram_offset.json"


class ListenerComandos:
    """
    Fica ouvindo o Telegram numa thread separada.

    🔒 Segurança: SÓ aceita mensagens do SEU chat.
    💾 Persistência: Salva offset em disco para não repetir mensagens após restart.
    """

    def __init__(self, notificador, ao_receber):
        self.notificador = notificador
        self.ao_receber = ao_receber
        self.chat_permitido = str(notificador.chat_id)
        self.rodando = True
        self.offset = self._carregar_offset()
        self._descartar_antigas()

    # ==========================================
    # PERSISTÊNCIA DE OFFSET
    # ==========================================

    def _carregar_offset(self):
        """Carrega o último offset salvo em disco."""
        try:
            if os.path.exists(OFFSET_FILE):
                with open(OFFSET_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    offset = data.get("offset")
                    if offset is not None:
                        log_info(f"📡 Offset restaurado do arquivo: {offset}")
                        return int(offset)
        except Exception as e:
            log_erro(f"Falha ao carregar offset: {e}")
        return None

    def _salvar_offset(self):
        """Salva o offset atual em disco."""
        if self.offset is None:
            return
        try:
            with open(OFFSET_FILE, "w", encoding="utf-8") as f:
                json.dump({"offset": self.offset}, f)
        except Exception as e:
            log_erro(f"Falha ao salvar offset: {e}")

    # ==========================================
    # DESCARTE DE MENSAGENS ANTIGAS
    # ==========================================

    def _descartar_antigas(self):
        """
        Ignora mensagens enviadas enquanto o bot estava desligado.
        Se já tem offset salvo, usa ele. Senão, pega o update_id mais recente.
        """
        if self.offset is not None:
            # Já tem offset salvo → valida se ainda é válido
            log_info(f"📡 Usando offset salvo: {self.offset}")
            return

        # Sem offset salvo → descarta todas as mensagens pendentes
        try:
            atualizacoes = self.notificador.ler_atualizacoes()
            if atualizacoes:
                self.offset = max(u["update_id"] for u in atualizacoes) + 1
                self._salvar_offset()
                log_info(
                    f"📡 Descartadas {len(atualizacoes)} mensagem(ns) antiga(s). "
                    f"Novo offset: {self.offset}"
                )
            else:
                log_info("📡 Nenhuma mensagem pendente. Offset será definido na primeira mensagem.")
        except Exception as e:
            log_erro(f"Erro ao descartar mensagens antigas: {e}")

    # ==========================================
    # LOOP PRINCIPAL
    # ==========================================

    def iniciar(self):
        """Inicia a escuta em segundo plano."""
        thread = threading.Thread(target=self._loop, daemon=True)
        thread.start()
        print("📡 Escuta de comandos ativada (Telegram)")

    def parar(self):
        """Para a escuta."""
        self.rodando = False
        self._salvar_offset()
        log_info("📡 Escuta de comandos parada. Offset salvo.")

    def _loop(self):
        while self.rodando:
            try:
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

                # Salva offset periodicamente (a cada batch de updates)
                if atualizacoes:
                    self._salvar_offset()

            except Exception as e:
                log_erro(f"Erro no loop de comandos: {type(e).__name__}: {e}")

            time.sleep(3)  # verifica a cada 3 segundos