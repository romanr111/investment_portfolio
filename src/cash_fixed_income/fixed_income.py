import helpers

class FixedIncomeAsset:

    def calc_avg_interest_rate(self, dict, key):
        ''' Calcualates avarage weighted interest rate in initial dict. \
            Adds that value into the dict.
            
        Args:
            dict: Values should be tupples of two items 1) Principal; 2) Interest.
            key: Name for the group of assets.
        Returns: 
            Dict: Original dict plus additional key/value for 1) Sum of all principal; 2) Avg interest. 
        '''
        sum_of_all_principal = 0
        sum_of_all_interest = 0

        for principal, interest in dict.values():
            sum_of_all_principal += principal
            sum_of_all_interest += principal * interest
    
        avarage_interest_rate = round(sum_of_all_interest / sum_of_all_principal, 3)
        dict[key] = (sum_of_all_principal, avarage_interest_rate)
        
        return dict

class EurAsset():
    EUR_BALANCE = (1, 0.1)
    
    @property
    def usd_balance(self):
        ''' 
        Returns 
            tupple: USD represantation of EUR asset along with interest rate
        '''
        eur_to_usd = round(helpers.convert('EUR', 'USD', self.EUR_BALANCE[0]))
        return (eur_to_usd, self.EUR_BALANCE[1])


class EstateGuru(FixedIncomeAsset, EurAsset):
    EUR_BALANCE = (3712, 0.09)
    
    
class PeerBerry(FixedIncomeAsset, EurAsset):
    EUR_BALANCE = (10129, 0.1)


