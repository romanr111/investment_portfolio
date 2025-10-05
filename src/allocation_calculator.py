class AllocationCalculator:
    def __init__(self, data):
        self.data = data

    def get_sorted_sector_allocations(self) -> dict:
        return self._calculate_allocations(self.data)

    @staticmethod
    def _calculate_allocations(data: dict) -> dict:
        from decimal import Decimal, ROUND_HALF_UP, getcontext

        getcontext().prec = 10

        def to_decimal(value) -> Decimal:
            try:
                return Decimal(str(value))
            except Exception:
                return Decimal("0")

        def sum_as_decimal(values) -> Decimal:
            return sum((to_decimal(v) for v in values), Decimal("0"))

        total_assets = to_decimal(data.get("TOTAL_ASSETS", 0))
        if total_assets == 0:
            return {"allocation_breakdown": {}, "total_fixed_income_pct": 0.0}

        ib_data = data.get("IB_DATA", {})

        bonds_value = sum_as_decimal(ib_data.get("Bonds", {}).values())
        stocks_value = to_decimal(ib_data.get("Total Stocks Value", 0))
        commodities_value = sum_as_decimal(ib_data.get("Commodities", {}).values())
        precious_metals_value = sum_as_decimal(ib_data.get("Precious Metals", {}).values())
        reit_value = sum_as_decimal(ib_data.get("REIT", {}).values())

        crypto_data = data.get("CRYPTO_DATA", {})
        crypto_spot_value = to_decimal(crypto_data.get("Total_Crypto_Value", 0))

        fi_data = data.get("FIXED_INCOME_DATA", {})
        group_interest = fi_data.get("group_weighted_interest", {})
        crypto_lending_value = to_decimal(group_interest.get("Crypto Landing", (0,))[0])
        p2p_lending_value = to_decimal(group_interest.get("p2p_lending", (0,))[0])

        cash_total = data.get("CASH_DATA", {}).get("Total", 0)
        cash_value = to_decimal(cash_total)

        other_assets = data.get("OTHER_ASSETS", {})
        if other_assets:
            other_value = sum_as_decimal(other_assets.values())
        else:
            try:
                from data.assets_data import OTHER_BETS

                other_value = to_decimal(OTHER_BETS)
            except Exception:
                other_value = Decimal("0")

        category_values = {
            "Bonds": bonds_value,
            "Stocks": stocks_value,
            "Commodities": commodities_value,
            "Precious Metals": precious_metals_value,
            "Crypto Coins": crypto_spot_value,
            "Crypto Lending": crypto_lending_value,
            "P2P Lending": p2p_lending_value,
            "REIT": reit_value,
            "Cash": cash_value,
            "Other Bets": other_value,
        }

        hundred = Decimal("100")
        quantize_unit = Decimal("0.1")

        raw_percentages = {
            cat: (value / total_assets * hundred) if total_assets else Decimal("0")
            for cat, value in category_values.items()
        }

        rounded_percentages = {
            cat: raw.quantize(quantize_unit, rounding=ROUND_HALF_UP)
            for cat, raw in raw_percentages.items()
        }

        total_rounded = sum(rounded_percentages.values())
        discrepancy = hundred - total_rounded

        if discrepancy != Decimal("0"):
            steps = int(
                (abs(discrepancy) / quantize_unit).to_integral_value(
                    rounding=ROUND_HALF_UP
                )
            )
            for _ in range(steps):
                if discrepancy == Decimal("0"):
                    break
                if discrepancy > 0:
                    # Increase categories with the largest positive residual first
                    cat = max(
                        rounded_percentages.keys(),
                        key=lambda c: (
                            raw_percentages[c] - rounded_percentages[c],
                            raw_percentages[c],
                        ),
                    )
                    rounded_percentages[cat] += quantize_unit
                    discrepancy -= quantize_unit
                else:
                    # Reduce categories that were rounded up the most
                    candidates = sorted(
                        (
                            c
                            for c in rounded_percentages
                            if rounded_percentages[c] > Decimal("0")
                        ),
                        key=lambda c: (
                            raw_percentages[c] - rounded_percentages[c],
                            raw_percentages[c],
                        ),
                    )
                    cat = None
                    for candidate in candidates:
                        if rounded_percentages[candidate] - quantize_unit >= Decimal("0"):
                            cat = candidate
                            break
                    if cat is None:
                        break
                    rounded_percentages[cat] -= quantize_unit
                    discrepancy += quantize_unit

        final_allocations = {k: float(v) for k, v in rounded_percentages.items()}

        sorted_allocation = dict(
            sorted(final_allocations.items(), key=lambda item: item[1], reverse=True)
        )

        total_fixed_income = to_decimal(
            fi_data.get("fixed_inc_principal_and_interest", {}).get("principal", 0)
        )
        if total_assets == 0:
            total_fixed_income_pct = 0.0
        else:
            total_fixed_income_pct = float(
                (total_fixed_income / total_assets * hundred).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
            )

        return {
            "allocation_breakdown": sorted_allocation,
            "total_fixed_income_pct": total_fixed_income_pct,
        }


# Example usage
if __name__ == "__main__":
    from decimal import Decimal

    dict1 = {
        "IB_DATA": {
            "Bonds": {
                "IBCID746579811": 29655,
                "IBCID722427489": 22879,
                "TLT": 3481,
                "SGOV": 1705,
            },
            "China Stocks": {"700": 5378, "9988": 5304, "KWEB": 3950, "PDD": 975},
            "Stocks": {
                "C": 3834,
                "GOOG": 3688,
                "NKE": 3513,
                "BN": 2230,
                "CVS": 2001,
                "COP": 1842,
                "COF": 1802,
                "HUM": 1778,
                "CVX": 1733,
                "INTC": 1459,
                "IBKR": 1112,
                "ADBE": 894,
                "CP": 798,
                "UPS": 756,
            },
            "Short Selling": {},
            "REIT": {},
            "Precious Metals": {"IAU": 544},
            "Commodities": {"COMB": 2572},
            "Total Stocks Value": 43047,
            "Net_cash": 139,
            "IB_Portfolio_Value": 104022,
        },
        "CRYPTO_DATA": {
            "Total_Crypto_Value": 6263,
            "Crypto_Market_Values": {
                "BTC": 3762,
                "ETH": 2056,
                "TON": 102,
                "ADA": 92,
                "BNB": 84,
                "EOS": 72,
                "NEO": 71,
                "SC": 24,
            },
        },
        "FIXED_INCOME_DATA": {
            "group_weighted_interest": {
                "Bonds": (57720, 0.044),
                "Crypto Landing": (25255, 0.108),
                "p2p_lending": (3508, 0.079),
            },
            "fixed_inc_principal_and_interest": {"principal": 86483, "interest": 0.064},
            "total_monthly": 539,
            "total_yearly": 6470,
        },
        "CASH_DATA": {
            "Total": Decimal("1241"),
        },
        "TOTAL_ASSETS": 140289,
    }

    calculator = AllocationCalculator(dict1)
    print(calculator.get_sorted_sector_allocations())
