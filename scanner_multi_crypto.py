"""
Scanner Multi-Crypto Profissional v6 (Adaptado para OKX)
- Formato LISTA primeiro (evita KeyError e spam de log)
- Cooldown automático para HTTP 429 do CoinGecko
- Watchlist dinâmica integrada ao Auto-Discovery
- Rate limiting robusto
"""
import asyncio
import traceback
import time
from typing import Dict, List, Optional, Any, Iterable
from datetime import datetime

from analise import analisar_candles, gerar_sinal_com_indicadores
from indicadores import analisar_indicadores
from logger_bot import log_info, log_erro, log_sinal

import config as _cfg
from config import (
    WATCHLIST, INTERVALO, LIMITE_CANDLES,
    PESO_TECNICO, PESO_VOLUME_LIQUIDEZ, PESO_SENTIMENTO,
    PESO_ONCHAIN_PROXY, PESO_EVENTO_RISCO,
    MIN_VOLUME_USD, MAX_SPREAD_PCT, COINGECKO_CACHE_TTL,
    SCORE_MINIMO_COMPRA, SCORE_MINIMO_VENDA,
    USAR_TESTNET
)


def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return float(default)
        return float(value)
    except Exception:
        return float(default)


SCORE_ALTO_TESTNET = _safe_float(getattr(_cfg, "SCORE_ALTO_TESTNET", 75.0), 75.0)

try:
    import ccxt.async_support as ccxt_async
except ImportError:
    raise ImportError("Instale ccxt: pip install ccxt")

try:
    import aiohttp
except ImportError:
    raise ImportError("Instale aiohttp: pip install aiohttp")


# ==========================================
# CACHE EM MEMÓRIA COM TTL
# ==========================================
class _TTLCache:
    def __init__(self):
        self._store: Dict[str, tuple] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        val, exp = item
        if time.monotonic() < exp:
            return val
        del self._store[key]
        return None

    def set(self, key: str, value: Any, ttl_seconds: int):
        self._store[key] = (value, time.monotonic() + max(0, int(ttl_seconds)))


_cache = _TTLCache()


# ==========================================
# CLIENTE CCXT (ADAPTADO PARA OKX)
# ==========================================
class _CCXTClient:
    VALID_TIMEFRAMES = {
        '1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h',
        '6h', '8h', '12h', '1d', '3d', '1w', '1M'
    }

    def __init__(self):
        exchange_id = "okx"  # <-- MUDANÇA 1: OKX em vez de Binance
        cls = getattr(ccxt_async, exchange_id)
        self.exchange = cls({
            'enableRateLimit': True,
        })
        if USAR_TESTNET:
            self.exchange.set_sandbox_mode(True)  # <-- MUDANÇA 2: Sandbox explícito para OKX
        self._closed = False

    @staticmethod
    def _to_ccxt_symbol(symbol: str) -> str:
        """Normaliza o símbolo para o formato interno do CCXT (BASE/QUOTE)"""
        symbol = str(symbol or "").upper().strip()
        # Se já tiver hífen (formato OKX config), converte para barra
        if symbol.endswith("-USDT"):
            return symbol.replace("-USDT", "/USDT")
        # Se for formato legado sem separador
        if symbol.endswith("USDT"):
            return symbol.replace("USDT", "/USDT")
        return symbol

    async def fetch_ohlcv_ccxt(self, symbol: str) -> List[List]:
        try:
            ccxt_symbol = self._to_ccxt_symbol(symbol)
            timeframe = INTERVALO if INTERVALO in self.VALID_TIMEFRAMES else '1h'
            data = await self.exchange.fetch_ohlcv(
                ccxt_symbol,
                timeframe=timeframe,
                limit=LIMITE_CANDLES
            )
            return data or []
        except Exception as e:
            log_erro(f"[CCXT] OHLCV {symbol}: {type(e).__name__}: {e}")
            return []

    async def fetch_ticker_ccxt(self, symbol: str) -> Optional[Dict]:
        try:
            ccxt_symbol = self._to_ccxt_symbol(symbol)
            t = await self.exchange.fetch_ticker(ccxt_symbol)

            price = _safe_float(t.get('last'), 0.0)
            bid = _safe_float(t.get('bid'), 0.0)
            ask = _safe_float(t.get('ask'), 0.0)
            volume_usd = _safe_float(t.get('quoteVolume'), 0.0)

            spread_pct = 999.0
            if price > 0 and bid > 0 and ask > 0:
                spread_pct = ((ask - bid) / price) * 100

            return {
                "price": price,
                "volume_usd": volume_usd,
                "spread_pct": spread_pct,
                "bid": bid,
                "ask": ask
            }
        except Exception as e:
            log_erro(f"[CCXT] Ticker {symbol}: {type(e).__name__}: {e}")
            return None

    async def close(self):
        if not self._closed:
            await self.exchange.close()
            self._closed = True


# ==========================================
# CLIENTE COINGECKO COM COOLDOWN
# ==========================================
class _CoinGeckoClient:
    BASE_URL = "https://api.coingecko.com/api/v3"
    MIN_INTERVAL = 4.0          
    COOLDOWN_429_SECONDS = 180  

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_call = 0.0
        self._lock: Optional[asyncio.Lock] = None
        self._cooldown_until = 0.0

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _rate_limit(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            if elapsed < self.MIN_INTERVAL:
                await asyncio.sleep(self.MIN_INTERVAL - elapsed)
            self._last_call = time.monotonic()

    async def get_fundamental_data(self, coingecko_id: str) -> Optional[Dict]:
        if not coingecko_id:
            return None

        cache_key = f"cg:{coingecko_id}"
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        now = time.monotonic()
        if now < self._cooldown_until:
            restante = int(self._cooldown_until - now)
            log_info(f"[CoinGecko] Cooldown ativo por mais {restante}s. Pulando {coingecko_id}.")
            return None

        await self._ensure_session()
        await self._rate_limit()

        url = f"{self.BASE_URL}/coins/{coingecko_id}"
        params = {
            "localization": "false", "tickers": "false",
            "community_data": "true", "developer_data": "true"
        }

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.get(url, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    normalized = {
                        "market_cap_rank": data.get("market_cap_rank", 9999),
                        "community_score": data.get("community_score", 0),
                        "developer_score": data.get("developer_score", 0),
                        "sentiment_up_pct": data.get("sentiment_votes_up_percentage", 50),
                        "coingecko_score": data.get("coingecko_score", 0),
                    }
                    _cache.set(cache_key, normalized, COINGECKO_CACHE_TTL)
                    return normalized

                if resp.status in (429, 418):
                    self._cooldown_until = time.monotonic() + self.COOLDOWN_429_SECONDS
                    log_erro(f"[CoinGecko] HTTP {resp.status} para {coingecko_id}. Cooldown por {self.COOLDOWN_429_SECONDS}s.")
                    return None

                log_erro(f"[CoinGecko] HTTP {resp.status} para {coingecko_id}")
                return None
        except Exception as e:
            log_erro(f"[CoinGecko] Erro {coingecko_id}: {type(e).__name__}: {e}")
            return None

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ==========================================
# NORMALIZADOR DE RAZÕES
# ==========================================
def _normalizar_razoes(razoes_raw: Any) -> List[str]:
    if razoes_raw is None: return []
    if isinstance(razoes_raw, str): return [razoes_raw] if razoes_raw.strip() else []
    if isinstance(razoes_raw, (int, float)): return [str(razoes_raw)]
    if isinstance(razoes_raw, list):
        resultado = []
        for item in razoes_raw:
            if isinstance(item, list): resultado.extend([str(x) for x in item])
            elif item is not None: resultado.append(str(item))
        return resultado
    return [str(razoes_raw)]


# ==========================================
# MOTOR DE SCORE UNIFICADO
# ==========================================
def _calcular_score_unificado(score_tecnico: float, razoes_tecnicas: Any, fundamental: Optional[Dict], ticker: Optional[Dict]) -> Dict:
    scores_parciais = {}
    razoes = _normalizar_razoes(razoes_tecnicas)

    scores_parciais["tecnico"] = score_tecnico * PESO_TECNICO

    vol_score = 0.0
    if ticker:
        if ticker["volume_usd"] >= MIN_VOLUME_USD:
            vol_score += 50
            razoes.append(f"Vol ${ticker['volume_usd']/1e6:.1f}M OK")
        else:
            razoes.append(f"Vol baixo (${ticker['volume_usd']/1e6:.1f}M)")
        if ticker["spread_pct"] <= MAX_SPREAD_PCT:
            vol_score += 50
            razoes.append(f"Spread {ticker['spread_pct']:.3f}% OK")
        else:
            razoes.append(f"Spread alto ({ticker['spread_pct']:.3f}%)")
    else:
        razoes.append("Sem dados de ticker")
    scores_parciais["volume_liq"] = vol_score * PESO_VOLUME_LIQUIDEZ

    sent_score = 0.0
    if fundamental:
        rank = fundamental["market_cap_rank"]
        if rank <= 20: sent_score += 30; razoes.append(f"Top {rank} market cap")
        elif rank <= 100: sent_score += 15
        
        sentiment = fundamental["sentiment_up_pct"]
        if sentiment >= 65: sent_score += 35; razoes.append(f"Sentimento {sentiment:.0f}% positivo")
        elif sentiment >= 45: sent_score += 15
        
        dev = fundamental["developer_score"]
        if dev >= 60: sent_score += 20; razoes.append("Dev activity alta")
        elif dev >= 30: sent_score += 10
        
        comm = fundamental["community_score"]
        if comm >= 50: sent_score += 15; razoes.append("Comunidade engajada")
    else:
        razoes.append("Sem dados CoinGecko")
    scores_parciais["sentimento"] = sent_score * PESO_SENTIMENTO

    onchain_score = 0.0
    if fundamental:
        rank = fundamental["market_cap_rank"]
        onchain_score = max(0, 100 - (rank / 2))
    scores_parciais["onchain"] = onchain_score * PESO_ONCHAIN_PROXY

    scores_parciais["evento"] = 50.0 * PESO_EVENTO_RISCO

    score_final = max(0.0, min(100.0, sum(scores_parciais.values())))

    return {
        "score_final": round(score_final, 1),
        "breakdown": {k: round(v, 1) for k, v in scores_parciais.items()},
        "razoes": razoes
    }


# ==========================================
# CONVERSORES DE CANDLE
# ==========================================
def _converter_ohlcv_para_lista(ohlcv_raw: List[List]) -> List[List]:
    candles = []
    for c in ohlcv_raw:
        if not c or len(c) < 6: continue
        try:
            candles.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])])
        except Exception:
            continue
    return candles

def _converter_lista_para_dict(candles_lista: List[List]) -> List[Dict]:
    return [{"timestamp": int(c[0]), "time": int(c[0]), "open": float(c[1]), "high": float(c[2]), "low": float(c[3]), "close": float(c[4]), "volume": float(c[5])} for c in candles_lista]


# ==========================================
# SCANNER PRINCIPAL
# ==========================================
class MultiCryptoScanner:
    def __init__(self):
        self.ccxt = _CCXTClient()
        self.cg = _CoinGeckoClient()

        symbols = getattr(WATCHLIST, "symbols", ()) or ()
        if not symbols:
            symbols = (getattr(_cfg, "SIMBOLO", "BTC-USDT"),)

        self._symbols = tuple(str(s).strip().upper().replace("/", "") for s in symbols if s)

        self._coingecko_ids = dict(getattr(WATCHLIST, "coingecko_ids", {}) or {})
        # MUDANÇA 3: Defaults com hífen (OKX) e fallback sem hífen (legado)
        self._coingecko_ids.setdefault("BTC-USDT", "bitcoin")
        self._coingecko_ids.setdefault("ETH-USDT", "ethereum")
        self._coingecko_ids.setdefault("BTCUSDT", "bitcoin")
        self._coingecko_ids.setdefault("ETHUSDT", "ethereum")

    def atualizar_watchlist(self, symbols: Iterable[str], coingecko_ids: Optional[Dict[str, str]] = None):
        nova_lista = []
        for s in (symbols or []):
            su = str(s).strip().upper().replace("/", "")
            if su and su not in nova_lista:
                nova_lista.append(su)

        if not nova_lista:
            log_erro("[Scanner] Watchlist vazia recebida. Mantendo atual.")
            return

        self._symbols = tuple(nova_lista)

        if coingecko_ids is not None:
            mapa_atualizado = dict(self._coingecko_ids)
            mapa_atualizado.update(coingecko_ids)
            self._coingecko_ids = mapa_atualizado

        self._coingecko_ids.setdefault("BTC-USDT", "bitcoin")
        self._coingecko_ids.setdefault("ETH-USDT", "ethereum")

        log_info(f"[Scanner] Watchlist aplicada: {len(self._symbols)} criptos | {', '.join(self._symbols)}")

    def _obter_coingecko_id(self, symbol: str) -> Optional[str]:
        sym = str(symbol or "").upper()
        cg_id = self._coingecko_ids.get(sym)
        if cg_id: return cg_id
        if sym in ("BTCUSDT", "BTC-USDT"): return "bitcoin"
        if sym in ("ETHUSDT", "ETH-USDT"): return "ethereum"
        return None

    async def avaliar_simbolo(self, symbol: str) -> Optional[Dict]:
        try:
            ohlcv_raw = await self.ccxt.fetch_ohlcv_ccxt(symbol)
            candles_lista = _converter_ohlcv_para_lista(ohlcv_raw)

            if len(candles_lista) < 20:
                log_erro(f"[{symbol}] Candles insuficientes ({len(candles_lista)})")
                return None

            candles_dict = _converter_lista_para_dict(candles_lista)
            resultado_candles, indicadores, formato_usado = None, None, None

            try:
                resultado_candles = analisar_candles(candles_lista)
                if resultado_candles:
                    indicadores = analisar_indicadores(candles_lista)
                    if indicadores: formato_usado = "lista"
            except Exception as e:
                log_info(f"[{symbol}] Formato lista falhou: {type(e).__name__}: {e}")

            if not resultado_candles or not indicadores:
                try:
                    resultado_candles = analisar_candles(candles_dict)
                    if resultado_candles:
                        indicadores = analisar_indicadores(candles_dict)
                        if indicadores:
                            formato_usado = "dict"
                except Exception as e:
                    log_erro(f"[{symbol}] Ambos formatos falharam: {e}")
                    return None

            if not resultado_candles or not indicadores:
                return None

            dados_para_sinal = candles_lista if formato_usado == "lista" else candles_dict

            try:
                sinal_original, score_original, explicacao = gerar_sinal_com_indicadores(resultado_candles, indicadores, dados_para_sinal)
            except Exception as e:
                log_erro(f"[{symbol}] gerar_sinal_com_indicadores falhou: {type(e).__name__}: {e}")
                return None

            score_original = _safe_float(score_original, 0.0)
            log_info(f"[{symbol}] Técnica OK: sinal={sinal_original}, score={score_original:.1f}, formato={formato_usado}")

            cg_id = self._obter_coingecko_id(symbol)
            fundamental = None
            if cg_id:
                fundamental = await self.cg.get_fundamental_data(cg_id)
                if fundamental: log_info(f"[{symbol}] CoinGecko OK: rank={fundamental['market_cap_rank']}")
                else: log_info(f"[{symbol}] CoinGecko sem dados/cooldown")
            else:
                log_info(f"[{symbol}] Sem CoinGecko ID mapeado")

            ticker = await self.ccxt.fetch_ticker_ccxt(symbol)
            if not ticker or ticker.get("price", 0) <= 0:
                log_erro(f"[{symbol}] Ticker inválido ou preço zero")
                return None

            score_result = _calcular_score_unificado(score_tecnico=score_original, razoes_tecnicas=explicacao, fundamental=fundamental, ticker=ticker)
            score_final = score_result["score_final"]

            if score_final >= SCORE_ALTO_TESTNET and sinal_original != "VENDA": acao = "COMPRA"
            elif sinal_original == "COMPRA" and score_final >= SCORE_MINIMO_COMPRA: acao = "COMPRA"
            elif sinal_original == "VENDA" and score_final >= SCORE_MINIMO_VENDA: acao = "VENDA"
            else: acao = "AGUARDAR"

            log_info(f"[{symbol}] Decisão: {acao} | Score={score_final:.1f}% | Sinal={sinal_original}")

            return {
                "symbol": symbol, "sinal_original": sinal_original, "score_original": round(score_original, 1),
                "score_unificado": score_final, "acao": acao, "preco": ticker["price"],
                "volume_usd": ticker["volume_usd"], "spread_pct": ticker["spread_pct"],
                "breakdown": score_result["breakdown"], "razoes": score_result["razoes"],
                "timestamp": datetime.utcnow().isoformat()
            }
        except Exception as e:
            log_erro(f"[{symbol}] Exceção na avaliação: {type(e).__name__}: {e}")
            return None

    async def scan_completo(self) -> List[Dict]:
        if not self._symbols:
            fallback = getattr(_cfg, "SIMBOLO", "BTC-USDT")
            self._symbols = (str(fallback).strip().upper().replace("/", ""),)

        log_info(f"🔍 Scan iniciado: {len(self._symbols)} criptos | {datetime.now().strftime('%H:%M:%S')}")
        tasks = [self.avaliar_simbolo(sym) for sym in self._symbols]
        resultados = await asyncio.gather(*tasks, return_exceptions=True)

        validos, erros = [], 0
        for i, r in enumerate(resultados):
            if isinstance(r, dict): validos.append(r)
            else:
                erros += 1
                symbol_erro = self._symbols[i] if i < len(self._symbols) else "?"
                log_erro(f"[{symbol_erro}] Exceção: {type(r).__name__}: {r}")

        validos.sort(key=lambda x: x["score_unificado"], reverse=True)
        log_info(f"✅ Scan concluído: {len(validos)} OK, {erros} falhas")
        return validos

    async def fechar(self):
        try: await self.ccxt.close()
        except Exception as e: log_erro(f"Erro ao fechar CCXT: {e}")
        try: await self.cg.close()
        except Exception as e: log_erro(f"Erro ao fechar CoinGecko: {e}")