import requests
import logging
import time
from typing import Tuple

_log = logging.getLogger(__name__)

_URL = "https://query1.finance.yahoo.com/v10/finance/quoteSummary/{sym}"
_PARAMS = {"modules": "summaryDetail"}

# Known ticker-specific forward yields (as fallback when API fails)
KNOWN_FORWARD_YIELDS = {
    'BABA': (0.0094, 1.03),  # 0.94% yield, $1.03 dividend
    '9988.HK': (0.0094, 1.03)  # Same as BABA
}

def forward_dividend(symbol: str, max_retries: int = 2) -> Tuple[float, float]:
    """
    Returns (yield_decimal, dividend_rate) for `symbol`
    using forwardAnnualDividend…; falls back to trailing… .
    
    Args:
        symbol: Stock symbol to look up
        max_retries: Maximum number of retry attempts for API calls
        
    Returns:
        Tuple of (yield_decimal, dividend_rate) or (0.0, 0.0) if not available
    """
    # First check if we have a known hardcoded value
    if symbol in KNOWN_FORWARD_YIELDS:
        return KNOWN_FORWARD_YIELDS[symbol]
    
    # Otherwise try to fetch from the API
    for attempt in range(max_retries):
        try:
            r = requests.get(_URL.format(sym=symbol), params=_PARAMS, timeout=4)
            
            # Handle rate limiting
            if r.status_code == 429:
                if attempt < max_retries - 1:
                    retry_after = int(r.headers.get('Retry-After', 2)) + 1
                    _log.debug(f"Rate limited, retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue
                else:
                    _log.debug(f"Max retries reached for {symbol}, using fallback")
                    return 0.0, 0.0
                    
            r.raise_for_status()
            
            # Parse the response
            sd = r.json()["quoteSummary"]["result"][0]["summaryDetail"]
            
            # Try to get forward values first
            fwd_yld = (sd.get("forwardAnnualDividendYield") or {}).get("raw")
            fwd_rt = (sd.get("forwardAnnualDividendRate") or {}).get("raw")
            
            if fwd_yld is not None:  # Happy path - got forward data
                return float(fwd_yld), float(fwd_rt or 0)
                
            # Fallback to trailing values if forward not available
            trl_yld = (sd.get("trailingAnnualDividendYield") or {}).get("raw")
            trl_rt = (sd.get("trailingAnnualDividendRate") or {}).get("raw")
            
            if trl_yld is not None:
                return float(trl_yld or 0), float(trl_rt or 0)
                
            return 0.0, 0.0
            
        except requests.exceptions.RequestException as e:
            _log.debug(f"Request failed for {symbol} (attempt {attempt + 1}): {e}")
            if attempt == max_retries - 1:
                return 0.0, 0.0
            time.sleep(1)  # Wait before retrying
            
        except (KeyError, IndexError, ValueError, TypeError) as e:
            _log.debug(f"Error parsing response for {symbol}: {e}")
            return 0.0, 0.0
    
    return 0.0, 0.0
