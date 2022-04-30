import sys
sys.path.append(".")

from src.brokers import ib
from src.cash_fixed_income import mono, privatbank, wise
from src.crypto.crypto_data import Crypto
from .fixed_income import EstateGuru, PeerBerry

class Cash:
    
    mono = mono.Mono()
    privat = privatbank.Privat()
    wise = wise.Wise()
    
    estateguru = EstateGuru()
    peerberry = PeerBerry()
    crypto = Crypto()

    total_crypto_interest_earning = crypto.get_all_crypto_fixed_income()['TotalInterestEarningCrypto']

    def get_all_p2p_income(self):
        p2p = {
            'estateguru': self.estateguru.usd_balance,
            'peerberry': self.peerberry.usd_balance,
        }
        return p2p


    def get_all_fixed_income(self):
        x = {
            'crypto': self.total_crypto_interest_earning
        }
        return x



