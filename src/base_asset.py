from functools import lru_cache
from data.cash_and_fi_data import *


class Asset:
    def __init__(self, principal, interest):
        self._principal = principal  # changed to protected member
        self._interest = interest  # changed to protected member

    @property
    def principal(self):
        return self._principal

    @principal.setter
    def principal(self, value):
        self._principal = value

    @property
    def interest(self):
        return self._interest

    @interest.setter
    def interest(self, value):
        self._interest = value

    @property
    def data(self):
        return {self.__class__.__name__: (self._principal, self._interest)}

    @lru_cache(maxsize=None)
    def calculate_weighted_interest(self, data):
        """
        Calculate weighted interest for given data.

        Arguments:
        - data: Either a tuple or a tuple of tuples representing (principal, interest)

        Returns:
        - A tuple containing total principal and average interest
        """
        total_principal = sum(principal for principal, _ in data)

        if total_principal:
            weighted_interest = sum(
                principal * interest for principal, interest in data
            )
            avg_interest = round(weighted_interest / total_principal, 3)
        else:
            avg_interest = 0

        return total_principal, avg_interest

    def verify_calculation(self, actual, expected):
        """
        Verify that the calculated amount closely matches the expected value.

        Args:
        - expected: Expected amount.

        Raises:
        - AssertionError: If the difference between the calculated and expected value exceeds 1%.
        """
        percentage_diff = ((expected - actual) / abs(actual)) * 100 if actual else 0
        msg = f"Incorrect principal amount: Actual {expected}, Expected {actual}, Diff: {percentage_diff}%"
        assert -1 < percentage_diff < 1, msg
