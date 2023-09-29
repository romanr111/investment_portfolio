from src.brokers.ib import InteractiveBrokers
from src.crypto.bin import BinanceFiltered
from src.crypto.crypto import Crypto, CryptoValue, CoinMarketCapFetcher
from src.cash_fixed_income.cash_summary import Cash
from src.dasha.dasha import Portfolio

ib = InteractiveBrokers()
crypto = Crypto()
crypto_value = CryptoValue()
cash = Cash()
dasha = Portfolio(ib)
binance = BinanceFiltered()
quantities = Crypto.get_all_crypto_quantity(binance)
fetcher = CoinMarketCapFetcher()
market_values = CryptoValue.get_market_value(quantities, fetcher)
total_market_value = CryptoValue.get_crypto_total_market_value(market_values)


class Portfolio_Allocations:
    ib_positions = ib.get_portfolio_positions()
    total_stocks_mkt_val = ib_positions["Total_Stocks_Value"]
    bonds_mkt_value = ib_positions["Bonds"]
    total_reits_mkt_val = ib_positions["REIT"]
    ib_gold_mkt_value = ib_positions["Gold"]
    comm_mkt_value = ib_positions["Commodities"]
    crypto_mkt_value = crypto
    gld = ib_positions["Gold"]
    cash_balance = cash.total_cash()

    dasha_net_worth = dasha.get_portfolio_value()

    # TODO Check net-worth calculation!
    net_worth = (
        total_stocks_mkt_val
        + bonds_mkt_value
        + total_reits_mkt_val
        + ib_gold_mkt_value
        + comm_mkt_value
        + crypto_mkt_value
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
    cash_allocation = calculate_allocation(cash_balance, net_worth)

    actual_allocations = {
        "I4:K4": stocks_allocation,
        "I5:K5": bonds_allocation,
        "I6:K6": reit_allocation,
        "I7:K7": crypto_allocation,
        "I8:K8": gold_allocation,
        "I9:K9": commodities_allocation,
        "I11:K11": cash_allocation,
    }

    expected_allocations = {
        "Stocks": 35,
        "Bonds": 5,
        "REIT": 5,
        "Crypto": 5,
        "Gold": 1,
        "Commodities": 5,
        "Cash & Equivalents": 38,
    }
