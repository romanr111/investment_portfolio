from support_data.endpoints import MONO_API, MONO_PERSONAL_TOKEN
from src.helpers.convertor import CurrencyConverter
from src.helpers.requests_handler import RequestsHandler

class Mono:
    request = RequestsHandler()
    converter = CurrencyConverter()

    def get_mono(self):
        totalMoney = 0
        usd = 0
        eur = 0
        uah = 0

        account_info = self.request.perform_request(MONO_API, header = MONO_PERSONAL_TOKEN) 
        accounts = account_info['accounts']

        for acc in accounts:
            if acc['balance'] > 0:
                if acc['currencyCode'] == 980:
                    if acc['creditLimit'] > 0:
                        uah = (acc['balance'] - acc['creditLimit']) / 100
                    else: 
                        uah = acc['balance'] / 100
                elif acc['currencyCode'] == 840:
                    usd = acc['balance'] / 100
                elif acc['currencyCode'] == 978:      
                    eur = acc['balance'] / 100
        
        uah_to_usd = self.converter.convert('UAH', 'USD', uah)

        if (eur > 0):
            eur_to_usd = self.converter.convert('EUR', 'USD', eur)
        else: eur_to_usd = 0

        totalMoney = usd + uah_to_usd + eur_to_usd

        print('Mono cash!')
        print(f'USD - {usd}, UAH/USD - {uah_to_usd}, EUR/USD - {eur_to_usd}')
        print(f'TOTAL MONO - {round(totalMoney)}')

        return round(totalMoney)      