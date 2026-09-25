# teste_binance.py
from trading import criar_cliente, obter_saldo, obter_preco, comprar_mercado, vender_mercado

print("="*50)
print("🧪 TESTE BINANCE TESTNET")
print("="*50)

# 1. Conecta
client = criar_cliente()
if not client:
    exit()

# 2. Mostra saldos
usdt = obter_saldo(client, "USDT")
btc = obter_saldo(client, "BTC")
print(f"\n💵 Saldo USDT: {usdt:.2f}")
print(f"🪙 Saldo BTC: {btc:.6f}")

# 3. Mostra preço
preco = obter_preco(client, "BTCUSDT")
print(f"📈 Preço BTC: ${preco:.2f}")

# 4. Primeira ordem de teste (só se tiver saldo)
if usdt >= 100:
    print("\n🛒 Executando COMPRA de teste com 100 USDT...")
    ordem = comprar_mercado(client, "BTCUSDT", 100)
    
    if ordem:
        btc_depois = obter_saldo(client, "BTC")
        print(f"🪙 BTC após compra: {btc_depois:.6f}")
        
        # Pergunta se quer vender de volta
        resposta = input("\nQuer vender de volta agora? (s/n): ")
        if resposta.lower() == 's':
            qtd = round(obter_saldo(client, "BTC"), 5)
            if qtd > 0:
                vender_mercado(client, "BTCUSDT", qtd)
                usdt_final = obter_saldo(client, "USDT")
                print(f"💵 USDT final: {usdt_final:.2f}")
else:
    print("\n⚠️ Saldo USDT insuficiente pra testar.")
    print("   Entre no site da testnet e procure o 'Faucet' pra receber moedas de teste.")

print("\n" + "="*50)
print("🎉 TESTE CONCLUÍDO!")
print("="*50)