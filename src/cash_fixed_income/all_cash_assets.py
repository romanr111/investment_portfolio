import sys

sys.path.append(".")
from ..fixed_income.fixed_income import FixedIncomeAsset, EstateGuru, PeerBerry
from src.cash_fixed_income import mono, privatbank, wise
from src.crypto import Crypto


class Cash:
    def __init__(self, ib_cash):
        self.cash = 100000
        self.lended = 700
        self.my_debt = -3000
        self.mono = mono.Mono()
        self.privat = privatbank.Privat()
        self.wise = wise.Wise()
        self.ib_cash = ib_cash
        self.crypto = Crypto()
        self.estateguru = EstateGuru()
        self.peerberry = PeerBerry()
        self.asset = FixedIncomeAsset()

    def calculate_all_non_invested_cash(self):
        all_cash = {
            "Cash": self.cash,
            "Lended": self.lended,
            "My_Debt": self.my_debt,
            "Mono": self.mono.get_mono(),
            "Privat": self.privat.BALANCE,
            "Wise": self.wise.usd_balance,
            "IB_Free_Cash": self.ib_cash,
            "Crypto_Free_Cash": self.crypto.get_all_free_cash_in_stablecoins(),
        }
        print(all_cash)
        total_cash = 0
        for cash in all_cash.values():
            total_cash += cash

        return total_cash

    def get_montly_fixed_income(self):
        all_principal, avg_interest = self.get_all_fixed_income_info()[
            "TotalFixedIncome"
        ]
        return round((all_principal * avg_interest) / 12)

    def get_all_fixed_income_info(self):
        total_fixed_income = {
            "Crypto": self.crypto.get_all_crypto_fixed_income()[
                "TotalInterestEarningCrypto"
            ],
            "P2P": self.get_all_p2p_income()["Total_P2P"],
        }
        total_fixed_income = self.asset.calc_avg_interest_rate(
            total_fixed_income, "TotalFixedIncome"
        )
        return total_fixed_income

    def get_all_p2p_income(self):
        p2p = {
            "estateguru": self.estateguru.usd_balance,
            "peerberry": self.peerberry.usd_balance,
        }
        p2p = self.asset.calc_avg_interest_rate(p2p, "Total_P2P")
        return p2p
