import logging
import requests
from requests.exceptions import HTTPError


def sort_dict(dict):
    sort = sorted(dict.items(), key=lambda item: item[1], reverse=True)
    return {k: v for k, v in sort}


def calculate_total_mkt_value(dict):
    return round(sum([value for value in dict.values()]))


def convert(from_currency, to_currency, amount):
    exchange_api = "https://api.exchangerate-api.com/v4/latest/USD"
    data = requests.get(exchange_api).json()
    currencies = data["rates"]
    if from_currency != "USD":
        amount = amount / currencies[from_currency]

    # limiting the precision to 4 decimal places
    amount = round(amount * currencies[to_currency], 2)
    return amount


def perform_request(api, param="", header={}, verify=True):
    """
    Perform an HTTP GET request with enhanced error handling and logging.
    
    Args:
        api: Base API URL
        param: URL parameters to append
        header: Request headers
        verify: Whether to verify SSL certificates
        
    Returns:
        Parsed JSON response as a dictionary, or None if the request failed
    """
    url = api + param
    logger = logging.getLogger(__name__)
    
    try:
        logger.debug(f"Making request to: {url}")
        response = requests.get(url, headers=header, verify=verify, timeout=10)
        
        # Log response status and headers for debugging
        logger.debug(f"Response status: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        # Check for HTTP errors
        response.raise_for_status()
        
        try:
            response_data = response.json()
            logger.debug(f"Successfully parsed JSON response from {url}")
            return response_data
            
        except ValueError as json_err:
            logger.error(f"Failed to parse JSON response from {url}: {str(json_err)}")
            logger.debug(f"Response content: {response.text[:500]}")
            return None
            
    except requests.exceptions.HTTPError as http_err:
        status_code = http_err.response.status_code if hasattr(http_err, 'response') else 'unknown'
        logger.error(f"HTTP {status_code} error for {url}: {str(http_err)}")
        
        # For 404 errors, log more details
        if status_code == 404:
            logger.debug(f"404 details - URL: {url}")
            if hasattr(http_err, 'response') and http_err.response is not None:
                logger.debug(f"Response content: {http_err.response.text[:500]}")
        
        return None
        
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request failed for {url}: {str(req_err)}")
        return None
        
    except Exception as err:
        logger.error(f"Unexpected error for {url}: {str(err)}", exc_info=True)
        return None
