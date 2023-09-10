import requests
from requests.exceptions import HTTPError

def sort_dict(dict):
    sort = sorted(dict.items(), key = lambda item: item[1], reverse=True)
    return  {k: v for k, v in sort}

def convert(from_currency, to_currency, amount):
    exchange_api = 'https://api.exchangerate-api.com/v4/latest/USD'
    data = requests.get(exchange_api).json()
    currencies = data['rates'] 
    if from_currency != 'USD' : 
        amount = amount / currencies[from_currency] 

    # limiting the precision to 4 decimal places 
    amount = round(amount * currencies[to_currency], 2) 
    return amount

def perform_request(api, param = '', header = {}, verify = True):
    try:
        response = requests.get(api + param,  headers = header, verify = verify)
        # If the response was successful, no Exception will be raised
        response.raise_for_status()
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')  
    except Exception as err:
        print(f'Other error occurred: {err}')
    else:
        print(f'Success! API - {api}')
        response = response.json()
        return response