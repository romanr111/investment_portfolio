
from src.helpers.convertor import CurrencyConverter

class EurAsset:
    EUR_BALANCE = (1, 0.1)
    convertor = CurrencyConverter()
    
    @property
    def usd_balance(self):
        eur_to_usd = self.convertor.convert('EUR', 'USD', self.EUR_BALANCE[0])
        return (eur_to_usd, self.EUR_BALANCE[1])


class EstateGuru(EurAsset):
    EUR_BALANCE = (3712, 0.9)
    
    
class PeerBerry(EurAsset):
    EUR_BALANCE = (10129, 0.1)


