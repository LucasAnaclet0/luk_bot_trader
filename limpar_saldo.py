# limpar_saldo.py
from trading import criar_cliente, obter_saldo, vender_mercado

client = criar_cliente()
if not client:
    exit()

qtd = obter_saldo(client, "BTC")
print(f"🪙 BTC na carteira: {qtd:.6f}")

if qtd > 0:
    resposta = input("Vender todo esse BTC agora? (s/n): ")
    if resposta.lower() == 's':
        vender_mercado(client, "BTCUSDT", qtd)
        print("✅ Carteira limpa!")
else:
    print("✅ Nada pra limpar.")