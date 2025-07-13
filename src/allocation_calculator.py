class AllocationCalculator:
    def __init__(self, data):
        self.data = data

    def get_sorted_sector_allocations(self) -> dict:
        return self._calculate_allocations(self.data)

    @staticmethod
    def _calculate_allocations(data: dict) -> dict:
        from decimal import Decimal, ROUND_HALF_UP, getcontext

        # Set precision
        getcontext().prec = 6

        total_assets = Decimal(data.get("TOTAL_ASSETS", 0))

        # Extract sector values
        bonds_value = Decimal(sum(data.get("IB_DATA", {}).get("Bonds", {}).values()))
        stocks_value = Decimal(data.get("IB_DATA", {}).get("Total Stocks Value", 0))
        commodities_value = Decimal(
            sum(data.get("IB_DATA", {}).get("Commodities", {}).values())
        )
        precious_metals_value = Decimal(
            sum(data.get("IB_DATA", {}).get("Precious Metals", {}).values())
        )
        crypto_spot_value = Decimal(
            data.get("CRYPTO_DATA", {}).get("Total_Crypto_Value", 0)
        )
        crypto_lending_value = Decimal(
            data.get("FIXED_INCOME_DATA", {})
            .get("group_weighted_interest", {})
            .get("Crypto Landing", (0,))[0]
        )
        p2p_lending_value = Decimal(
            data.get("FIXED_INCOME_DATA", {})
            .get("group_weighted_interest", {})
            .get("p2p_lending", (0,))[0]
        )
        reit_value = Decimal(sum(data.get("IB_DATA", {}).get("REIT", {}).values()))
        cash_value = Decimal(float(data.get("CASH_DATA", {}).get("Total", 0)))

        # Compute percentages with higher precision
        allocation_breakdown = {
            "Bonds": (bonds_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Stocks": (stocks_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Commodities": (commodities_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Precious Metals": (precious_metals_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Crypto Coins": (crypto_spot_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Crypto Lending": (crypto_lending_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "P2P Lending": (p2p_lending_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "REIT": (reit_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
            "Cash": (cash_value / total_assets * 100).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            ),
        }

        # Sum all percentages
        total_percentage = sum(allocation_breakdown.values())

        # Calculate discrepancy
        discrepancy = Decimal("100.00") - total_percentage

        # Assign discrepancy to the largest sector
        if discrepancy != Decimal("0.00"):
            largest_sector = max(allocation_breakdown, key=allocation_breakdown.get)
            allocation_breakdown[largest_sector] += discrepancy

        # Convert to float for final output
        final_allocations = {k: float(v) for k, v in allocation_breakdown.items()}

        # Sort the allocations
        sorted_allocation = dict(
            sorted(final_allocations.items(), key=lambda item: item[1], reverse=True)
        )

        # Calculate total fixed income percentage
        total_fixed_income = Decimal(
            data.get("FIXED_INCOME_DATA", {})
            .get("fixed_inc_principal_and_interest", {})
            .get("principal", 0)
        )
        total_fixed_income_pct = float(
            (total_fixed_income / total_assets * 100).quantize(
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
