from src.helpers.convertor import CurrencyConverter

class Wise():
    EUR_BALANCE = 297

    @property
    def usd_balance(self):
        ''' 
        Returns 
            tupple: USD represantation of EUR asset along with interest rate
        '''
        convertor = CurrencyConverter()
        eur_to_usd = convertor.convert('EUR', 'USD', self.EUR_BALANCE)
        return eur_to_usd




'''

curl -X GET https://api.transferwise.com/profiles/29208436/balances -H "Authorization: Bearer d91292d8-ff32-4db9-b854-1f3e0e5f5474"

curl -X GET https://api.sandbox.transferwise.tech/v4/profiles/29208436/balances?types=STANDARD \
     -H "Authorization: Bearer d91292d8-ff32-4db9-b854-1f3e0e5f5474"

curl -X GET https://api.sandbox.transferwise.tech/v1/profiles/29208436/account-details -H "Authorization: Bearer d91292d8-ff32-4db9-b854-1f3e0e5f5474"
'''
