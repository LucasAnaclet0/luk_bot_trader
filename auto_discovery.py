"""
Auto-Discovery Seguro de Criptomoedas v4 (Adaptado para OKX)
- Descobre automaticamente as melhores criptos para operar
- Filtra por segurança, liquidez e listagem na exchange
- Remove filtro de liquidity_score da API free
- Retorna watchlist + mapeamento CoinGecko para o scanner
- BTC e ETH sempre mantidos como base segura
- Atualização diária (não a cada ciclo)
- Notifica mudanças via Telegram
"""
import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple
from datetime import datetime
from collections import Counter

try:
    import aiohttp
except ImportError:
    raise ImportError("Instale aiohttp: pip install aiohttp")

try:
    import ccxt.async_support as ccxt_async
except ImportError:
    raise ImportError("Instale ccxt: pip install ccxt")

from logger_bot import log_info, log_erro
from config import USAR_TESTNET


# ==========================================
# CONFIGURAÇÕES DE SEGURANÇA
# ==========================================
class DiscoverySafetyConfig:
    """
    Parâmetros de segurança do auto-discovery.
    """
    # Criptos que SEMPRE estão na watchlist (base segura) - Formato OKX
    ALWAYS_INCLUDE: Tuple[str, ...] = ("BTC-USDT", "ETH-USDT")

    # Filtros mínimos de segurança
    MIN_VOLUME_USD_24H = 1_000_000        # $1M/dia mínimo
    MAX_MARKET_CAP_RANK = 100             # Apenas top 100
    MAX_SPREAD_PCT = 0.5                  
    MAX_WATCHLIST_SIZE = 10               # Máximo de criptos na watchlist
    MIN_WATCHLIST_SIZE = 5                # Mínimo desejado

    # Frequência de atualização
    UPDATE_INTERVAL_SECONDS = 86400       # 24 horas

    # Exige que o símbolo exista na exchange carregada.
    REQUIRE_EXCHANGE_LISTING = True

    # Categorias excluídas
    EXCLUDED_CATEGORIES: Set[str] = {
        "stablecoins", "wrapped-tokens", "bridge-tokens",
        "synthetic-assets", "algorithmic-stablecoins",
    }

    # Tickers comuns de stablecoin / fiat
    STABLECOIN_TICKERS: Set[str] = {
        "USDT", "USDC", "DAI", "TUSD", "BUSD", "FDUSD",
        "USDD", "PYUSD", "GUSD", "FRAX", "LUSD",
        "USDE", "USDS", "USD1", "EURC", "EUR", "GBP", "AUD", "BRL", "TRY", "ARS",
    }

    # Símbolos excluídos explicitamente no formato OKX
    EXCLUDED_SYMBOLS: Set[str] = {
        "OKB-USDT",  # Token da exchange OKX
        "TUSD-USDT", "BUSD-USDT", "DAI-USDT", "USDC-USDT", "FDUSD-USDT",
        "USDD-USDT", "PYUSD-USDT", "GUSD-USDT", "FRAX-USDT", "LUSD-USDT",
        "USDE-USDT", "USDS-USDT", "USD1-USDT", "ZEC-USDT",
        "EUR-USDT", "GBP-USDT", "AUD-USDT", "BRL-USDT",
    }

SAFETY = DiscoverySafetyConfig()


# ==========================================
# MAPEAMENTO COINGECKO → OKX
# ==========================================
CG_TO_OKX: Dict[str, Optional[str]] = {
    "bitcoin": "BTC-USDT",
    "ethereum": "ETH-USDT",
    "tether": None,
    "binancecoin": None, # Removido pois é token da Binance
    "ripple": "XRP-USDT",
    "solana": "SOL-USDT",
    "usd-coin": None,
    "cardano": "ADA-USDT",
    "dogecoin": "DOGE-USDT",
    "tron": "TRX-USDT",
    "chainlink": "LINK-USDT",
    "stellar": "XLM-USDT",
    "hedera-hashgraph": "HBAR-USDT",
    "litecoin": "LTC-USDT",
    "polkadot": "DOT-USDT",
    "bitcoin-cash": "BCH-USDT",
    "uniswap": "UNI-USDT",
    "monero": "XMR-USDT",
    "avalanche-2": "AVAX-USDT",
    "shiba-inu": "SHIB-USDT",
    "the-open-network": "TON-USDT",
    "dai": None,
    "true-usd": None,
    "ethena-usde": None,
    "usds": None,
    "first-digital-usd": None,
    "ondo-finance": "ONDO-USDT",
    "bitget-token": "BGB-USDT",
    "sui": "SUI-USDT",
    "pepe": "PEPE-USDT",
    "aptos": "APT-USDT",
    "near": "NEAR-USDT",
    "render-token": "RENDER-USDT",
    "internet-computer": "ICP-USDT",
    "kaspa": "KAS-USDT",
    "fetch-ai": "FET-USDT",
    "aave": "AAVE-USDT",
    "filecoin": "FIL-USDT",
    "mantle": "MNT-USDT",
    "starknet": "STRK-USDT",
    "polygon-ecosystem-token": "POL-USDT",
    "cronos": "CRO-USDT",
    "algorand": "ALGO-USDT",
    "okb": "OKB-USDT",
    "vechain": "VET-USDT",
    "arbitrum": "ARB-USDT",
    "celestia": "TIA-USDT",
    "bonk": "BONK-USDT",
    "sei-network": "SEI-USDT",
    "maker": "MKR-USDT",
    "jupiter": "JUP-USDT",
    "injective-protocol": "INJ-USDT",
    "bittensor": "TAO-USDT",
    "the-graph": "GRT-USDT",
    "optimism": "OP-USDT",
    "floki": "FLOKI-USDT",
    "theta-token": "THETA-USDT",
    "cosmos": "ATOM-USDT",
    "eos": "EOS-USDT",
    "flow": "FLOW-USDT",
    "the-sandbox": "SAND-USDT",
    "axie-infinity": "AXS-USDT",
    "decentraland": "MANA-USDT",
    "gala": "GALA-USDT",
    "quant-network": "QNT-USDT",
    "apecoin": "APE-USDT",
    "chiliz": "CHZ-USDT",
    "tezos": "XTZ-USDT",
    "thorchain": "RUNE-USDT",
    "helium": "HNT-USDT",
    "iota": "IOTA-USDT",
    "zcash": None,
    "pancakeswap-token": "CAKE-USDT",
    "stacks": "STX-USDT",
    "neo": "NEO-USDT",
    "immutable-x": "IMX-USDT",
    "pax-gold": None,
    "nexo": "NEXO-USDT",
    "ravencoin": "RVN-USDT",
    "decred": "DCR-USDT",
    "curve-dao-token": "CRV-USDT",
    "lido-dao": "LDO-USDT",
    "1inch": "1INCH-USDT",
    "jasmy": "JASMY-USDT",
    "ankr": "ANKR-USDT",
    "mask-network": "MASK-USDT",
    "livepeer": "LPT-USDT",
    "kava": "KAVA-USDT",
    "oasis-network": "ROSE-USDT",
    "woo-network": "WOO-USDT",
    "zilliqa": "ZIL-USDT",
    "enjincoin": "ENJ-USDT",
    "gnosis": "GNO-USDT",
    "iotex": "IOTX-USDT",
    "hyperliquid": "HYPE-USDT",
}


# ==========================================
# CLIENTE COINGECKO PARA DISCOVERY
# ==========================================
class _DiscoveryCoinGeckoClient:
    BASE_URL = "https://api.coingecko.com/api/v3"
    MIN_INTERVAL = 2.0

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._last_call = 0.0
        self._lock: Optional[asyncio.Lock] = None

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def _rate_limit(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            loop = asyncio.get_running_loop()
            now = loop.time()
            elapsed = now - self._last_call
            if elapsed < self.MIN_INTERVAL:
                await asyncio.sleep(self.MIN_INTERVAL - elapsed)
            self._last_call = asyncio.get_running_loop().time()

    async def get_top_coins(self, per_page: int = 100) -> List[Dict[str, Any]]:
        await self._ensure_session()
        await self._rate_limit()
        url = f"{self.BASE_URL}/coins/markets"
        params = {
            "vs_currency": "usd", "order": "market_cap_desc",
            "per_page": per_page, "page": 1, "sparkline": "false",
            "price_change_percentage": "24h",
        }
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with self._session.get(url, params=params, timeout=timeout) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    log_erro(f"[Discovery] CoinGecko HTTP {resp.status}")
                    return []
        except Exception as e:
            log_erro(f"[Discovery] CoinGecko erro: {type(e).__name__}: {e}")
            return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


# ==========================================
# VALIDADOR DE SEGURANÇA
# ==========================================
class _SafetyValidator:
    def __init__(self, exchange_symbols: Set[str]):
        self.exchange_symbols = exchange_symbols or set()

    def _resolver_simbolo(self, coin: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        cg_id = str(coin.get("id", "") or "")
        ticker = str(coin.get("symbol", "") or "").upper()
        name = str(coin.get("name", "") or "").lower()

        if ticker in SAFETY.STABLECOIN_TICKERS:
            return None, f"Stablecoin detectada ({ticker})"

        palavras_suspensas = ("stablecoin", "wrapped", "bridged", "synthetic", "usd", "euro", "pound", "real")
        if any(p in name for p in palavras_suspensas):
            if "bitcoin" not in name and "ethereum" not in name:
                return None, "Nome sugere ativo excluído"

        if cg_id in CG_TO_OKX:
            mapped = CG_TO_OKX[cg_id]
            if mapped is None:
                return None, "Excluída no mapeamento (stablecoin/token)"
            symbol = mapped
        else:
            if not ticker:
                return None, "Sem ticker"
            symbol = f"{ticker}-USDT"

        if symbol in SAFETY.EXCLUDED_SYMBOLS:
            return None, "Símbolo excluído"

        if SAFETY.REQUIRE_EXCHANGE_LISTING and self.exchange_symbols:
            if symbol not in self.exchange_symbols:
                return None, f"Não listado na exchange ({symbol})"

        return symbol, None

    def validate(self, coin: Dict[str, Any]) -> Tuple[bool, str, Optional[str]]:
        symbol, erro = self._resolver_simbolo(coin)
        if erro:
            return False, erro, None
        if not symbol:
            return False, "Sem símbolo resolvido", None

        categories = set(coin.get("categories") or [])
        if categories & SAFETY.EXCLUDED_CATEGORIES:
            return False, "Categoria excluída", None

        rank = coin.get("market_cap_rank") or 9999
        try: rank = int(rank)
        except Exception: rank = 9999
        if rank > SAFETY.MAX_MARKET_CAP_RANK:
            return False, f"Rank {rank}>{SAFETY.MAX_MARKET_CAP_RANK}", None

        volume = coin.get("total_volume", 0) or 0
        try: volume = float(volume)
        except Exception: volume = 0.0
        if volume < SAFETY.MIN_VOLUME_USD_24H:
            return False, f"Vol ${volume/1e6:.1f}M<${SAFETY.MIN_VOLUME_USD_24H/1e6:.0f}M", None

        return True, "OK", symbol


# ==========================================
# RANKING DE POTENCIAL
# ==========================================
def _calcular_potencial(coin: Dict[str, Any]) -> float:
    rank = coin.get("market_cap_rank") or 9999
    try: rank = int(rank)
    except Exception: rank = 9999

    volume = coin.get("total_volume", 0) or 0
    try: volume = float(volume)
    except Exception: volume = 0.0

    change_24h = coin.get("price_change_percentage_24h", 0) or 0
    try: change_24h = float(change_24h)
    except Exception: change_24h = 0.0

    sentiment = coin.get("sentiment_votes_up_percentage", 50) or 50
    try: sentiment = float(sentiment)
    except Exception: sentiment = 50.0

    rank_score = max(0.0, 100.0 - rank)
    vol_score = min(100.0, (volume / 50_000_000.0) * 100.0)

    if 1.0 <= change_24h <= 12.0: momentum_score = 100.0
    elif 0.0 <= change_24h < 1.0: momentum_score = 70.0
    elif 12.0 < change_24h <= 25.0: momentum_score = 55.0
    elif change_24h > 25.0: momentum_score = 25.0
    elif -5.0 <= change_24h < 0.0: momentum_score = 45.0
    else: momentum_score = 15.0

    sentiment_score = max(0.0, min(100.0, sentiment))

    score = (rank_score * 0.35 + vol_score * 0.30 + momentum_score * 0.20 + sentiment_score * 0.15)
    return round(max(0.0, min(100.0, score)), 1)


# ==========================================
# AUTO-DISCOVERY PRINCIPAL
# ==========================================
class AutoDiscovery:
    def __init__(self):
        self.cg = _DiscoveryCoinGeckoClient()
        self._exchange_symbols: Set[str] = set()
        self._last_update = 0.0
        self._current_watchlist: List[str] = list(SAFETY.ALWAYS_INCLUDE)
        self._initialized = False

    async def _carregar_simbolos_exchange(self):
        if self._exchange_symbols:
            return
        try:
            exchange_class = getattr(ccxt_async, "okx")
            exchange = exchange_class({
                "enableRateLimit": True,
            })
            if USAR_TESTNET:
                exchange.set_sandbox_mode(True)
            
            markets = await exchange.load_markets()
            
            # CCXT retorna "BTC/USDT", convertemos para "BTC-USDT"
            self._exchange_symbols = {
                m.replace("/", "-")
                for m in markets.keys()
                if m.endswith("/USDT") and markets[m].get("active")
            }
            await exchange.close()
            log_info(f"[Discovery] {len(self._exchange_symbols)} pares USDT carregados da OKX (referência)")
        except Exception as e:
            log_erro(f"[Discovery] Falha ao carregar símbolos OKX: {e}")
            self._exchange_symbols = set()

    def precisa_atualizar(self) -> bool:
        if not self._initialized:
            return True
        elapsed = time.time() - self._last_update
        return elapsed >= SAFETY.UPDATE_INTERVAL_SECONDS

    async def descobrir_melhores_criptos(self) -> Dict[str, Any]:
        await self._carregar_simbolos_exchange()
        log_info("[Discovery] Buscando top 100 criptos no CoinGecko...")
        coins = await self.cg.get_top_coins(per_page=100)

        if not coins:
            log_erro("[Discovery] Sem dados do CoinGecko. Mantendo watchlist atual.")
            return {"watchlist": self._current_watchlist, "coingecko_map": {}, "changed": False, "reason": "Falha ao buscar dados", "entraram": [], "sairam": [], "total_avaliadas": 0, "seguras": 0, "rejeitadas_count": 0, "candidates": [], "timestamp": datetime.utcnow().isoformat()}

        validator = _SafetyValidator(self._exchange_symbols)
        candidates: List[Dict[str, Any]] = []
        rejeitadas: List[str] = []
        motivos_rejeicao: Counter = Counter()

        for coin in coins:
            é_seguro, motivo, symbol = validator.validate(coin)
            if é_seguro and symbol:
                potencial = _calcular_potencial(coin)
                candidates.append({
                    "symbol": symbol, "cg_id": coin.get("id"), "name": coin.get("name"),
                    "rank": coin.get("market_cap_rank", 9999), "volume_usd": coin.get("total_volume", 0),
                    "change_24h": coin.get("price_change_percentage_24h", 0), "sentiment": coin.get("sentiment_votes_up_percentage", 50),
                    "potencial": potencial, "na_exchange": symbol in self._exchange_symbols if self._exchange_symbols else None,
                })
            else:
                cg_id = coin.get("id", "?")
                rejeitadas.append(f"{cg_id}: {motivo}")
                motivos_rejeicao[motivo] += 1

        log_info("[Discovery] === RELATÓRIO DE REJEIÇÕES ===")
        for motivo, count in motivos_rejeicao.most_common():
            log_info(f"[Discovery]   {motivo}: {count} criptos")
        if rejeitadas:
            log_info(f"[Discovery] Exemplos: {'; '.join(rejeitadas[:8])}")
        log_info("[Discovery] ================================")

        candidates.sort(key=lambda x: x["potencial"], reverse=True)
        selecionados_symbols = [c["symbol"] for c in candidates[:SAFETY.MAX_WATCHLIST_SIZE]]

        for sym in SAFETY.ALWAYS_INCLUDE:
            if sym not in selecionados_symbols:
                selecionados_symbols.insert(0, sym)

        nova_watchlist = selecionados_symbols[:SAFETY.MAX_WATCHLIST_SIZE]
        while len(nova_watchlist) < SAFETY.MIN_WATCHLIST_SIZE and candidates:
            idx = len(nova_watchlist)
            if idx < len(candidates):
                sym = candidates[idx]["symbol"]
                if sym not in nova_watchlist:
                    nova_watchlist.append(sym)
            else:
                break

        coingecko_map: Dict[str, str] = {}
        for c in candidates:
            if c["symbol"] in nova_watchlist and c.get("cg_id"):
                coingecko_map[c["symbol"]] = c["cg_id"]
        coingecko_map.setdefault("BTC-USDT", "bitcoin")
        coingecko_map.setdefault("ETH-USDT", "ethereum")

        antiga = set(self._current_watchlist)
        nova = set(nova_watchlist)
        entraram = nova - antiga
        sairam = antiga - nova
        mudou = bool(entraram or sairam)

        self._current_watchlist = nova_watchlist
        self._last_update = time.time()
        self._initialized = True

        resultado = {
            "watchlist": nova_watchlist, "coingecko_map": coingecko_map, "changed": mudou,
            "entraram": list(entraram), "sairam": list(sairam), "total_avaliadas": len(coins),
            "seguras": len(candidates), "rejeitadas_count": len(rejeitadas),
            "candidates": candidates[:SAFETY.MAX_WATCHLIST_SIZE], "timestamp": datetime.utcnow().isoformat(),
        }

        log_info(f"[Discovery] Avaliadas: {len(coins)} | Seguras: {len(candidates)} | Selecionadas: {len(nova_watchlist)}")
        if mudou:
            if entraram: log_info(f"[Discovery] 🆕 Entraram: {', '.join(entraram)}")
            if sairam: log_info(f"[Discovery] ❌ Saíram: {', '.join(sairam)}")
        else:
            log_info("[Discovery] ✅ Watchlist sem alterações")

        return resultado

    def get_current_watchlist(self) -> List[str]:
        return list(self._current_watchlist)

    def get_current_coingecko_map(self) -> Dict[str, str]:
        mapa: Dict[str, str] = {}
        for sym in self._current_watchlist:
            if sym == "BTC-USDT": mapa[sym] = "bitcoin"
            elif sym == "ETH-USDT": mapa[sym] = "ethereum"
            else:
                for cg_id, okx_symbol in CG_TO_OKX.items():
                    if okx_symbol == sym:
                        mapa[sym] = cg_id
                        break
        return mapa

    async def close(self):
        await self.cg.close()


# ==========================================
# FUNÇÃO DE INTEGRAÇÃO COM MAIN.PY
# ==========================================
async def atualizar_watchlist_se_necessario(discovery: AutoDiscovery, notificador=None) -> Optional[Dict[str, Any]]:
    if not discovery.precisa_atualizar():
        return None
    try:
        resultado = await discovery.descobrir_melhores_criptos()
        if resultado["changed"] and notificador:
            msg = "🔄 *WATCHLIST ATUALIZADA*\n\n"
            if resultado["entraram"]: msg += f"🆕 *Entraram:* {', '.join(resultado['entraram'])}\n"
            if resultado["sairam"]: msg += f"❌ *Saíram:* {', '.join(resultado['sairam'])}\n"
            msg += f"\n📊 *Nova watchlist ({len(resultado['watchlist'])} criptos):*\n"
            for i, sym in enumerate(resultado["watchlist"], 1):
                candidate = next((c for c in resultado["candidates"] if c["symbol"] == sym), None)
                if candidate:
                    exchange_flag = " ✅" if candidate.get("na_exchange") is True else (" ⚠️" if candidate.get("na_exchange") is False else "")
                    msg += f"{i}. `{sym}`{exchange_flag} — Potencial: {candidate['potencial']:.1f}%\n"
                else:
                    msg += f"{i}. `{sym}`\n"
            msg += "\n✅ = Listado na exchange atual | ⚠️ = Fora da exchange atual"
            notificador.enviar_mensagem(msg)
        if resultado["changed"]:
            return {"watchlist": resultado["watchlist"], "coingecko_map": resultado.get("coingecko_map", {})}
        return None
    except Exception as e:
        log_erro(f"[Discovery] Erro na atualização: {type(e).__name__}: {e}")
        return None