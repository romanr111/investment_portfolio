# DEPRECATED MODULE - No longer in use
# This module is kept for reference but all functionality has been disabled

import logging

logger = logging.getLogger(__name__)


class Wise:
    """
    DEPRECATED: Wise integration module.

    This class is no longer used and all functionality has been disabled.
    It now returns empty/zero values to maintain compatibility with existing code.
    """

    def __init__(self):
        logger.info(
            "Wise module is deprecated and disabled - using stub implementation"
        )
        self.balances = {}

    def fetch_balances(self):
        """DEPRECATED: Always returns empty dict"""
        return {}

    def get_eur_to_usd_balance(self):
        """DEPRECATED: Always returns 0"""
        return 0

    def get_usd_balance(self):
        """DEPRECATED: Always returns 0"""
        return 0

    def get_total_balance_in_usd(self):
        """DEPRECATED: Always returns 0"""
        print("Wise module is deprecated - returning 0 balance")
        return 0
