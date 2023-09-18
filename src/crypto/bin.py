import math
from collections import defaultdict

from binance.spot import Spot
from data.api_keys import BINANCE_KEY, BINANCE_SECRET

class Binance:
    # Needs to be updated manually every time staking changes;
    LOCKED_STACKING = {
        'BTC': 0.01,
        'ETH': 0.1,
        'NEO': 2.85,
        'ADA': 100,
        'BNB': 0.442,
        'LUNA': 1.32,
        'MATIC': 150
    }

    def __init__(self) -> None:
        #self.__binance_connection = Spot(key=BINANCE_KEY, secret=BINANCE_SECRET)
        self.__binance_connection = Spot(api_key=BINANCE_KEY, api_secret=BINANCE_SECRET)

        if self.__binance_connection:
            print('Binace connection is successful!')
        else:
            raise Exception('Connection to Binance FAILED!')

    def get_total_cash_savings(self):
        '''
        Returns: 
            int: Sum of cash savings in Binance Earn
        '''
        return math.ceil(float(self.__binance_connection.savings_account()['totalAmountInUSDT']))

    def _get_flexible_savings_info(self):
        '''
        Returns: 
            dict: Info about all flexible savings in Binance Earn
        '''
        return self.__binance_connection.savings_flexible_product_position()

    def _get_fixed_savings_info(self):
        '''
        Returns: 
            dict: Info about all fixed savings in Binance Earn
        '''
        return self.__binance_connection.savings_project_position()

    def _get_spot_account_balances(self):
        ''' 
        Returns: 
            dict: Spot account balance without zero values.
        '''
        balances = self.__binance_connection.account()['balances']
        filtered_spot = {}

        for balance in balances:
            if 'LD' in balance['asset']:
                pass
            elif float(balance['free']) > 0.0:
                filtered_spot[balance['asset']] = balance['free']

        return filtered_spot

class BinanceFiltered(Binance):

    def get_spot_account_cash_balance(self):
        ''' Filters out USDT/USDC/BUSD/PAX/DAI from all tokens.

        Returns: 
            int: Total amount of uninvested cash account balance.
        '''
        crypto_cash = 0
        balances = self._get_spot_account_balances()

        for token, balance in balances.items():
            if token in ['USDT','USDC','BUSD', 'PAX', 'DAI']:
                crypto_cash += round(float(balance))

        return crypto_cash

    def get_spot_account_crypto_balances(self):
        ''' Filters out Crypto from Crypto-Dollars in Spot account.

        Returns: 
            defaultdict: Spot crypto balances.
        '''
        crypto = defaultdict(int)
        balances = self._get_spot_account_balances()

        for token, balance in balances.items():
            if token not in ['USDT','USDC','BUSD', 'PAX', 'DAI', 'QISWAP', 'BOBA']:
                if float(balance) > 0.0001:
                    crypto[token] = round(float(balance), 3)

        return crypto

    def get_all_crypto_balances(self):
        ''' Sums up all crypto in different wallets (Spot + Earn).

        Returns: 
            defaultdict: Name + Amount
        '''
        crypto = self.get_spot_account_crypto_balances()

        for token, amount in self.LOCKED_STACKING.items():
            crypto[token] += amount

        return crypto

    def get_all_principal_plus_avg_interest_rate(self):
        '''
        Returns: 
            Tuple: 2 values. The first one is the sum of all interest generating cash \ 
            and the second is the weighted average annual yield.
        '''
        flexible = self._get_flexible_savings_info()
        fixed = self._get_fixed_savings_info()
        sum_of_all_principal = 0
        sum_of_all_interest = 0

        for loan in flexible:
            sum_of_all_principal += int(loan['totalAmount'])
            sum_of_all_interest += int(loan['totalAmount']) * float(loan['annualInterestRate'])
  
        for loan in fixed:
            sum_of_all_principal += int(loan['principal'])
            sum_of_all_interest += int(loan['principal']) * float(loan['interestRate'])

        # Preventive check for function that calculates avarage interest rate.
        total_cash = self.get_total_cash_savings()
        print(f"Total cash DEBUG --> {total_cash}, type {type(total_cash)}")
        if total_cash == 0:
            percentage_diff = 0  # or any other default value
        else:
            percentage_diff = ((sum_of_all_principal - total_cash) / abs(total_cash)) * 100
        assert percentage_diff < 1 and percentage_diff > -1, \
        f'Incorrect principal amount: Actual {sum_of_all_principal}, Expected {total_cash}, Diff: {percentage_diff}%'

        avarage_interest_rate = round(sum_of_all_interest / sum_of_all_principal, 3)

        return (sum_of_all_principal, avarage_interest_rate)
        

if __name__ == "__main__":
    bin = BinanceFiltered()
    x = bin.get_all_principal_plus_avg_interest_rate()
    print(x)
