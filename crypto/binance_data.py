
import math
from collections import defaultdict
from binance.spot import Spot
from .api_keys import BINANCE_KEY, BINANCE_SECRET

class Binance:
    BTC_DEFI_STAKING = 0.01
    ETH_DEFI_STAKING = 0.1

    def __init__(self) -> None:
        self.__binance_connection = Spot(key=BINANCE_KEY, secret=BINANCE_SECRET)

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
            if token not in ['USDT','USDC','BUSD', 'PAX', 'DAI']:
                if float(balance) > 0.0001:
                    crypto[token] = round(float(balance), 3)

        return crypto

    def get_all_crypto_balances(self):
        ''' Sums up all crypto in different wallets (Spot + Earn).

        Returns: 
            dict: Total amount of different crypto tokens.
        '''
        spot_crypto = self.get_spot_account_crypto_balances()
        if spot_crypto.get('BTC') is not None:
            spot_crypto['BTC'] += self.BTC_DEFI_STAKING
        else:
             spot_crypto['BTC'] = self.BTC_DEFI_STAKING

        if spot_crypto.get('ETH') is not None:
            spot_crypto['ETH'] += self.ETH_DEFI_STAKING
        else:
             spot_crypto['ETH'] = self.ETH_DEFI_STAKING

        return spot_crypto

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
        assert total_cash == sum_of_all_principal, f'Incorrect principal amount: Actual {sum_of_all_principal}, Expected {total_cash}'
        avarage_interest_rate = round(sum_of_all_interest / sum_of_all_principal, 3)

        return (sum_of_all_principal, avarage_interest_rate)
        

