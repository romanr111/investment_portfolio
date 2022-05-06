from src.cash_fixed_income.all_cash_assets import Cash
from src.crypto.all_crypto import Crypto
from src.phys_gold import PhysGold
from src.brokers.ib import IBFiltered


if __name__ == "__main__":

    c = Cash()
    crypto = Crypto()
    gold = PhysGold()
 
    print('\n')
    ib = IBFiltered()
    print('\n')
    print(ib.get_portfolio_positions())
    print('\n')
    print('\n')
    print(ib.get_cash_balance())
    print('\n')
    print(ib.get_banks_positions())
    print('\n')
    print(ib.get_banks_total_mkt_value())

    print(f'Cash balance: {c.calculate_all_non_invested_cash()}')
    print('\n')
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
