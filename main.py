#from crypto.crypto_data import Crypto
from crypto.binance_data import BinanceFiltered

bin = BinanceFiltered()
print(bin.get_all_crypto_balances())
#print(Crypto.get_all_crypto_tokens())
