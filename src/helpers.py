import logging
import requests


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
        response = requests.get(url, headers=header, verify=verify, timeout=10)
        response.raise_for_status()

        try:
            response_data = response.json()
            return response_data

        except ValueError as json_err:
            logger.error(f"Failed to parse JSON response from {url}: {str(json_err)}")
            return None

    except requests.exceptions.HTTPError as http_err:
        status_code = (
            http_err.response.status_code
            if hasattr(http_err, "response")
            else "unknown"
        )
        logger.error(f"HTTP {status_code} error for {url}: {str(http_err)}")
        return None

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request failed for {url}: {str(req_err)}")
        return None

    except Exception as err:
        logger.error(f"Unexpected error for {url}: {str(err)}")
        return None


def perform_post_request(url, json_body, header=None, verify=True, timeout=30):
    """
    Perform an HTTP POST request with JSON body; mirrors perform_request error handling.
    """
    header = dict(header or {})
    if "Content-Type" not in header:
        header["Content-Type"] = "application/json"
    logger = logging.getLogger(__name__)

    try:
        response = requests.post(
            url, headers=header, json=json_body, verify=verify, timeout=timeout
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as json_err:
            logger.error(f"Failed to parse JSON response from {url}: {str(json_err)}")
            return None

    except requests.exceptions.HTTPError as http_err:
        status_code = (
            http_err.response.status_code
            if hasattr(http_err, "response") and http_err.response is not None
            else "unknown"
        )
        logger.error(f"HTTP {status_code} error for {url}: {str(http_err)}")
        return None

    except requests.exceptions.RequestException as req_err:
        logger.error(f"Request failed for {url}: {str(req_err)}")
        return None

    except Exception as err:
        logger.error(f"Unexpected error for {url}: {str(err)}")
        return None
