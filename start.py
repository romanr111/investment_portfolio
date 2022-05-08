import time
#from src.cash_fixed_income.all_cash_assets import Cash
#from src.crypto.all_crypto import Crypto
#from src.phys_gold import PhysGold
from src.brokers.ib import InteractiveBrokers


def main():

    ib = InteractiveBrokers()
    portfolio = ib.get_portfolio_positions()

    print('\n')
    print(f'cash balance: {ib.cash_balance}')
    print('\n')
    print(portfolio)
    print('\n')
    print(portfolio['China_Stocks'])
    print('\n')
    print(ib.calculate_total_mkt_value(portfolio['China_Stocks']))

    '''
    print(f'Monthly Fixed Income: {c.get_montly_fixed_income()}')

    print('\n')
    print(f'Gold Value: {gold.get_total_phys_gold_value()}')

    print('\n')
    print(f'All Fixed Income: {c.get_all_fixed_income_info()}')
    print('\n')
    print(c.get_all_p2p_income())
    print('\n')
    print(crypto.get_all_crypto_fixed_income())
    print('\n')
    '''

if __name__ == "__main__":
    start_time = time.time()
    main()
    print("--- TOTAL: %s seconds ---" % (time.time() - start_time))

