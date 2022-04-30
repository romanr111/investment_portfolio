from src.crypto.crypto_data import CryptoMarketValue
from src.cash_fixed_income.cash_assets_data import Cash


if __name__ == "__main__":

    c = Cash()
    
    print(c.get_all_fixed_income())
    print('\n')
    print(c.get_all_p2p_income())
    print('\n')
    print(CryptoMarketValue.get_all_free_cash_in_stablecoins())
    print('\n')
    print(CryptoMarketValue.get_crypto_market_value())
    print('\n')
    print(CryptoMarketValue.get_crypto_total_market_value())
    print('\n')
    print(CryptoMarketValue.get_mining_value())