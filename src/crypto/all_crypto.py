import src.helpers as helpers
from src.cash_fixed_income import fixed_income
from .binance_data import BinanceFiltered
from .crypto_landing.coinloan import CoinLoan
from .crypto_landing.youholder import YouHodler
from src.cash_fixed_income.fixed_income import FixedIncomeAsset
from support_data.endpoints import COINMARKETCAP_API, COINMARKETCAP_HEADERS


class Crypto:
    ''' Grouping and of crypto related data is performed here.
    '''
    # TREZOR + Other Crypto Wallets;
    EXTERNAL_CRYPTO = {
        'BTC': 0.039994,
        'ETH': 0.50884,
        'EOS': 90,
        'NEO': 5,
        'SC': 4343
    }

    binance = BinanceFiltered()
    
    @classmethod
    def get_all_free_cash_in_stablecoins(cls):
        '''
        Returns: 
            int: Sums up all uninvested cash in stablecoins. 
        '''
        return cls.binance.get_spot_account_cash_balance()

    @classmethod
    def get_all_crypto_fixed_income(cls):
        ''' Gathers information about interest earning crypto assets across all platforms. \ 
            Calculates their summ and avarage interest rate. 

        Returns: 
            Dict: Maps asset names with tupples of principal and interest. 
        '''
        crypto_fixed_income = {
            'YouHodler': YouHodler.BALANCE,
            'Binance': cls.binance.get_all_principal_plus_avg_interest_rate(),
            'CoinLoan': CoinLoan.BALANCE,
        }
        asset = FixedIncomeAsset()
        crypto_fixed_income = asset.calc_avg_interest_rate(crypto_fixed_income, 'TotalInterestEarningCrypto')

        return crypto_fixed_income

    @classmethod
    def _get_all_crypto_quantity(cls):
        ''' Sums up Binance crypto and crypto from other wallets that are without API support

         Returns: 
            defaultdict: Maps crypto names with their total quantity.
        '''
        crypto = cls.binance.get_all_crypto_balances()

        for token, amount in cls.EXTERNAL_CRYPTO.items():
            crypto[token] += amount
        
        for token, amount in crypto.items():
            crypto[token] = round(amount, 3)
        
        return crypto


class CryptoMarketValue(Crypto):
    ''' Representation of crypto market value is performed here.
    '''
    symbols = '?symbol=BTC,ETH,ADA,BNB,EOS,NEO,LUNA,MATIC,NEAR,FTM,OMG,SC'
    coinmarketcap_crypto_info = helpers.perform_request(COINMARKETCAP_API, symbols, COINMARKETCAP_HEADERS)

    @classmethod
    def get_crypto_market_value(cls):
        ''' Calculates market value for each crypto available in portfolio.

         Returns: 
            dict: Maps crypto names with their market value.
        '''
        crypto_quantity = cls._get_all_crypto_quantity()
        crypto_market_value = {}
        crypto_value = {}

        for crypto in crypto_quantity.keys():
            crypto_market_value.update({ crypto: cls.coinmarketcap_crypto_info['data'][crypto]['quote']['USD']})

        for crypto, price, quantity in zip(list(crypto_market_value.keys()), list(crypto_market_value.values()), list(crypto_quantity.values())): 
            value = round(quantity * price['price'])
            crypto_value[crypto] = value

        sorted_dict = dict(sorted(crypto_value.items(), key=lambda x:x[1], reverse=True))

        return sorted_dict

    @classmethod
    def get_crypto_total_market_value(cls):
        '''
         Returns: 
            int: Calculates total market value of all crypto available in portfolio.
        '''
        crypto = cls.get_crypto_market_value()
        totalValue = 0

        for crypto in crypto.values():
            totalValue += crypto

        return totalValue

    @classmethod
    def get_mining_value(cls):
        nanopool_balance = 0.03749
        assets_price = 1400
        eth_market_price = cls.coinmarketcap_crypto_info['data']['ETH']['quote']['USD']['price']

        eth_value = round(nanopool_balance * eth_market_price)
        total = eth_value + assets_price
        
        return total
        
