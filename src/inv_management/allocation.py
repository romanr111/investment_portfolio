from ib import InteractiveBrokers
from crypto_data import CryptoData
from cash_balance import CashBalance
from dasha_portfolio import DashaPortfolio

ib = InteractiveBrokers()
crypto = CryptoData()
cash = CashBalance()
dasha = DashaPortfolio()


class Portfolio_Allocations:
    total_stocks_mkt_val = ib.get_stocks_total_mkt_value()
    bonds_mkt_value = ib.get_bonds_total_mkt_value()
    total_reits_mkt_val = ib.get_reits_total_mkt_value()
    ib_gold_mkt_value = ib.get_gold_total_mkt_value()
    comm_mkt_value = ib.get_commodities_total_mkt_value()
    crypto_mkt_value = crypto.getCryptoTotalValue()
    mining_mkt_value = crypto.getMiningValue()
    gld = ib_gold_mkt_value
    cash_balance = cash.get_cash_balance()

    dasha_net_worth = dasha.get_portfolio_value()

    # TODO Check net-worth calculation!
    net_worth = (
        total_stocks_mkt_val
        + bonds_mkt_value
        + total_reits_mkt_val
        + ib_gold_mkt_value
        + comm_mkt_value
        + crypto_mkt_value
        + mining_mkt_value
        + cash_balance
    ) - dasha_net_worth

    def calculate_allocation(inv_type, net_worth):
        alloc = round((inv_type / net_worth) * 100)
        return alloc

    stocks_allocation = calculate_allocation(total_stocks_mkt_val, net_worth)
    bonds_allocation = calculate_allocation(bonds_mkt_value, net_worth)
    reit_allocation = calculate_allocation(total_reits_mkt_val, net_worth)
    gold_allocation = calculate_allocation(gld, net_worth)
    commodities_allocation = calculate_allocation(comm_mkt_value, net_worth)
    crypto_allocation = calculate_allocation(crypto_mkt_value, net_worth)
    mining_allocation = calculate_allocation(mining_mkt_value, net_worth)
    cash_allocation = calculate_allocation(cash_balance, net_worth)

    actual_allocations = {
        "I4:K4": stocks_allocation,
        "I5:K5": bonds_allocation,
        "I6:K6": reit_allocation,
        "I7:K7": crypto_allocation,
        "I8:K8": gold_allocation,
        "I9:K9": commodities_allocation,
        "I10:K10": mining_allocation,
        "I11:K11": cash_allocation,
    }

    expected_allocations = {
        "Stocks": 35,
        "Bonds": 5,
        "REIT": 5,
        "Crypto": 5,
        "Gold": 1,
        "Commodities": 5,
        "Mining": 2,
        "Cash & Equivalents": 38,
    }
