"""Regression of confirmed-buy persistence in Main, fully offline.

Extracts only the relevant Python functions/class methods via AST. Does NOT
import the trading bot, load .env, create CCXT clients or call OKX.
Run: python3 -m unittest discover -s tests -p 'test_confirmed_buy_persistence.py' -v
"""
import ast
import copy
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock


SOURCE = Path(__file__).resolve().parents[1] / "trader_testnet.py"


def _isolated_trader():
    source = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [
        copy.deepcopy(node)
        for node in source.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"_norm_symbol", "_safe_float"}
    ]
    original_class = next(
        node for node in source.body
        if isinstance(node, ast.ClassDef) and node.name == "TraderTestnet"
    )
    isolated_class = copy.deepcopy(original_class)
    isolated_class.body = [
        node for node in isolated_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name in {"tem_posicao", "em_cooldown", "abrir_compra"}
    ]
    tree = ast.fix_missing_locations(
        ast.Module(body=[*functions, isolated_class], type_ignores=[])
    )
    env = {
        "datetime": datetime,
        "time": time,
        "_STOP_LOSS_PCT": -0.02,
        "_TAKE_PROFIT_PCT": 0.03,
        "comprar_mercado": Mock(),
        "obter_preco": Mock(return_value=10.0),
        "salvar_posicao": Mock(),
        "log_info": Mock(),
        "log_erro": Mock(),
        "log_operacao": Mock(),
    }
    exec(compile(tree, str(SOURCE), "exec"), env)
    trader = env["TraderTestnet"].__new__(env["TraderTestnet"])
    trader.client = Mock()
    trader.symbol_padrao = "BTC-USDT"
    trader.valor_operacao = 100.0
    trader._cooldowns = {}
    trader.posicoes = {}
    return trader, env


class ConfirmedBuyPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.trader, self.env = _isolated_trader()

    def _confirmed(self, cost=100.0):
        return {
            "id": "synthetic-order-123",
            "status": "closed",
            "filled": 2.0,
            "cost": cost,
        }

    def test_confirmed_order_registers_position_once(self):
        self.env["comprar_mercado"].return_value = self._confirmed()
        position = self.trader.abrir_compra("BTC-USDT")
        self.assertIsNotNone(position)
        self.assertEqual(position["quantidade"], 2.0)
        self.assertEqual(position["valor_investido"], 100.0)
        self.assertEqual(position["preco_entrada"], 50.0)
        self.assertEqual(position["stop_loss"], 49.0)
        self.assertEqual(position["take_profit"], 51.5)
        self.assertEqual(self.trader.posicoes["BTC-USDT"], position)
        self.env["salvar_posicao"].assert_called_once_with(position)
        self.env["comprar_mercado"].assert_called_once_with(
            self.trader.client, "BTC-USDT", 100.0
        )
        self.trader.client.fetch_order.assert_not_called()

    def test_no_duplicate_when_position_already_open(self):
        self.env["comprar_mercado"].return_value = self._confirmed()
        self.assertIsNotNone(self.trader.abrir_compra("BTC-USDT"))
        self.assertIsNone(self.trader.abrir_compra("BTC-USDT"))
        self.env["comprar_mercado"].assert_called_once()

    def test_rejects_unconfirmed_order(self):
        for bad in [
            None,
            {"status": "closed", "filled": 2.0, "cost": 100.0},
            {"id": "x", "status": "open", "filled": 2.0, "cost": 100.0},
            {"id": "x", "status": "closed", "filled": 0, "cost": 0},
        ]:
            with self.subTest(bad=bad):
                trader, env = _isolated_trader()
                env["comprar_mercado"].return_value = bad
                self.assertIsNone(trader.abrir_compra("BTC-USDT"))
                self.assertEqual(trader.posicoes, {})
                env["salvar_posicao"].assert_not_called()

    def test_no_rebuy_during_cooldown(self):
        self.trader._cooldowns["BTC-USDT"] = time.time() + 30
        self.assertIsNone(self.trader.abrir_compra("BTC-USDT"))
        self.env["comprar_mercado"].assert_not_called()

    def test_cost_fallback_uses_reference_price(self):
        self.env["comprar_mercado"].return_value = self._confirmed(cost=0)
        position = self.trader.abrir_compra("BTC-USDT")
        self.assertEqual(position["valor_investido"], 20.0)
        self.assertEqual(position["preco_entrada"], 10.0)

    def test_cost_and_reference_missing_does_not_persist(self):
        self.env["comprar_mercado"].return_value = self._confirmed(cost=0)
        self.env["obter_preco"].return_value = 0
        self.assertIsNone(self.trader.abrir_compra("BTC-USDT"))
        self.assertEqual(self.trader.posicoes, {})
        self.env["salvar_posicao"].assert_not_called()


if __name__ == "__main__":
    unittest.main()
