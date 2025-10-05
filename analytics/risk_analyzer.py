import json
from typing import Dict, List, Tuple
from collections import defaultdict
from decimal import Decimal


class PortfolioRiskAnalyzer:
    """
    Analyzes portfolio risk and assigns risk scores (1-10) to each asset.
    1 = Lowest Risk, 10 = Highest Risk

    Improvements:
    - Handles Decimal types from CASH_DATA
    - Supports OTHER_ASSETS with high risk
    - Considers diversification benefits
    - Volatility estimation for known assets
    - Regulatory and geopolitical risk factors
    """

    # Asset class base risk scores (1-10 scale)
    ASSET_CLASS_RISK = {
        "Bonds": 2.0,
        "REIT": 4.0,
        "Precious Metals": 3.5,
        "Commodities": 5.5,
        "Stocks": 5.0,
        "China Stocks": 6.1,
        "Crypto Coins": 8.5,
        "Crypto Lending": 4.8,
        "P2P Lending": 6.5,
        "Short Selling": 9.0,
        "Other Bets": 5.3,  # Speculative positions but not necessarily catastrophic
        "Cash": 1.0,
    }

    # Volatility estimates (annual standard deviation %)
    # Higher volatility = higher risk
    VOLATILITY_ESTIMATES = {
        # Low volatility
        "VOO": 15,
        "TLT": 12,
        "IAU": 16,
        "BRK B": 18,
        "UNH": 20,
        # Medium volatility
        "GOOG": 25,
        "NKE": 28,
        "CVS": 30,
        "COP": 35,
        "CVX": 32,
        "SLV": 35,
        # High volatility
        "UBER": 45,
        "ASML": 40,
        "IBKR": 38,
        "C": 35,
        "COF": 38,
        # Very high volatility (China stocks)
        "9988": 55,
        "KWEB": 50,
        "PDD": 60,
        # Bonds
        "IHYG": 10,
        "SPHY": 12,
        # Crypto
        "BTC": 70,
        "ETH": 80,
        "BNB": 85,
        "ADA": 90,
        "AVAX": 95,
    }

    # Specific asset adjustments based on known characteristics
    SPECIFIC_ASSET_ADJUSTMENTS = {
        # Low-risk stocks/ETFs
        "VOO": -1.5,  # S&P 500 ETF - diversified
        "BRK B": -1.0,  # Berkshire - quality conglomerate
        "UNH": -0.5,  # Healthcare moat
        # Bonds
        "TLT": -0.5,  # US Treasury backed
        "IHYG": +1.0,  # High-yield = higher default risk
        "SPHY": +1.5,  # High-yield + shorter duration
        # Higher volatility stocks
        "UBER": +1.5,  # Not yet consistently profitable
        "ASML": +1.0,  # Semiconductor cyclicality
        "NKE": +0.5,  # Consumer cyclical
        "C": +0.5,  # Banking sector risk
        "COF": +0.5,  # Credit card exposure
        # Energy - commodity price risk
        "COP": +0.5,
        "CVX": +0.5,
        # Chinese stocks - regulatory & geopolitical risk
        "9988": +0.5,  # Alibaba - regulatory overhang
        "PDD": +1.0,  # Pinduoduo - competitive pressure
        "KWEB": +0.3,  # ETF but China exposure
        # Crypto majors
        "BTC": -1.0,  # Most established crypto
        "ETH": -0.5,  # Second most established
        "BNB": +0.5,  # Centralized exchange token
        "ADA": +1.0,  # Lower adoption
        # Precious metals
        "IAU": -0.5,  # Gold - safe haven
        "SLV": +0.5,  # Silver more volatile
    }

    def __init__(self, portfolio_data: Dict):
        self.portfolio_data = portfolio_data
        self.risk_scores = {}
        self.total_portfolio_value = self._calculate_total_value()

    def _calculate_total_value(self) -> float:
        """Calculate total portfolio value."""
        total = self.portfolio_data.get("TOTAL_ASSETS", 0)
        if total > 0:
            return float(total)

        # Fallback: sum components
        ib_value = self.portfolio_data.get("IB_DATA", {}).get("IB_Portfolio_Value", 0)
        crypto_value = self.portfolio_data.get("CRYPTO_DATA", {}).get(
            "Total_Crypto_Value", 0
        )
        cash = self.portfolio_data.get("CASH_DATA", {}).get("Total", 0)
        if isinstance(cash, Decimal):
            cash = float(cash)
        other = self.portfolio_data.get("OTHER_ASSETS", {}).get("Other Bets", 0)

        return ib_value + crypto_value + cash + other

    def calculate_concentration_risk(self, value: float, total_value: float) -> float:
        """
        Calculate additional risk based on position concentration.
        Higher concentration = higher risk if position goes wrong.
        """
        concentration = (value / total_value) * 100 if total_value > 0 else 0

        if concentration > 20:
            return 2.0
        elif concentration > 15:
            return 1.5
        elif concentration > 10:
            return 1.0
        elif concentration > 5:
            return 0.5
        elif concentration < 0.5:
            return -0.5  # Very small positions, minimal portfolio impact
        elif concentration < 1:
            return -0.3
        return 0.0

    def calculate_volatility_risk(self, asset: str) -> float:
        """
        Calculate risk adjustment based on historical volatility.
        """
        volatility = self.VOLATILITY_ESTIMATES.get(asset)
        if volatility is None:
            return 0.0

        # Convert volatility to risk adjustment
        if volatility > 80:
            return 2.0
        elif volatility > 60:
            return 1.5
        elif volatility > 40:
            return 1.0
        elif volatility > 30:
            return 0.5
        elif volatility < 15:
            return -0.5
        elif volatility < 20:
            return -0.3
        return 0.0

    def calculate_liquidity_risk(
        self, asset: str, asset_class: str, value: float
    ) -> float:
        """
        Estimate liquidity risk based on asset type and size.
        """
        # Crypto tokens with very small holdings likely have low liquidity
        if asset_class in ["Crypto Coins", "Crypto Lending"]:
            if value < 10:  # Dust - extremely illiquid
                return 2.5
            elif value < 50:  # Very small holdings
                return 2.0
            elif value < 200:
                return 1.0
            elif value < 500:
                return 0.5
            elif asset in ["BTC", "ETH"]:
                return -0.5  # Very liquid
            elif asset in ["BNB", "ADA", "AVAX"]:
                return 0.0  # Reasonably liquid

        # P2P lending - illiquid, hard to exit
        if asset_class == "P2P Lending":
            return 2.0

        # Large cap stocks and major ETFs - highly liquid
        if asset in ["VOO", "TLT", "GOOG", "BRK B", "UNH", "IAU"]:
            return -0.5

        # Small positions in stocks may be harder to exit efficiently
        if asset_class == "Stocks" and value < 1000:
            return 0.3

        # Other Bets - typically illiquid
        if asset_class == "Other Bets":
            return 1.5

        return 0.0

    def calculate_diversification_benefit(self, asset: str, asset_class: str) -> float:
        """
        Broad index funds provide diversification, reducing risk.
        Individual stocks or concentrated bets don't.
        """
        # Broad market ETFs
        if asset in ["VOO", "VTI", "SPY"]:
            return -1.0

        # Sector/theme ETFs - some diversification
        if asset in ["KWEB", "TLT", "IAU", "SLV"]:
            return -0.3

        # Individual stocks - no diversification benefit
        if asset_class in ["Stocks", "China Stocks"]:
            return 0.3

        return 0.0

    def analyze_ib_assets(self) -> Dict[str, Tuple[float, float]]:
        """Analyze Interactive Brokers assets."""
        ib_data = self.portfolio_data.get("IB_DATA", {})
        total_value = self.total_portfolio_value
        results = {}

        asset_classes = [
            "Bonds",
            "Stocks",
            "China Stocks",
            "REIT",
            "Precious Metals",
            "Commodities",
            "Short Selling",
        ]

        for asset_class in asset_classes:
            assets = ib_data.get(asset_class, {})
            base_risk = self.ASSET_CLASS_RISK.get(asset_class, 5.0)

            for asset, value in assets.items():
                if isinstance(value, (int, float)) and value > 0:
                    # Base risk
                    risk = base_risk

                    # Specific asset adjustment
                    risk += self.SPECIFIC_ASSET_ADJUSTMENTS.get(asset, 0.0)

                    # Volatility risk
                    risk += self.calculate_volatility_risk(asset)

                    # Concentration risk
                    risk += self.calculate_concentration_risk(value, total_value)

                    # Liquidity risk
                    risk += self.calculate_liquidity_risk(asset, asset_class, value)

                    # Diversification benefit
                    risk += self.calculate_diversification_benefit(asset, asset_class)

                    # Clamp between 1 and 10
                    risk = max(1.0, min(10.0, risk))

                    results[asset] = (risk, value)

        return results

    def analyze_crypto_assets(self) -> Dict[str, Tuple[float, float]]:
        """Analyze cryptocurrency assets."""
        crypto_data = self.portfolio_data.get("CRYPTO_DATA", {})
        market_values = crypto_data.get("Crypto_Market_Values", {})
        total_value = self.total_portfolio_value
        results = {}

        base_risk = self.ASSET_CLASS_RISK.get("Crypto Coins", 8.5)

        for asset, value in market_values.items():
            if isinstance(value, (int, float)) and value > 0:
                # Base risk
                risk = base_risk

                # Specific asset adjustment
                risk += self.SPECIFIC_ASSET_ADJUSTMENTS.get(asset, 0.0)

                # Volatility risk
                risk += self.calculate_volatility_risk(asset)

                # Small cap/microcap tokens are extremely risky
                if value < 5:
                    risk += 2.0  # Dust, near worthless
                elif value < 10:
                    risk += 1.5
                elif value < 50:
                    risk += 1.0
                elif value < 200:
                    risk += 0.5

                # Concentration risk
                risk += self.calculate_concentration_risk(value, total_value)

                # Liquidity risk
                risk += self.calculate_liquidity_risk(asset, "Crypto Coins", value)

                # Clamp between 1 and 10
                risk = max(1.0, min(10.0, risk))

                results[asset] = (risk, value)

        return results

    def analyze_crypto_lending(self) -> Dict[str, Tuple[float, float]]:
        """Analyze crypto lending positions."""
        fixed_income = self.portfolio_data.get("FIXED_INCOME_DATA", {})
        crypto_lending = fixed_income.get("fixed_income_full_data", {}).get(
            "Crypto Landing", {}
        )
        total_value = self.total_portfolio_value
        results = {}

        base_risk = self.ASSET_CLASS_RISK.get("Crypto Lending", 4.8)

        for platform, assets in crypto_lending.items():
            if isinstance(assets, dict):
                for asset, (value, rate) in assets.items():
                    if isinstance(value, (int, float)) and value > 0:
                        key = f"{platform}_{asset}"
                        risk = base_risk

                        # High APY = higher risk (unsustainable rates)
                        if rate > 0.20:
                            risk += 1.0
                        elif rate > 0.15:
                            risk += 0.7
                        elif rate > 0.10:
                            risk += 0.5
                        elif rate > 0.05:
                            risk += 0.3

                        # Platform risk (centralized exchange counterparty risk)
                        # CEX custody risk is meaningful but not catastrophic
                        if platform in ["binance", "okx", "whitebit"]:
                            risk += 0.4

                        # Telegram bots - even higher risk
                        if platform == "telegram":
                            risk += 0.7

                        # Concentration risk (scaled to avoid maxing scores)
                        risk += self.calculate_concentration_risk(
                            value, total_value
                        ) * 0.3

                        risk = max(1.0, min(10.0, risk))
                        results[key] = (risk, value)

        return results

    def analyze_p2p_lending(self) -> Dict[str, Tuple[float, float]]:
        """Analyze P2P lending positions."""
        fixed_income = self.portfolio_data.get("FIXED_INCOME_DATA", {})
        p2p_data = fixed_income.get("fixed_income_full_data", {}).get("p2p_lending", {})
        total_value = self.total_portfolio_value
        results = {}

        base_risk = self.ASSET_CLASS_RISK.get("P2P Lending", 6.5)

        for platform, (value, rate) in p2p_data.items():
            if isinstance(value, (int, float)) and value > 0:
                risk = base_risk

                # Platform-specific adjustments
                if platform == "EstateGuru":
                    risk += 0.5  # Real estate backed, but platform risk
                elif platform == "PeerBerry":
                    risk += 0.3

                # Concentration risk
                risk += self.calculate_concentration_risk(value, total_value)

                risk = max(1.0, min(10.0, risk))
                results[platform] = (risk, value)

        return results

    def analyze_other_assets(self) -> Dict[str, Tuple[float, float]]:
        """Analyze other speculative bets."""
        other_assets = self.portfolio_data.get("OTHER_ASSETS", {})
        total_value = self.total_portfolio_value
        results = {}

        base_risk = self.ASSET_CLASS_RISK.get("Other Bets", 5.3)

        for category, value in other_assets.items():
            if isinstance(value, (int, float)) and value > 0:
                risk = base_risk

                # Other bets are typically speculative, illiquid, or unproven.
                # Apply softer adjustments so large positions don't automatically max out risk.

                # Concentration risk scaled down for catch-all buckets
                risk += self.calculate_concentration_risk(value, total_value) * 0.5

                # Liquidity risk (usually illiquid, scale with size)
                if value < 5000:
                    risk += 0.4
                elif value < 20000:
                    risk += 0.6
                else:
                    risk += 0.8

                # Information asymmetry / opacity grows with ticket size
                risk += 0.3 if value < 10000 else 0.4

                risk = max(1.0, min(10.0, risk))
                results[category] = (risk, value)

        return results

    def analyze_cash(self) -> Dict[str, Tuple[float, float]]:
        """Analyze cash positions."""
        cash_data = self.portfolio_data.get("CASH_DATA", {})
        breakdown = cash_data.get("Breakdown", {})
        results = {}

        base_risk = self.ASSET_CLASS_RISK.get("Cash", 1.0)

        for cash_type, value in breakdown.items():
            if isinstance(value, (Decimal, int, float)):
                value = float(value)
                if value > 0:
                    risk = base_risk

                    # Cash has inflation risk
                    if value > 5000:
                        risk += 0.5  # Opportunity cost of holding too much cash

                    # Lended cash has counterparty risk
                    if cash_type == "lended":
                        risk += 2.0

                    # Private loans - higher risk
                    if cash_type == "private":
                        risk += 3.0

                    risk = max(1.0, min(10.0, risk))
                    results[f"Cash_{cash_type}"] = (risk, value)

        return results

    def analyze_all(self) -> Dict[str, Dict]:
        """Perform complete risk analysis."""
        all_risks = {}

        # Analyze IB assets
        ib_risks = self.analyze_ib_assets()
        for asset, (risk, value) in ib_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": self._get_ib_category(asset),
                "risk_level": self._get_risk_level(risk),
            }

        # Analyze crypto
        crypto_risks = self.analyze_crypto_assets()
        for asset, (risk, value) in crypto_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": "Crypto_Coin",
                "risk_level": self._get_risk_level(risk),
            }

        # Analyze crypto lending
        lending_risks = self.analyze_crypto_lending()
        for asset, (risk, value) in lending_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": "Crypto_Lending",
                "risk_level": self._get_risk_level(risk),
            }

        # Analyze P2P lending
        p2p_risks = self.analyze_p2p_lending()
        for asset, (risk, value) in p2p_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": "P2P_Lending",
                "risk_level": self._get_risk_level(risk),
            }

        # Analyze other assets
        other_risks = self.analyze_other_assets()
        for asset, (risk, value) in other_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": "Other_Bets",
                "risk_level": self._get_risk_level(risk),
            }

        # Analyze cash (optional - usually low risk)
        cash_risks = self.analyze_cash()
        for asset, (risk, value) in cash_risks.items():
            all_risks[asset] = {
                "risk_score": round(risk, 2),
                "value": round(value, 2),
                "category": "Cash",
                "risk_level": self._get_risk_level(risk),
            }

        return all_risks

    def _get_ib_category(self, asset: str) -> str:
        """Determine IB asset category."""
        ib_data = self.portfolio_data.get("IB_DATA", {})
        for category in [
            "Bonds",
            "Stocks",
            "China Stocks",
            "REIT",
            "Precious Metals",
            "Commodities",
            "Short Selling",
        ]:
            if asset in ib_data.get(category, {}):
                return category.replace(" ", "_")
        return "Unknown"

    def _get_risk_level(self, risk_score: float) -> str:
        """Convert risk score to descriptive level."""
        if risk_score <= 3:
            return "Low"
        elif risk_score <= 6:
            return "Medium"
        elif risk_score <= 8:
            return "High"
        else:
            return "Very High"

    def get_summary_statistics(self, risk_scores: Dict) -> Dict:
        """Calculate portfolio-wide risk statistics."""
        if not risk_scores:
            return {}

        scores = [data["risk_score"] for data in risk_scores.values()]
        values = [data["value"] for data in risk_scores.values()]
        total_value = sum(values)

        # Weighted average risk
        weighted_risk = (
            sum(s * v for s, v in zip(scores, values)) / total_value
            if total_value > 0
            else 0
        )

        # Risk distribution by value
        risk_buckets = defaultdict(float)
        for data in risk_scores.values():
            score = data["risk_score"]
            if score <= 3:
                risk_buckets["Low (1-3)"] += data["value"]
            elif score <= 6:
                risk_buckets["Medium (4-6)"] += data["value"]
            elif score <= 8:
                risk_buckets["High (7-8)"] += data["value"]
            else:
                risk_buckets["Very High (9-10)"] += data["value"]

        risk_distribution = {
            k: round((v / total_value) * 100, 2) for k, v in risk_buckets.items()
        }

        # Category breakdown
        category_risk = defaultdict(lambda: {"total_value": 0, "weighted_risk": 0})
        for asset, data in risk_scores.items():
            cat = data["category"]
            category_risk[cat]["total_value"] += data["value"]
            category_risk[cat]["weighted_risk"] += data["risk_score"] * data["value"]

        category_summary = {}
        for cat, values in category_risk.items():
            if values["total_value"] > 0:
                category_summary[cat] = {
                    "value": round(values["total_value"], 2),
                    "avg_risk": round(
                        values["weighted_risk"] / values["total_value"], 2
                    ),
                    "pct_of_portfolio": round(
                        (values["total_value"] / total_value) * 100, 2
                    ),
                }

        return {
            "average_risk": round(sum(scores) / len(scores), 2),
            "weighted_average_risk": round(weighted_risk, 2),
            "min_risk": round(min(scores), 2),
            "max_risk": round(max(scores), 2),
            "risk_distribution_pct": risk_distribution,
            "category_breakdown": category_summary,
            "total_assets_analyzed": len(risk_scores),
            "total_value_analyzed": round(total_value, 2),
        }

    def get_recommendations(self, risk_scores: Dict, summary: Dict) -> List[str]:
        """Generate risk-based recommendations."""
        recommendations = []

        weighted_risk = summary.get("weighted_average_risk", 0)
        risk_dist = summary.get("risk_distribution_pct", {})

        # Overall portfolio risk
        if weighted_risk > 7:
            recommendations.append(
                "⚠️  Portfolio has HIGH overall risk (score: {:.1f}/10). Consider rebalancing towards lower-risk assets.".format(
                    weighted_risk
                )
            )
        elif weighted_risk > 5.5:
            recommendations.append(
                "⚡ Portfolio has MODERATE-HIGH risk (score: {:.1f}/10). Ensure this aligns with your risk tolerance.".format(
                    weighted_risk
                )
            )

        # High risk concentration
        very_high_pct = risk_dist.get("Very High (9-10)", 0)
        high_pct = risk_dist.get("High (7-8)", 0)

        if very_high_pct > 15:
            recommendations.append(
                f"🔴 {very_high_pct:.1f}% of portfolio in VERY HIGH risk assets. Consider reducing exposure."
            )

        if very_high_pct + high_pct > 30:
            recommendations.append(
                f"⚠️  {very_high_pct + high_pct:.1f}% in high/very high risk assets. Diversify into medium/low risk."
            )

        # Top risk assets
        sorted_by_risk = sorted(
            risk_scores.items(),
            key=lambda x: (x[1]["risk_score"], x[1]["value"]),
            reverse=True,
        )
        top_risky = [
            (asset, data)
            for asset, data in sorted_by_risk[:3]
            if data["risk_score"] >= 8
        ]

        if top_risky:
            recommendations.append("🎯 Highest risk positions to monitor:")
            for asset, data in top_risky:
                recommendations.append(
                    f"   • {asset}: {data['risk_score']}/10 (${data['value']:,.0f})"
                )

        # Concentration warnings
        for asset, data in risk_scores.items():
            pct = (data["value"] / summary["total_value_analyzed"]) * 100
            if pct > 15 and data["risk_score"] > 6:
                recommendations.append(
                    f"⚠️  {asset} represents {pct:.1f}% of portfolio with risk score {data['risk_score']}/10"
                )

        # Positive notes
        low_risk_pct = risk_dist.get("Low (1-3)", 0)
        if low_risk_pct > 30:
            recommendations.append(
                f"✅ Good foundation: {low_risk_pct:.1f}% in low-risk assets provides stability."
            )

        if not recommendations:
            recommendations.append(
                "✅ Portfolio risk profile appears balanced for your allocation strategy."
            )

        return recommendations

    def print_report(self, show_all_assets: bool = False):
        """Print formatted risk analysis report."""
        risk_scores = self.analyze_all()

        print("=" * 90)
        print("PORTFOLIO RISK ANALYSIS REPORT")
        print("=" * 90)
        print(f"Total Portfolio Value: ${self.total_portfolio_value:,.0f}")
        print()

        # Sort by risk score (highest first), then by value
        sorted_assets = sorted(
            risk_scores.items(),
            key=lambda x: (x[1]["risk_score"], x[1]["value"]),
            reverse=True,
        )

        # Show top risky assets or all
        display_assets = sorted_assets if show_all_assets else sorted_assets[:30]

        print(f"{'Asset':<25} {'Risk':<6} {'Value':<14} {'% Port':<8} {'Category':<18}")
        print("-" * 90)

        for asset, data in display_assets:
            risk_indicator = (
                "🔴"
                if data["risk_score"] >= 8
                else "🟡" if data["risk_score"] >= 6 else "🟢"
            )
            pct = (data["value"] / self.total_portfolio_value) * 100
            print(
                f"{asset:<25} {risk_indicator} {data['risk_score']:<4.1f} ${data['value']:<12,.0f} {pct:<7.2f}% {data['category']:<18}"
            )

        if not show_all_assets and len(sorted_assets) > 30:
            print(
                f"\n... and {len(sorted_assets) - 30} more assets (set show_all_assets=True to see all)"
            )

        print()
        print("=" * 90)
        print("SUMMARY STATISTICS")
        print("=" * 90)

        stats = self.get_summary_statistics(risk_scores)
        print(f"Average Risk Score: {stats['average_risk']}/10")
        print(f"Weighted Average Risk: {stats['weighted_average_risk']}/10")
        print(f"Risk Range: {stats['min_risk']} - {stats['max_risk']}")
        print(f"Total Assets Analyzed: {stats['total_assets_analyzed']}")
        print()

        print("Risk Distribution by Value:")
        for risk_level, pct in sorted(
            stats["risk_distribution_pct"].items(), key=lambda x: x[1], reverse=True
        ):
            bar_length = int(pct / 2)  # Scale for display
            bar = "█" * bar_length
            print(f"  {risk_level:<20} {pct:>6.2f}% {bar}")

        print()
        print("Category Breakdown:")
        print(f"{'Category':<20} {'Value':<14} {'Avg Risk':<10} {'% Portfolio':<12}")
        print("-" * 60)
        for cat, data in sorted(
            stats["category_breakdown"].items(),
            key=lambda x: x[1]["value"],
            reverse=True,
        ):
            print(
                f"{cat:<20} ${data['value']:<12,.0f} {data['avg_risk']:<10.1f} {data['pct_of_portfolio']:<12.2f}%"
            )

        print()
        print("=" * 90)
        print("RECOMMENDATIONS")
        print("=" * 90)
        recommendations = self.get_recommendations(risk_scores, stats)
        for rec in recommendations:
            print(rec)

        print("=" * 90)

        return risk_scores, stats


# Example usage
if __name__ == "__main__":
    # Your updated portfolio data
    portfolio_data = {
        "IB_DATA": {
            "Bonds": {"IBCID791308604": 30972, "TLT": 7597, "IHYG": 3802, "SPHY": 1906},
            "China Stocks": {"9988": 11909, "KWEB": 4816, "PDD": 1209},
            "Stocks": {
                "NKE": 4823,
                "GOOG": 4676,
                "BRK B": 4000,
                "UNH": 3968,
                "BN": 3780,
                "VOO": 2462,
                "C": 2442,
                "COP": 2354,
                "CVS": 2326,
                "HUM": 2270,
                "COF": 2144,
                "CVX": 1844,
                "CP": 1785,
                "IBKR": 1227,
                "ASML": 1028,
                "UBER": 290,
            },
            "Short Selling": {},
            "REIT": {},
            "Precious Metals": {"IAU": 5858, "SLV": 3092},
            "Commodities": {"COMB": 3172},
            "Total Stocks Value": 59353,
            "Net_cash": 156,
            "IB_Portfolio_Value": 115908,
        },
        "CRYPTO_DATA": {
            "Total_Crypto_Value": 8071,
            "Crypto_Market_Values": {
                "BTC": 4924,
                "ETH": 2829,
                "BNB": 138,
                "ADA": 91,
                "EOS": 37,
                "NEO": 32,
                "SC": 12,
                "AVAX": 7,
                "PENGU": 1,
            },
        },
        "FIXED_INCOME_DATA": {
            "fixed_income_full_data": {
                "Crypto Landing": {
                    "binance": {"USDT": (204, 0.165)},
                    "okx": {"AVAX": (1, 0.083)},
                    "whitebit": {
                        "USDC": (11601, 0.174),
                        "USDT": (2244, 0.186),
                        "ETH": (0.1125, 0.174),
                    },
                    "telegram": {"USDT": (3295, 0.13)},
                },
                "p2p_lending": {"EstateGuru": (1985, 0.09), "PeerBerry": (0, 0.0)},
            }
        },
        "CASH_DATA": {
            "Total": Decimal("1179"),
            "Breakdown": {
                "cash": Decimal("983"),
                "lended": Decimal("933"),
                "debt": Decimal("0"),
                "private": Decimal("-1700"),
                "ib_cash": Decimal("156"),
                "crypto_cash": Decimal("0"),
                "mono": Decimal("807"),
                "wise": Decimal("0"),
            },
        },
        "OTHER_ASSETS": {"Other Bets": 20983},
        "TOTAL_ASSETS": 165471,
    }

    # Create analyzer and run analysis
    analyzer = PortfolioRiskAnalyzer(portfolio_data)
    risk_scores, summary = analyzer.print_report(show_all_assets=False)
