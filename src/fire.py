from portfolio_allocation import Portfolio_Allocations
from dividends import Dividends

alloc = Portfolio_Allocations()
div = Dividends()


# FIRE - Financial Independence, Retire Early


class FinancialFreedom:
    def calculate_financial_freedom_goal_progress(self):
        goal = 400000
        current = alloc.net_worth
        goal_progress = round((current / goal) * 100, 2)
        return str(goal_progress) + "%"
