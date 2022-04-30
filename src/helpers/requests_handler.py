import requests
from requests.exceptions import HTTPError

class RequestsHandler:
    def perform_request(self, api, param = '', header = {}, verify = True):
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