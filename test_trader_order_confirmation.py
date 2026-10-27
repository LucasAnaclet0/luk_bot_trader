"""Regression test for confirmed buy-order persistence in TraderTestnet.

Run with: python3 -m unittest test_trader_order_confirmation -v
"""
import unittest
from unittest.mock import Mock, patch

from trader_testnet import TraderTestnet


class ConfirmedBuyOrderTests(unittest.TestCase):
    def test_does_not_refetch_already_confirmed_order(self):
        trader = TraderTestnet.__new__(TraderTestnet)
        trader.client = Mock()
        trader.symbol_padrao = "BTC-USDT"
        trader.valor_operacao = 100.0
        trader.historico = []
        trader.posicoes = {}
        trader._cooldowns = {}

        confirmed_order = {
            "id": "mock-order-123",
            "status": "closed",
            "filled": 1.0,
            "cost": 100.0,
        }

        with patch("trader_testnet.comprar_mercado", return_value=confirmed_order), \
             patch("trader_testnet.salvar_posicao") as save_position, \
             patch("trader_testnet.log_operacao"):
            result = trader.abrir_compra("BTC-USDT")

        self.assertIsNotNone(result)
        self.assertEqual(result["quantidade"], 1.0)
        self.assertEqual(result["valor_investido"], 100.0)
        save_position.assert_called_once_with(result)
        trader.client.fetch_order.assert_not_called()


if __name__ == "__main__":
    unittest.main()
