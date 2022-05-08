import sys
import csv

from helpers import perform_request, sort_dict, convert
sys.path.append(".")
import support_data.portfolio_filters as filters
from support_data.endpoints import SUMMARY_API, POSITIONS_API


class InteractiveBrokers:
    def __init__(self):
        self.summary = perform_request(SUMMARY_API, verify=False)
        self.all_portfolio_info = perform_request(POSITIONS_API, verify=False)

    @property
    def cash_balance(self): 
        balance = round(self.summary['totalcashvalue']['amount'])
        return balance 
       
    def get_portfolio_positions(self): 
        public_reit_names = self._get_public_reits_names()

        portfolio = {
            'China_Stocks': {},
            'Bank_Stocks': {},
            'USA_Stocks': {},
            'Short_Stocks': {},
            'REIT': {},
            'Gold': {},
            'Commodities': {},
        }
        for position in self.all_portfolio_info:
            stock = position['contractDesc']
            mkt_value = round(position['mktValue'])
            stock_name_value = {stock: mkt_value}

            if mkt_value < 0:
                portfolio['Short_Stocks'].update(stock_name_value)
            elif stock in filters.CHINA or stock in filters.CHINA_ADR:
                if stock in filters.CHINA:
                    usd_stock_price = round(convert('HKD', 'USD', mkt_value))
                    portfolio['China_Stocks'].update({ stock: usd_stock_price })
                else:
                    portfolio['China_Stocks'].update(stock_name_value)
            elif stock in filters.BANKS:
                portfolio['Bank_Stocks'].update(stock_name_value)
            elif (stock in public_reit_names) or (stock in filters.REITS):
                portfolio['REIT'].update(stock_name_value)
            elif stock in filters.GOLD:
                portfolio['Gold'].update(stock_name_value)
            elif stock in filters.COMM:
                portfolio['REIT'].update(stock_name_value)
            else:   
                portfolio['USA_Stocks'].update(stock_name_value)
            portfolio['REIT'].update({'LAND': 200})

            for k, dict in portfolio.items():
                portfolio[k] = sort_dict(dict)
        return portfolio

    def calculate_total_mkt_value(self, dict):
        return round(sum([value for value in dict.values()]))

    def _get_public_reits_names(self):
        reit_list = []
        f = open('support_data/List_U.S._REITs.csv')
        csv_f = csv.reader(f)
        for row in csv_f:
            reit_list.append(str(row[0]))
        return reit_list


    '''
    def get_stocks_quantity(self):   
        stocks = { stock['contractDesc']: round(stock['position']) for stock in self.portfolio }
        return stocks
    '''
