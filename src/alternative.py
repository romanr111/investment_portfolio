from data.api_keys import PHYS_GOLD_API_KEY
from data.endpoints import PHYS_GOLD_ENDPOINT
import src.helpers as helpers

CURRENCY = "USD"
METAL = "XAU"
GRAMS_AVAILABLE = 0
PARAM = METAL + "/" + CURRENCY
PHYS_GOLD_HEADERS = {"x-access-token": PHYS_GOLD_API_KEY}

INVESTMENT_EQUIPMENT = 340 + 6000


class PhysGold:
    responce = helpers.perform_request(
        PHYS_GOLD_ENDPOINT, PARAM, header=PHYS_GOLD_HEADERS
    )

    def get_phys_gold_g_price(self):
        price = self.responce["prev_close_price"]
        gram = round(price) / 31.1
        return gram

    def get_total_phys_gold_value(self):
        gram_price = self.get_phys_gold_g_price()
        ua_market = 1.07
        total = gram_price * GRAMS_AVAILABLE * ua_market
        return round(total)
