# FIRE - Financial Independence, Retire Early


class FinancialFreedom:
    def __init__(self, allocation):
        self.allocation = allocation

    def calculate_financial_freedom_goal_progress(self):
        goal = 400000
        current = self.allocation.net_worth
        goal_progress = round((current / goal) * 100, 2)
        return str(goal_progress) + "%"


def main():
    ff = FinancialFreedom()
    print(ff.calculate_financial_freedom_goal_progress())


if __name__ == "__main__":
    main()
