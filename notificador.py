# notificador.py
# Sistema de notificações via Telegram - versão profissional
#
# Melhorias:
# - Fallback automático se Markdown quebrar
# - Evita erro por underscores em STOP_LOSS, TAKE_PROFIT, SINAL_VENDA
# - Suporte multi-symbol nas notificações
# - Formatação dinâmica de preço
# - Session HTTP para melhor desempenho
# - Compatível com o main.py atual
import time
import requests
from typing import Any, Dict, Optional


class NotificadorTelegram:
    """
    Envia notificações pro Telegram quando o bot detecta sinais.

    📱 Como funciona:
    - Bot detecta sinal de COMPRA → te avisa no celular
    - Bot detecta sinal de VENDA → te avisa no celular
    - Bot abre/fecha posição → te avisa no celular
    """

    def __init__(
        self,
        token: str,
        chat_id: str,
        default_symbol: str = "BTCUSDT",
        timeout: int = 10,
    ):
        """
        Inicializa o notificador.

        Args:
            token: token do bot (pegou do @BotFather)
            chat_id: seu ID no Telegram (pegou do @userinfobot)
            default_symbol: símbolo padrão usado quando a posição não informar
            timeout: timeout das requisições HTTP
        """
        self.token = token
        self.chat_id = chat_id
        self.url_base = f"https://api.telegram.org/bot{token}"
        self.ativado = True
        self.default_symbol = self._norm_symbol(default_symbol) or "BTCUSDT"
        self.timeout = timeout
        self.session = requests.Session()

    # ==========================================
    # HELPERS INTERNOS
    # ==========================================

    @staticmethod
    def _norm_symbol(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip().upper().replace("/", "")

    def _symbol_from_dict(self, dados: Optional[Dict[str, Any]]) -> str:
        dados = dados or {}
        symbol = (
            dados.get("symbol")
            or dados.get("simbolo")
            or dados.get("par")
            or self.default_symbol
        )
        return self._norm_symbol(symbol) or self.default_symbol

    def _base_from_symbol(self, symbol: Any) -> str:
        symbol = self._norm_symbol(symbol)
        if symbol.endswith("USDT"):
            return symbol[:-4]
        return symbol.replace("USDT", "")

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return float(default)
            return float(value)
        except Exception:
            return float(default)

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return int(default)
            return int(float(value))
        except Exception:
            return int(default)

    def _fmt_price(self, value: Any) -> str:
        v = self._safe_float(value, 0.0)

        if v >= 1000:
            return f"{v:,.2f}"
        if v >= 100:
            return f"{v:.2f}"
        if v >= 1:
            return f"{v:.4f}"
        if v > 0:
            return f"{v:.6f}"

        return "0.00"

    def _fmt_money(self, value: Any) -> str:
        v = self._safe_float(value, 0.0)
        return f"${v:+,.2f}"

    def _sanitize_known_underscores(self, texto: str) -> str:
        """
        Remove underscores problemáticos de termos técnicos.
        Isso evita que o Telegram interprete como itálico Markdown.
        """
        texto = str(texto or "")

        substituicoes = {
            "STOP_LOSS": "STOP LOSS",
            "TAKE_PROFIT": "TAKE PROFIT",
            "SINAL_VENDA": "SINAL VENDA",
            "SINAL_COMPRA": "SINAL COMPRA",
            "STOP_WATCHDOG": "STOP WATCHDOG",
            "ENCERRAMENTO": "ENCERRAMENTO",
            "MOTIVO_DESCONHECIDO": "MOTIVO DESCONHECIDO",
        }

        for antigo, novo in substituicoes.items():
            texto = texto.replace(antigo, novo)

        return texto

    def _prepare_text(self, mensagem: Any) -> Dict[str, str]:
        """
        Prepara duas versões da mensagem:
        - markdown: com underscores escapados
        - plain: texto puro, sem riscos de parse
        """
        texto_base = self._sanitize_known_underscores(str(mensagem or "").strip())

        # Versão Markdown: escapa underscores restantes.
        texto_markdown = texto_base.replace("_", "\\_")

        # Versão texto puro: remove underscores restantes para segurança máxima.
        texto_plain = texto_base.replace("_", " ")

        return {
            "markdown": texto_markdown,
            "plain": texto_plain,
        }

    def _reset_session(self):
        """Fecha e recria a sessão HTTP para limpar conexões quebradas."""
        try:
            self.session.close()
        except Exception:
            pass
        self.session = requests.Session()

    def _post(self, endpoint: str, payload: Dict[str, Any]):
        """
        POST com retry para erros de conexão.
        Ajuda contra ConnectionResetError / timeout / queda momentânea.
        """
        url = f"{self.url_base}/{endpoint}"
        ultima_erro = ""

        for tentativa in range(3):
            try:
                resposta = self.session.post(
                    url,
                    json=payload,
                    timeout=self.timeout
                )

                try:
                    dados = resposta.json()
                except Exception:
                    dados = {}

                return resposta.status_code, dados, resposta.text

            except requests.exceptions.ConnectionError as e:
                ultima_erro = f"ConnectionError: {e}"
                print(f"   ⚠️ Conexão com Telegram caiu. Tentativa {tentativa + 1}/3...")
                self._reset_session()
                time.sleep(1.5 * (tentativa + 1))

            except requests.exceptions.Timeout as e:
                ultima_erro = f"Timeout: {e}"
                print(f"   ⚠️ Timeout ao enviar para Telegram. Tentativa {tentativa + 1}/3...")
                self._reset_session()
                time.sleep(1.5 * (tentativa + 1))

            except Exception as e:
                ultima_erro = f"{type(e).__name__}: {e}"
                print(f"   ⚠️ Erro inesperado ao enviar para Telegram. Tentativa {tentativa + 1}/3...")
                self._reset_session()
                time.sleep(1.5 * (tentativa + 1))

        return 0, {}, ultima_erro
    
    def _is_parse_error(self, status_code: int, dados: Dict[str, Any], raw: str) -> bool:
        if status_code != 400:
            return False

        descricao = str(dados.get("description", "")).lower()
        raw_lower = str(raw).lower()

        sinais = (
            "parse",
            "entity",
            "entities",
            "markdown",
            "format",
            "can't find end",
            "bad request",
        )

        return any(sinal in descricao or sinal in raw_lower for sinal in sinais)

    # ==========================================
    # ENVIO PRINCIPAL
    # ==========================================

    def enviar_mensagem(
        self,
        mensagem: Any,
        parse_mode: str = "Markdown",
        force_plain: bool = False,
    ) -> bool:
        """
        Envia uma mensagem pro Telegram com fallback seguro.

        Args:
            mensagem: texto da mensagem
            parse_mode: modo de formatação. Padrão: Markdown
            force_plain: se True, envia direto como texto puro

        Returns:
            bool: True se enviou, False se deu erro
        """
        if not self.ativado:
            return False

        texto = str(mensagem or "").strip()
        if not texto:
            return False

        preparado = self._prepare_text(texto)

        # 1) Tenta Markdown, a menos que seja forçado texto puro.
        if not force_plain:
            payload_md = {
                "chat_id": self.chat_id,
                "text": preparado["markdown"],
                "parse_mode": parse_mode or "Markdown",
            }

            status, dados, raw = self._post("sendMessage", payload_md)

            if status == 200 and dados.get("ok"):
                print("   📱 Notificação enviada pro Telegram")
                return True

            # Se for erro de formatação, cai para texto puro.
            if self._is_parse_error(status, dados, raw):
                print("   ⚠️ Markdown falhou. Reenviando como texto puro...")
            else:
                print(f"   ⚠️ Erro ao enviar notificação Markdown: {raw}")

        # 2) Fallback: texto puro.
        payload_plain = {
            "chat_id": self.chat_id,
            "text": preparado["plain"],
        }

        status, dados, raw = self._post("sendMessage", payload_plain)

        if status == 200 and dados.get("ok"):
            print("   📱 Notificação enviada pro Telegram (texto puro)")
            return True

        print(f"   ⚠️ Erro final ao enviar notificação: {raw}")
        return False

    # ==========================================
    # NOTIFICAÇÕES ESPECÍFICAS
    # ==========================================

    def notificar_sinal(
        self,
        sinal: str,
        score: Any,
        preco: Any,
        symbol: Optional[str] = None,
    ) -> bool:
        """
        Notifica quando detecta um sinal de compra/venda.

        Args:
            sinal: "COMPRA" ou "VENDA"
            score: score de confiança
            preco: preço atual
            symbol: símbolo, ex.: BTCUSDT, ETHUSDT. Se None, usa default.
        """
        sinal = str(sinal or "").upper()
        symbol = self._norm_symbol(symbol) or self.default_symbol
        score = self._safe_float(score, 0.0)
        preco = self._safe_float(preco, 0.0)

        if sinal == "COMPRA":
            emoji = "🟢"
            texto = "SINAL DE COMPRA DETECTADO"
        elif sinal == "VENDA":
            emoji = "🔴"
            texto = "SINAL DE VENDA DETECTADO"
        else:
            return False

        mensagem = (
            f"{emoji} *{texto}*\n\n"
            f"📦 Par: *{symbol}*\n"
            f"💰 Preço: *${self._fmt_price(preco)}*\n"
            f"🎯 Score: *{score:.1f}/100*\n\n"
            "O bot está monitorando o mercado."
        )

        return self.enviar_mensagem(mensagem)

    def notificar_posicao_aberta(self, posicao: Dict[str, Any]) -> bool:
        """
        Notifica quando abre uma posição.

        Args:
            posicao: dicionário com dados da posição
        """
        posicao = posicao or {}

        symbol = self._symbol_from_dict(posicao)
        base = self._base_from_symbol(symbol)
        tipo = str(posicao.get("tipo", "COMPRA")).upper()

        preco = self._safe_float(posicao.get("preco_entrada"), 0.0)
        valor = self._safe_float(posicao.get("valor_investido"), 0.0)
        stop = self._safe_float(posicao.get("stop_loss"), 0.0)
        profit = self._safe_float(posicao.get("take_profit"), 0.0)
        qtd = self._safe_float(posicao.get("quantidade"), 0.0)

        emoji = "🟢" if tipo == "COMPRA" else "🔴"

        mensagem = (
            f"{emoji} *POSIÇÃO ABERTA: {tipo}*\n\n"
            f"📦 Símbolo: *{symbol}*\n"
            f"🪙 Base: *{base}*\n"
            f"📊 Quantidade: *{qtd:.6f} {base}*\n"
            f"💰 Preço de entrada: *${self._fmt_price(preco)}*\n"
            f"💵 Valor investido: *${valor:.2f}*\n\n"
            f"🛑 Stop Loss: *${self._fmt_price(stop)}*\n"
            f"🎯 Take Profit: *${self._fmt_price(profit)}*\n\n"
            "Bot monitorando automaticamente."
        )

        return self.enviar_mensagem(mensagem)

    def notificar_posicao_fechada(self, operacao: Dict[str, Any]) -> bool:
        """
        Notifica quando fecha uma posição.

        Args:
            operacao: dicionário com dados da operação
        """
        operacao = operacao or {}

        symbol = self._symbol_from_dict(operacao)
        base = self._base_from_symbol(symbol)

        lucro = self._safe_float(operacao.get("lucro_prejuizo"), 0.0)
        variacao = self._safe_float(operacao.get("variacao_percentual"), 0.0)
        preco_entrada = self._safe_float(operacao.get("preco_entrada"), 0.0)
        preco_saida = self._safe_float(operacao.get("preco_saida"), 0.0)
        qtd = self._safe_float(operacao.get("quantidade"), 0.0)
        investido = self._safe_float(operacao.get("valor_investido"), 0.0)

        motivo_raw = str(operacao.get("motivo_fechamento", "FECHAMENTO")).upper()
        parcial = bool(operacao.get("parcial", False))

        motivos_display = {
            "STOP_LOSS": "Stop Loss atingido",
            "TAKE_PROFIT": "Take Profit atingido",
            "SINAL_VENDA": "Sinal de venda detectado",
            "STOP_WATCHDOG": "Stop watchdog ativado",
            "ENCERRAMENTO": "Encerramento manual/sistema",
            "FECHAMENTO": "Fechamento",
        }

        motivo_texto = motivos_display.get(motivo_raw, motivo_raw.replace("_", " "))

        emoji = "🟢" if lucro > 0 else "🔴"
        tipo_fechamento = "PARCIAL" if parcial else "TOTAL"

        mensagem = (
            f"{emoji} *POSIÇÃO FECHADA: {tipo_fechamento}*\n\n"
            f"📦 Símbolo: *{symbol}*\n"
            f"🧾 Motivo: *{motivo_texto}*\n\n"
            f"📥 Entrada: *${self._fmt_price(preco_entrada)}*\n"
            f"📤 Saída: *${self._fmt_price(preco_saida)}*\n"
            f"📊 Quantidade: *{qtd:.6f} {base}*\n"
            f"💵 Investido: *${investido:.2f}*\n"
            f"📈 Variação: *{variacao:+.2f}%*\n"
            f"💰 Resultado: *{self._fmt_money(lucro)}*"
        )

        return self.enviar_mensagem(mensagem)

    def notificar_erro(self, erro: Any) -> bool:
        """
        Notifica quando ocorre um erro grave.

        Args:
            erro: descrição do erro
        """
        mensagem = (
            "⚠️ ERRO NO BOT\n\n"
            f"{erro}\n\n"
            "O bot pode precisar de atenção."
        )

        # Erros podem conter caracteres arbitrários. Melhor enviar como texto puro.
        return self.enviar_mensagem(mensagem, force_plain=True)

    def notificar_resumo_diario(self, stats: Dict[str, Any]) -> bool:
        """
        Envia resumo do dia.

        Args:
            stats: dicionário com estatísticas
        """
        stats = stats or {}

        total_operacoes = self._safe_int(stats.get("total_operacoes"), 0)
        acertos = self._safe_int(stats.get("acertos"), 0)
        erros = self._safe_int(stats.get("erros"), 0)
        lucro = self._safe_float(stats.get("lucro"), 0.0)
        taxa_acerto = self._safe_float(stats.get("taxa_acerto"), 0.0)
        capital = self._safe_float(stats.get("capital"), 0.0)

        mensagem = (
            "📋 *RESUMO DIÁRIO*\n\n"
            f"💼 Operações: *{total_operacoes}*\n"
            f"✅ Acertos: *{acertos}*\n"
            f"❌ Erros: *{erros}*\n"
            f"💰 Lucro do dia: *{self._fmt_money(lucro)}*\n"
            f"📊 Taxa de acerto: *{taxa_acerto:.1f}%*\n"
            f"💵 Capital atual: *${capital:.2f}*"
        )

        return self.enviar_mensagem(mensagem)

    # ==========================================
    # LEITURA DE COMANDOS
    # ==========================================

    def ler_atualizacoes(self, offset: Optional[int] = None):
        """Lê mensagens novas que chegaram no bot."""
        url = f"{self.url_base}/getUpdates"
        params = {"timeout": 5}

        if offset:
            params["offset"] = offset

        try:
            resposta = self.session.get(url, params=params, timeout=15)
            dados = resposta.json()

            if dados.get("ok"):
                return dados.get("result", [])

            return []

        except Exception as e:
            print(f"   ⚠️ Erro ao ler mensagens: {e}")
            return []