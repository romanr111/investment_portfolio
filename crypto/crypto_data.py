from .binance_data import BinanceFiltered
from .crypto_landing.coinloan import CoinLoan
from .crypto_landing.youholder import YouHodler


class Crypto:
    ''' Grouping and represantation of crypto related data should be performed here.
    '''
    TREZOR_BTC = 0.01
    TREZOR_ETH = 0.2
    EOS_WALLET = 90
    NEO_WALLET = 5
    SIA_COIN = 4343

    crypto_quantity = {
        'BTC': None,
        'ETH': None,
        'ADA': None,
        'EOS': 90,
        'NEO': 7.85,
        'SC': SIA_COIN
    }

    binance = BinanceFiltered()

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

        sum_of_all_principal = 0
        sum_of_all_interest = 0

        for values in crypto_fixed_income.values():
            principal, interest = values
            sum_of_all_principal += principal
            sum_of_all_interest += principal * interest
        
        avarage_interest_rate = round(sum_of_all_interest / sum_of_all_principal, 3)
        crypto_fixed_income['TotalInterestEarningCrypto'] = (sum_of_all_principal, avarage_interest_rate)

        return crypto_fixed_income

    @classmethod
    def get_all_crypto(cls):
        ''' 
         Returns: 
            Dict: Maps crypto names with their quantity.
        '''
        binance_crypto = cls.binance.get_all_crypto_balances()

        for crypto in binance_crypto.items():
            print(crypto)



        
