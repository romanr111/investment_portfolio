import requests

class CurrencyConverter():
    def __init__(self):
            exchange_api = 'https://api.exchangerate-api.com/v4/latest/USD'
            self.data = requests.get(exchange_api).json()
            self.currencies = self.data['rates']

    def convert(self, from_currency, to_currency, amount): 
        if from_currency != 'USD' : 
            amount = amount / self.currencies[from_currency] 
  
        # limiting the precision to 4 decimal places 
        amount = round(amount * self.currencies[to_currency], 2) 
        return amount