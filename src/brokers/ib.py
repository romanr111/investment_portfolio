import sys
import csv
sys.path.append(".")
from support_data.endpoints import SUMMARY_API, POSITIONS_API
from src.helpers.requests_handler import RequestsHandler


class InteractiveBrokers(): 
     
    def __init__(self) -> None: 
        r = RequestsHandler()    
        self.summary = r.perform_request(SUMMARY_API, verify=False)
        self.portfolio = r.perform_request(POSITIONS_API, verify=False)
        print(f'summary: {self.summary}')
        print('\n')
        print(f'portfolio: {self.portfolio}')

    def get_cash_balance(self): 
        short_selling_amount = self.get_short_selling_amount()    
        balance = round(self.summary['totalcashvalue']['amount'])
        print(f'IB Short: {short_selling_amount}')
        return balance + short_selling_amount

    def get_portfolio_positions(self):   
        stocks = {}
        for stock in self.portfolio:
            stocks.update({stock['contractDesc'] : round(stock['mktValue']) })

        sort = sorted(stocks.items(), key = lambda item: item[1], reverse=True)
        sorted_stocks =  {k: v for k, v in sort}

        return sorted_stocks

    def get_short_selling_amount(self):
        portfolio = self.get_portfolio_positions()   
        short_amout = 0
        for _, value in portfolio.items():
            if value < 0:
                short_amout += value
        return short_amout

class IBFiltered(InteractiveBrokers):

    def sort_dict(self, dict):
        sort = sorted(dict.items(), key = lambda item: item[1], reverse=True)
        return  {k: v for k, v in sort}

    def get_banks_positions(self):
        portfolio = self.get_portfolio_positions()
        bank_positions = {}
        for stock, value in portfolio.items():
            if stock in ['TD', 'BNS', 'BAC', 'USB']:
                bank_positions[stock] = value
        return self.sort_dict(bank_positions)

    def get_banks_total_mkt_value(self):
        banks = self.get_banks_positions()
        mktValue = 0
        for value in banks.values():
            mktValue += value

        return mktValue

##################################################################
##################################################################

    def get_reits_info(self):
        my_reits = []
        reit_list = []
        f = open('List_U.S._REITs.csv')
        csv_f = csv.reader(f)
        for row in csv_f:
            reit_list.append(str(row[0]))
        for stock in self.portfolio:
            if (stock['contractDesc'] in reit_list) or (stock['contractDesc'] in ['VNQ', 'VNQI', 'FREL', 'HHC', 'PHM']):
                my_reits.append(stock)

        return my_reits 

    def get_reits_positions(self):
        reits = self.get_reits_info()
        reits_positions = {}
        for reit in reits:  
            reits_positions.update({ reit['contractDesc'] : round(reit['mktValue']) })
        reits_positions['LAND'] = 430
        sort = sorted(reits_positions.items(), key = lambda item: item[1], reverse=True)
        sorted_reits =  {k: v for k, v in sort}

        return sorted_reits   
    
    def get_reits_total_mkt_value(self):
        info = self.get_reits_info()
        mktValue = round(sum([ stock['mktValue'] for stock in info ]))
        mkt_value = 430 + mktValue
        return mkt_value
        
    def get_gold_positions(self):
        gold = [stock for stock in self.portfolio if stock['contractDesc'] in ['GLD', 'IAU', 'SGOL', 'PHYS'] ]
        gold_positions = {stock['contractDesc'] : round(stock['mktValue']) for stock in gold}
        return gold_positions

    def get_gold_total_mkt_value(self):
        info = self.get_gold_positions()
        mktValue = round(sum([value for value in info.values()]))
        return mktValue

    def get_commodities_positions(self):
        commodities = [ stock for stock in self.portfolio if stock['contractDesc'] in ['SLV', 'CPER', 'DBC', 'PDBC', 'COMB', 'BCI'] ]      
        commodities_positions = { stock['contractDesc']: round(stock['mktValue']) for stock in commodities }
        sort = sorted(commodities_positions.items(), key = lambda item: item[1], reverse=True)
        sorted_comm =  {k: v for k, v in sort}
        return sorted_comm

    def get_commodities_total_mkt_value(self):
        info = self.get_commodities_positions()
        mktValue = round(sum([value for value in info.values()]))
        return mktValue

    def get_stocks_without_banks_reits_gld_cmd(self):
        banks = self.get_banks_positions()
        reits = self.get_reits_positions()
        gld = self.get_gold_positions()
        cmd = self.get_commodities_positions()

        brgc = list(banks.keys()) + list(reits.keys()) + list(gld.keys()) + list(cmd.keys())
        stocks_positions = { stock['contractDesc'] : round(stock['mktValue']) for stock in self.portfolio if stock['contractDesc'] not in brgc }
        sorted_stocks = {}

        for stock, price in stocks_positions.items():
            if stock in ['9988', '700']:
                usd_stock_price = round(converter.convert('HKD', 'USD', price))
                sorted_stocks.update({stock: usd_stock_price })
            # Exclude short selling    
            elif price < 0:
                self.short_selling_amount += price
            else:
                sorted_stocks[stock] = price

        print(f'Function that calculates short_selling_amount ----> {self.short_selling_amount}')

        sort = sorted(sorted_stocks.items(), key = lambda item: item[1], reverse=True)
        sorted_stocks =  {k: v for k, v in sort}

        return sorted_stocks

    def get_stocks_total_mkt_value(self):
        banks_total_mkt_value = self.get_banks_total_mkt_value()
        non_bank_stocks_dict = self.get_stocks_without_banks_reits_gld_cmd()        
        nonBanksMarketValue = round(sum([value for value in non_bank_stocks_dict.values()]))
        total = banks_total_mkt_value + nonBanksMarketValue
        return total
    
    def get_stocks_quantity(self):   
        stocks = { stock['contractDesc']: round(stock['position']) for stock in self.portfolio }
        return stocks

