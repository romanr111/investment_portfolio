import sys

from src.cash_fixed_income import fixed_income
sys.path.append(".")

from src.brokers import ib
from src.cash_fixed_income import mono, privatbank, wise
from src.crypto.all_crypto import Crypto
from .fixed_income import FixedIncomeAsset, EstateGuru, PeerBerry

class Cash:
    
    def __init__(self) -> None:        
        self.mono = mono.Mono()
        self.privat = privatbank.Privat()
        self.wise = wise.Wise()
        self.estateguru = EstateGuru()
        self.peerberry = PeerBerry()
        self.crypto = Crypto()
        self.asset = FixedIncomeAsset()

    def get_total_fixed_income(self):
        fixed_income = self.asset.calc_avg_interest_rate(self.get_all_fixed_income(), 'FixedIncome')
        all_principal, avg_interest = fixed_income['FixedIncome']
        earnings = {
            'All_Principal': all_principal,
            'Avg_Interest': avg_interest,
            'Monthly_Earnings': round((all_principal * avg_interest) / 12)
        }
        return earnings

    def get_all_fixed_income(self):
        all_fixed = {
            'Crypto': self.crypto.get_all_crypto_fixed_income()['TotalInterestEarningCrypto'],
            'P2P': self.get_all_p2p_income()['P2P']
        }
        return all_fixed

    def get_all_p2p_income(self):
        p2p = {
        'estateguru': self.estateguru.usd_balance,
        'peerberry': self.peerberry.usd_balance,
        }
        p2p = self.asset.calc_avg_interest_rate(p2p,'P2P')
        return p2p






