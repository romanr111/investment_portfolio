import argparse
import json
import math
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Mapping, Optional

import numpy as np
import pandas as pd

LAYER_B_FACTOR_COLUMNS: tuple[str, ...] = (
    "growth",
    "inflation",
    "real_rates",
    "credit_liquidity",
)

HOLY_GRAIL_COMPONENT_WEIGHTS: Dict[str, float] = {
    "independence": 35.0,
    "balance": 35.0,
    "robustness": 20.0,
    "macro": 10.0,
}


def portfolio_variance_contributions(weights: np.ndarray, covariance: np.ndarray):
    """Return portfolio variance and Euler contributions in variance units."""
    contributions = weights * (covariance @ weights)
    return float(contributions.sum()), contributions


DEFAULT_FACTOR_MAP: Dict[str, str] = {
    "Stocks": "Growth/Risk-On",
    "Other Bets": "Growth/Risk-On",
    "Crypto Coins": "Growth/Risk-On",
    "Crypto Lending": "Growth/Risk-On",
    "P2P Lending": "Growth/Risk-On",
    "Bonds": "Deflation/Risk-Off",
    "Cash": "Deflation/Risk-Off",
    "Precious Metals": "Inflation Hedge",
    "Commodities": "Inflation Hedge",
}

DEFAULT_SCENARIO_SHOCKS: Dict[str, Dict[str, float]] = {
    "rate_hike": {
        "Bonds": -0.12,
        "Stocks": -0.08,
        "Other Bets": -0.10,
        "Crypto Lending": -0.06,
        "Precious Metals": -0.02,
        "Crypto Coins": -0.15,
        "Commodities": 0.03,
        "Cash": 0.00,
        "P2P Lending": -0.05,
    },
    "inflation_shock": {
        "Bonds": -0.10,
        "Stocks": -0.07,
        "Other Bets": -0.09,
        "Crypto Lending": -0.04,
        "Precious Metals": 0.12,
        "Crypto Coins": -0.12,
        "Commodities": 0.10,
        "Cash": -0.02,
        "P2P Lending": -0.06,
    },
    "credit_spread_recession": {
        "Bonds": 0.04,
        "Stocks": -0.18,
        "Other Bets": -0.22,
        "Crypto Lending": -0.20,
        "Precious Metals": 0.03,
        "Crypto Coins": -0.30,
        "Commodities": -0.10,
        "Cash": 0.00,
        "P2P Lending": -0.18,
    },
    "crypto_drawdown": {
        "Bonds": 0.01,
        "Stocks": -0.03,
        "Other Bets": -0.05,
        "Crypto Lending": -0.35,
        "Precious Metals": 0.02,
        "Crypto Coins": -0.55,
        "Commodities": -0.02,
        "Cash": 0.00,
        "P2P Lending": -0.04,
    },
}


@dataclass
class DalioAnalysisResult:
    normalized_data: pd.DataFrame
    weights_by_date: pd.DataFrame
    correlation_matrix: pd.DataFrame
    rolling_correlation: pd.DataFrame
    factor_returns_aligned: pd.DataFrame
    factor_betas_by_bucket_rolling: pd.DataFrame
    factor_model_quality_rolling: pd.DataFrame
    factor_risk_contribution_rolling: pd.DataFrame
    factor_residual_risk_rolling: pd.DataFrame
    layer_a_metrics_rolling: pd.DataFrame
    layer_a_trc_rolling: pd.DataFrame
    layer_a_cluster_membership_rolling: pd.DataFrame
    asset_coverage: pd.DataFrame
    covariance_matrix: pd.DataFrame
    risk_contribution_by_bucket: pd.DataFrame
    factor_exposure: pd.DataFrame
    stress_test_results: pd.DataFrame
    quality_checks: pd.DataFrame
    high_correlation_pairs: pd.DataFrame
    pairwise_confidence: pd.DataFrame
    tail_risk_metrics: pd.DataFrame
    weight_drift: pd.DataFrame
    holy_grail_scorecard: pd.DataFrame
    holy_grail_robustness: pd.DataFrame
    holy_grail_red_flags: pd.DataFrame
    diversification_metrics: Dict[str, float]
    management_rules: Dict[str, object]
    holy_grail_verdict: Dict[str, object]

    def to_tables(self) -> Dict[str, pd.DataFrame]:
        return {
            "normalized_data": self.normalized_data,
            "weights_by_date": self.weights_by_date,
            "correlation_matrix": self.correlation_matrix,
            "rolling_correlation": self.rolling_correlation,
            "factor_returns_aligned": self.factor_returns_aligned,
            "factor_betas_by_bucket_rolling": self.factor_betas_by_bucket_rolling,
            "factor_model_quality_rolling": self.factor_model_quality_rolling,
            "factor_risk_contribution_rolling": self.factor_risk_contribution_rolling,
            "factor_residual_risk_rolling": self.factor_residual_risk_rolling,
            "layer_a_metrics_rolling": self.layer_a_metrics_rolling,
            "layer_a_trc_rolling": self.layer_a_trc_rolling,
            "layer_a_cluster_membership_rolling": self.layer_a_cluster_membership_rolling,
            "asset_coverage": self.asset_coverage,
            "covariance_matrix": self.covariance_matrix,
            "risk_contribution_by_bucket": self.risk_contribution_by_bucket,
            "factor_exposure": self.factor_exposure,
            "stress_test_results": self.stress_test_results,
            "quality_checks": self.quality_checks,
            "high_correlation_pairs": self.high_correlation_pairs,
            "pairwise_confidence": self.pairwise_confidence,
            "tail_risk_metrics": self.tail_risk_metrics,
            "weight_drift": self.weight_drift,
            "holy_grail_scorecard": self.holy_grail_scorecard,
            "holy_grail_robustness": self.holy_grail_robustness,
            "holy_grail_red_flags": self.holy_grail_red_flags,
        }


class DalioHolyGrailAnalyzer:
    REQUIRED_COLUMNS = {"date", "asset_bucket", "market_value"}

    def __init__(
        self,
        history: pd.DataFrame,
        base_currency: str = "USD",
        fx_rates: Optional[Mapping[str, float]] = None,
        fx_history: Optional[pd.DataFrame] = None,
        factor_returns: Optional[pd.DataFrame] = None,
        factor_map: Optional[Mapping[str, str]] = None,
        scenario_shocks: Optional[Mapping[str, Mapping[str, float]]] = None,
        min_history_months: int = 36,
        return_unit: str = "decimal",
        min_covariance_observations: int = 12,
        allow_partial_scenarios: bool = False,
        allow_unmapped_factors: bool = False,
        allow_shorts: bool = False,
        max_gross_leverage: float = 1.05,
        min_net_to_gross: float = 0.60,
        covariance_method: str = "ledoit-wolf",
        ewma_alpha: float = 0.06,
        min_pair_overlap: int = 24,
        layer_b_window_months: int = 36,
        layer_b_min_observations: int = 24,
        layer_b_require_data: bool = False,
        layer_b_collinearity_cond_threshold: float = 30.0,
        layer_b_vif_threshold: float = 10.0,
        layer_b_max_factor_trc_share: float = 0.35,
        layer_b_factor_hhi_threshold: float = 0.35,
        layer_b_residual_share_threshold: float = 0.40,
        layer_b_min_coverage_pct: float = 80.0,
        layer_a_windows: tuple[int, ...] = (12, 24, 36),
        layer_a_high_corr_threshold: float = 0.70,
        layer_a_cluster_corr_cutoff: float = 0.70,
        layer_a_trc_max_share_threshold: float = 0.35,
        layer_a_min_n_rc: float = 4.0,
        layer_a_primary_window: int = 36,
        analysis_frequency: str = "auto",
        return_type: str = "simple",
        min_asset_coverage_pct: float = 80.0,
        covariance_window: Optional[int] = None,
    ):
        self.history = history.copy()
        self.base_currency = base_currency.upper()
        self.fx_rates = {self.base_currency: 1.0}
        if fx_rates:
            self.fx_rates.update({k.upper(): float(v) for k, v in fx_rates.items()})
        self.fx_history = fx_history.copy() if fx_history is not None else None
        self.factor_returns = (
            factor_returns.copy() if factor_returns is not None else None
        )
        self.factor_map = dict(DEFAULT_FACTOR_MAP)
        if factor_map:
            self.factor_map.update(factor_map)
        self.scenario_shocks = {
            scenario: dict(shocks)
            for scenario, shocks in (scenario_shocks or DEFAULT_SCENARIO_SHOCKS).items()
        }
        self.min_history_months = min_history_months
        self.return_unit = return_unit
        self.min_covariance_observations = min_covariance_observations
        self.allow_partial_scenarios = allow_partial_scenarios
        self.allow_unmapped_factors = allow_unmapped_factors
        self.allow_shorts = allow_shorts
        self.max_gross_leverage = max_gross_leverage
        self.min_net_to_gross = min_net_to_gross
        self.covariance_method = covariance_method.lower()
        self.ewma_alpha = ewma_alpha
        self.min_pair_overlap = min_pair_overlap
        self.analysis_frequency = analysis_frequency.lower()
        self.return_type = return_type.lower()
        self.min_asset_coverage_pct = float(min_asset_coverage_pct)
        self.covariance_window = (
            int(covariance_window) if covariance_window is not None else None
        )
        self.layer_b_window_months = int(layer_b_window_months)
        self.layer_b_min_observations = int(layer_b_min_observations)
        self.layer_b_require_data = bool(layer_b_require_data)
        self.layer_b_collinearity_cond_threshold = float(
            layer_b_collinearity_cond_threshold
        )
        self.layer_b_vif_threshold = float(layer_b_vif_threshold)
        self.layer_b_max_factor_trc_share = float(layer_b_max_factor_trc_share)
        self.layer_b_factor_hhi_threshold = float(layer_b_factor_hhi_threshold)
        self.layer_b_residual_share_threshold = float(layer_b_residual_share_threshold)
        self.layer_b_min_coverage_pct = float(layer_b_min_coverage_pct)
        if self.layer_b_window_months <= 0:
            raise ValueError("layer_b_window_months must be > 0.")
        if self.layer_b_min_observations <= 1:
            raise ValueError("layer_b_min_observations must be > 1.")
        if self.layer_b_collinearity_cond_threshold <= 0:
            raise ValueError("layer_b_collinearity_cond_threshold must be > 0.")
        if self.layer_b_vif_threshold <= 0:
            raise ValueError("layer_b_vif_threshold must be > 0.")
        if not 0.0 <= self.layer_b_max_factor_trc_share <= 1.0:
            raise ValueError("layer_b_max_factor_trc_share must be in [0, 1].")
        if not 0.0 <= self.layer_b_factor_hhi_threshold <= 1.0:
            raise ValueError("layer_b_factor_hhi_threshold must be in [0, 1].")
        if not 0.0 <= self.layer_b_residual_share_threshold <= 1.0:
            raise ValueError("layer_b_residual_share_threshold must be in [0, 1].")
        if not 0.0 <= self.layer_b_min_coverage_pct <= 100.0:
            raise ValueError("layer_b_min_coverage_pct must be in [0, 100].")
        self.layer_a_windows = self._normalize_layer_a_windows(layer_a_windows)
        self.layer_a_high_corr_threshold = float(layer_a_high_corr_threshold)
        self.layer_a_cluster_corr_cutoff = float(layer_a_cluster_corr_cutoff)
        self.layer_a_trc_max_share_threshold = float(layer_a_trc_max_share_threshold)
        self.layer_a_min_n_rc = float(layer_a_min_n_rc)
        self.layer_a_primary_window = int(layer_a_primary_window)
        if self.layer_a_primary_window not in self.layer_a_windows:
            raise ValueError(
                "layer_a_primary_window must be one of layer_a_windows: {}".format(
                    ", ".join(str(value) for value in self.layer_a_windows)
                )
            )
        if not 0.0 < self.layer_a_high_corr_threshold <= 1.0:
            raise ValueError("layer_a_high_corr_threshold must be in (0, 1].")
        if not 0.0 < self.layer_a_cluster_corr_cutoff <= 1.0:
            raise ValueError("layer_a_cluster_corr_cutoff must be in (0, 1].")
        if not 0.0 <= self.layer_a_trc_max_share_threshold <= 1.0:
            raise ValueError("layer_a_trc_max_share_threshold must be in [0, 1].")
        if self.layer_a_min_n_rc <= 0:
            raise ValueError("layer_a_min_n_rc must be > 0.")
        if self.analysis_frequency not in {"auto", "daily", "monthly"}:
            raise ValueError(
                "analysis_frequency must be one of: auto, daily, monthly."
            )
        if self.return_type not in {"simple", "log"}:
            raise ValueError("return_type must be one of: simple, log.")
        if not 0.0 <= self.min_asset_coverage_pct <= 100.0:
            raise ValueError("min_asset_coverage_pct must be in [0, 100].")
        if self.covariance_window is not None and self.covariance_window <= 0:
            raise ValueError("covariance_window must be > 0 when provided.")
        if self.covariance_method not in {"ledoit-wolf", "sample", "ewma"}:
            raise ValueError(
                "covariance_method must be one of: ledoit-wolf, sample, ewma."
            )
        self.raw_duplicate_pairs_count = 0

    def run_analysis(
        self,
        corr_threshold: float = 0.6,
        max_risk_contribution: float = 0.25,
        target_weights: Optional[Mapping[str, float]] = None,
        drift_threshold: float = 0.20,
    ) -> DalioAnalysisResult:
        normalized = self._normalize_history()
        self._validate_factor_mapping(normalized)
        weights_by_date = self._calculate_weights_by_date(normalized)
        returns_wide = self._build_returns_matrix(normalized)
        analysis_frequency_effective = self._resolve_analysis_frequency(
            returns_wide.index, self.analysis_frequency
        )
        asset_coverage = self._build_asset_coverage_table(returns_wide)
        included_assets = asset_coverage.loc[
            asset_coverage["included_for_covariance"], "asset_bucket"
        ].tolist()
        returns_for_covariance = returns_wide.reindex(columns=included_assets)
        covariance_window_effective = self._resolve_covariance_window(
            total_rows=len(returns_for_covariance.index),
            analysis_frequency=analysis_frequency_effective,
        )
        covariance_input = self._apply_covariance_window(
            returns_for_covariance, covariance_window_effective
        )
        correlation_matrix = returns_wide.corr(
            min_periods=self.min_covariance_observations
        )
        covariance_matrix = self._compute_covariance_matrix(covariance_input).reindex(
            index=returns_wide.columns,
            columns=returns_wide.columns,
        )
        rolling_correlation = self._rolling_pairwise_correlation(returns_wide, (12, 36))
        layer_ab_returns, layer_ab_weights = self._returns_weights_for_layer_ab(
            returns_wide, weights_by_date, analysis_frequency_effective
        )
        layer_b_outputs = self._layer_b_analysis(layer_ab_returns, layer_ab_weights)
        (
            layer_a_metrics_rolling,
            layer_a_trc_rolling,
            layer_a_cluster_membership_rolling,
        ) = self._layer_a_rollup(layer_ab_returns, layer_ab_weights)
        pairwise_confidence = self._pairwise_confidence_flags(returns_wide)
        quality_checks = self._run_quality_checks(normalized, weights_by_date)
        latest_weights = self._latest_weights(weights_by_date)
        diversification_metrics = self._diversification_metrics(latest_weights)
        risk_contribution = self._risk_contribution_by_bucket(
            latest_weights, covariance_matrix
        )
        factor_exposure = self._factor_exposure(latest_weights, risk_contribution)
        tail_risk_metrics = self._tail_risk_metrics(
            returns_wide,
            weights_by_date,
            analysis_frequency_effective,
        )
        stress_test_results = self._stress_tests(latest_weights, weights_by_date)
        high_corr_pairs = self._high_correlation_pairs(correlation_matrix, corr_threshold)
        weight_drift = self._weight_drift(latest_weights, target_weights, drift_threshold)
        excluded_assets = asset_coverage.loc[
            ~asset_coverage["included_for_covariance"], "asset_bucket"
        ].tolist()
        layer_ab_input_frequency = (
            "monthly"
            if analysis_frequency_effective == "daily"
            else analysis_frequency_effective
        )
        management_rules = self._management_rules_summary(
            normalized=normalized,
            weights_by_date=weights_by_date,
            high_corr_pairs=high_corr_pairs,
            risk_contribution=risk_contribution,
            max_risk_contribution=max_risk_contribution,
            weight_drift=weight_drift,
            corr_threshold=corr_threshold,
            drift_threshold=drift_threshold,
            pairwise_confidence=pairwise_confidence,
            layer_b_summary=layer_b_outputs["summary"],
            layer_a_metrics_rolling=layer_a_metrics_rolling,
            analysis_frequency=analysis_frequency_effective,
            covariance_method_effective=self.covariance_method,
            covariance_window_effective=covariance_window_effective,
            assets_excluded_low_coverage=excluded_assets,
            layer_ab_input_frequency=layer_ab_input_frequency,
        )
        (
            holy_grail_verdict,
            holy_grail_scorecard,
            holy_grail_robustness,
            holy_grail_red_flags,
        ) = self._holy_grail_verdict(
            layer_a_metrics_rolling=layer_a_metrics_rolling,
            layer_a_trc_rolling=layer_a_trc_rolling,
            factor_risk_contribution_rolling=layer_b_outputs[
                "factor_risk_contribution_rolling"
            ],
            factor_residual_risk_rolling=layer_b_outputs[
                "factor_residual_risk_rolling"
            ],
            layer_b_enabled=bool(layer_b_outputs["summary"].get("layer_b_enabled", False)),
        )

        risk_breach_mask = risk_contribution["risk_contribution_pct"] > max_risk_contribution
        risk_contribution["risk_limit_breach"] = risk_breach_mask.fillna(False)

        return DalioAnalysisResult(
            normalized_data=normalized,
            weights_by_date=weights_by_date,
            correlation_matrix=correlation_matrix,
            rolling_correlation=rolling_correlation,
            factor_returns_aligned=layer_b_outputs["factor_returns_aligned"],
            factor_betas_by_bucket_rolling=layer_b_outputs[
                "factor_betas_by_bucket_rolling"
            ],
            factor_model_quality_rolling=layer_b_outputs["factor_model_quality_rolling"],
            factor_risk_contribution_rolling=layer_b_outputs[
                "factor_risk_contribution_rolling"
            ],
            factor_residual_risk_rolling=layer_b_outputs[
                "factor_residual_risk_rolling"
            ],
            layer_a_metrics_rolling=layer_a_metrics_rolling,
            layer_a_trc_rolling=layer_a_trc_rolling,
            layer_a_cluster_membership_rolling=layer_a_cluster_membership_rolling,
            asset_coverage=asset_coverage,
            covariance_matrix=covariance_matrix,
            risk_contribution_by_bucket=risk_contribution,
            factor_exposure=factor_exposure,
            stress_test_results=stress_test_results,
            quality_checks=quality_checks,
            high_correlation_pairs=high_corr_pairs,
            pairwise_confidence=pairwise_confidence,
            tail_risk_metrics=tail_risk_metrics,
            weight_drift=weight_drift,
            holy_grail_scorecard=holy_grail_scorecard,
            holy_grail_robustness=holy_grail_robustness,
            holy_grail_red_flags=holy_grail_red_flags,
            diversification_metrics=diversification_metrics,
            management_rules=management_rules,
            holy_grail_verdict=holy_grail_verdict,
        )

    def save_result_tables(self, result: DalioAnalysisResult, output_dir: str) -> None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        for table_name, table in result.to_tables().items():
            table.to_csv(out_path / f"{table_name}.csv", index=True)

        summary = {
            "diversification_metrics": result.diversification_metrics,
            "management_rules": result.management_rules,
            "holy_grail_verdict": result.holy_grail_verdict,
        }
        with open(out_path / "summary.json", "w", encoding="utf-8") as summary_file:
            json.dump(summary, summary_file, indent=2, ensure_ascii=True, default=str)

    def _normalize_history(self) -> pd.DataFrame:
        self._validate_columns(self.history)
        normalized = self.history.copy()
        normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce")
        if normalized["date"].isna().any():
            raise ValueError("Column 'date' has unparsable values.")

        normalized["market_value"] = pd.to_numeric(
            normalized["market_value"], errors="coerce"
        )
        if normalized["market_value"].isna().any():
            raise ValueError("Column 'market_value' has non-numeric values.")

        normalized["currency"] = normalized.get("currency", self.base_currency)
        normalized["currency"] = normalized["currency"].fillna(self.base_currency).str.upper()
        self.raw_duplicate_pairs_count = int(
            normalized.duplicated(subset=["date", "asset_bucket"]).sum()
        )
        normalized["fx_rate_to_base"] = self._resolve_fx_rate_series(normalized)
        normalized["market_value_base"] = (
            normalized["market_value"] * normalized["fx_rate_to_base"]
        )

        if "return_pct" in normalized.columns:
            raw_return = pd.to_numeric(normalized["return_pct"], errors="coerce")
        else:
            raw_return = pd.Series([pd.NA] * len(normalized), index=normalized.index)
        normalized["return_pct"] = self._normalize_return_units(raw_return)

        normalized = normalized.sort_values(
            ["asset_bucket", "date", "currency"]
        ).reset_index(drop=True)

        aggregated = self._aggregate_bucket_history(normalized)
        computed_returns = aggregated.groupby("asset_bucket")["market_value_base"].pct_change()
        simple_returns = aggregated["provided_return_pct"].combine_first(
            computed_returns
        )
        aggregated["return_pct"] = self._apply_return_type(simple_returns)
        aggregated["factor"] = aggregated["asset_bucket"].map(self.factor_map).fillna(
            "Unmapped"
        )
        aggregated["month"] = aggregated["date"].dt.to_period("M")
        return aggregated

    def _validate_columns(self, data: pd.DataFrame) -> None:
        missing_columns = self.REQUIRED_COLUMNS.difference(data.columns)
        if missing_columns:
            raise ValueError(
                "Missing required columns: {}".format(", ".join(sorted(missing_columns)))
            )

    def _resolve_fx_rate_series(self, normalized: pd.DataFrame) -> pd.Series:
        if self.fx_history is None:
            unknown_currencies = sorted(
                currency
                for currency in normalized["currency"].unique()
                if currency not in self.fx_rates
            )
            if unknown_currencies:
                raise ValueError(
                    "Missing FX rates for currencies: {}".format(
                        ", ".join(unknown_currencies)
                    )
                )
            return normalized["currency"].map(self.fx_rates).astype(float)

        fx_history = self.fx_history.copy()
        required_fx_columns = {"date", "currency", "fx_rate_to_base"}
        missing_fx_columns = required_fx_columns.difference(fx_history.columns)
        if missing_fx_columns:
            raise ValueError(
                "fx_history is missing required columns: {}".format(
                    ", ".join(sorted(missing_fx_columns))
                )
            )

        fx_history["date"] = pd.to_datetime(fx_history["date"], errors="coerce")
        fx_history["currency"] = fx_history["currency"].str.upper()
        fx_history["fx_rate_to_base"] = pd.to_numeric(
            fx_history["fx_rate_to_base"], errors="coerce"
        )
        if fx_history["date"].isna().any() or fx_history["fx_rate_to_base"].isna().any():
            raise ValueError("fx_history has invalid date or fx_rate_to_base values.")

        merged = normalized.merge(
            fx_history[["date", "currency", "fx_rate_to_base"]],
            on=["date", "currency"],
            how="left",
        )
        if self.fx_rates:
            merged["fx_rate_to_base"] = merged["fx_rate_to_base"].where(
                merged["fx_rate_to_base"].notna(),
                merged["currency"].map(self.fx_rates),
            )

        missing_mask = merged["fx_rate_to_base"].isna()
        if missing_mask.any():
            missing_rows = (
                merged.loc[missing_mask, ["date", "currency"]]
                .drop_duplicates()
                .sort_values(["date", "currency"])
            )
            preview = ", ".join(
                f"{row.currency}@{row.date.date()}" for row in missing_rows.itertuples()
            )
            raise ValueError(
                f"Missing dated FX rates for: {preview}. "
                "Provide fx_history with date/currency/fx_rate_to_base coverage."
            )

        return merged["fx_rate_to_base"].astype(float)

    def _normalize_return_units(self, raw_return: pd.Series) -> pd.Series:
        numeric_return = pd.to_numeric(raw_return, errors="coerce")
        if numeric_return.dropna().empty:
            return numeric_return

        unit = self.return_unit.lower()
        if unit not in {"decimal", "percent"}:
            raise ValueError(
                "return_unit must be one of: decimal, percent."
            )

        if unit == "decimal":
            if (numeric_return.dropna().abs() > 1.0).any():
                raise ValueError(
                    "return_pct appears to contain percent values (>1.0) while "
                    "return_unit='decimal'. Use return_unit='percent'."
                )
            return numeric_return
        if unit == "percent":
            if (numeric_return.dropna().abs() > 100.0).any():
                raise ValueError(
                    "return_pct has values >100 while return_unit='percent'. "
                    "Check data quality."
                )
            return numeric_return / 100.0
        return numeric_return

    def _apply_return_type(self, simple_returns: pd.Series) -> pd.Series:
        numeric_returns = pd.to_numeric(simple_returns, errors="coerce")
        if self.return_type == "simple":
            return numeric_returns
        bad_values = numeric_returns.dropna() <= -1.0
        if bad_values.any():
            raise ValueError(
                "return_type='log' requires simple returns > -1. "
                "Found return_pct <= -1.0."
            )
        log_values = np.log1p(numeric_returns.astype(float))
        return pd.Series(log_values, index=simple_returns.index)

    def _empty_factor_returns_aligned_table(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["date", *LAYER_B_FACTOR_COLUMNS]).set_index("date")

    def _empty_factor_betas_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "date",
                "window_months",
                "asset_bucket",
                "alpha",
                "beta_growth",
                "beta_inflation",
                "beta_real_rates",
                "beta_credit_liquidity",
                "r2",
                "adj_r2",
            ]
        )

    def _empty_factor_quality_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "date",
                "window_months",
                "asset_bucket",
                "condition_number",
                "max_vif",
                "quality_flag",
                "observations",
            ]
        )

    def _empty_factor_risk_contribution_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "date",
                "window_months",
                "factor",
                "trc",
                "trc_share_signed",
                "trc_share_abs",
                "max_share_pct",
                "factor_hhi",
                "factor_n_rc",
                "factor_gini",
            ]
        )

    def _empty_factor_residual_risk_table(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=[
                "date",
                "window_months",
                "portfolio_var",
                "factor_var",
                "residual_var",
                "factor_risk_share_pct",
                "residual_risk_share_pct",
                "factor_coverage_pct",
            ]
        )

    def _default_layer_b_summary(
        self,
        enabled: bool,
        deprecation_notice: str = "",
        strict_required: bool = False,
    ) -> Dict[str, object]:
        return {
            "layer_b_enabled": enabled,
            "layer_b_strict_required": strict_required,
            "layer_b_deprecation_notice": deprecation_notice,
            "layer_b_latest_factor_hhi": math.nan,
            "layer_b_latest_max_factor_trc_share_pct": math.nan,
            "layer_b_latest_residual_risk_share_pct": math.nan,
            "layer_b_latest_factor_coverage_pct": math.nan,
            "layer_b_alert_factor_concentration": False,
            "layer_b_alert_high_residual": False,
            "layer_b_alert_low_coverage": False,
            "layer_b_alert_collinearity": False,
            "layer_b_breach_rate_last_12_obs_pct": math.nan,
        }

    def _prepare_factor_returns(self, factor_returns: pd.DataFrame) -> pd.DataFrame:
        required_columns = {"date", *LAYER_B_FACTOR_COLUMNS}
        missing = sorted(required_columns.difference(factor_returns.columns))
        if missing:
            raise ValueError(
                "Factor input is missing required columns: {}".format(
                    ", ".join(missing)
                )
            )

        prepared = factor_returns.copy()
        prepared["date"] = pd.to_datetime(prepared["date"], errors="coerce")
        if prepared["date"].isna().any():
            raise ValueError("Factor input has unparsable date values.")
        if prepared["date"].duplicated().any():
            duplicates = (
                prepared.loc[prepared["date"].duplicated(), "date"]
                .dt.strftime("%Y-%m-%d")
                .tolist()
            )
            raise ValueError(
                "Factor input has duplicated dates: {}.".format(", ".join(duplicates))
            )

        for column in LAYER_B_FACTOR_COLUMNS:
            prepared[column] = pd.to_numeric(prepared[column], errors="coerce")
            if prepared[column].isna().any():
                raise ValueError(
                    "Factor input has non-numeric values in '{}'.".format(column)
                )

        prepared = prepared[["date", *LAYER_B_FACTOR_COLUMNS]].sort_values("date")
        return prepared.set_index("date")

    def _layer_b_analysis(
        self, returns_wide: pd.DataFrame, weights_by_date: pd.DataFrame
    ) -> Dict[str, object]:
        empty_outputs = {
            "factor_returns_aligned": self._empty_factor_returns_aligned_table(),
            "factor_betas_by_bucket_rolling": self._empty_factor_betas_table(),
            "factor_model_quality_rolling": self._empty_factor_quality_table(),
            "factor_risk_contribution_rolling": self._empty_factor_risk_contribution_table(),
            "factor_residual_risk_rolling": self._empty_factor_residual_risk_table(),
            "summary": self._default_layer_b_summary(
                enabled=False,
                deprecation_notice=(
                    "Layer B deprecation notice: factor_input_csv is missing. "
                    "This will become required in a future major version."
                ),
                strict_required=self.layer_b_require_data,
            ),
        }
        if self.factor_returns is None:
            if self.layer_b_require_data:
                raise ValueError(
                    "Layer B factor input is required. Provide factor returns with columns: "
                    "date,growth,inflation,real_rates,credit_liquidity."
                )
            return empty_outputs

        prepared_factor_returns = self._prepare_factor_returns(self.factor_returns)
        aligned_dates = returns_wide.index.intersection(prepared_factor_returns.index)
        factor_returns_aligned = prepared_factor_returns.loc[aligned_dates].sort_index()
        if factor_returns_aligned.empty:
            message = (
                "No aligned dates between portfolio returns and factor returns after inner join."
            )
            if self.layer_b_require_data:
                raise ValueError(message)
            empty_outputs["summary"] = self._default_layer_b_summary(
                enabled=False,
                deprecation_notice=message,
                strict_required=self.layer_b_require_data,
            )
            return empty_outputs

        if (
            self.layer_b_require_data
            and len(factor_returns_aligned) < self.layer_b_min_observations
        ):
            raise ValueError(
                "Aligned factor rows ({}) are below layer_b_min_observations ({}).".format(
                    len(factor_returns_aligned), self.layer_b_min_observations
                )
            )

        (
            factor_betas,
            factor_quality,
            factor_risk_contribution,
            factor_residual_risk,
        ) = self._rolling_factor_model(
            returns_wide=returns_wide,
            weights_by_date=weights_by_date,
            factor_returns_aligned=factor_returns_aligned,
        )
        summary = self._layer_b_alert_summary(
            factor_risk_contribution=factor_risk_contribution,
            factor_residual_risk=factor_residual_risk,
            factor_model_quality=factor_quality,
        )

        return {
            "factor_returns_aligned": factor_returns_aligned,
            "factor_betas_by_bucket_rolling": factor_betas,
            "factor_model_quality_rolling": factor_quality,
            "factor_risk_contribution_rolling": factor_risk_contribution,
            "factor_residual_risk_rolling": factor_residual_risk,
            "summary": summary,
        }

    def _rolling_factor_model(
        self,
        returns_wide: pd.DataFrame,
        weights_by_date: pd.DataFrame,
        factor_returns_aligned: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        factor_columns = list(LAYER_B_FACTOR_COLUMNS)
        dates = list(returns_wide.index.sort_values())
        weights_wide = (
            weights_by_date.pivot(index="date", columns="asset_bucket", values="weight")
            .sort_index()
            .reindex(returns_wide.index)
            .fillna(0.0)
        )

        betas_rows = []
        quality_rows = []
        factor_rc_rows = []
        point_rows = []

        for date_value in dates:
            window_factors = factor_returns_aligned.loc[:date_value].tail(
                self.layer_b_window_months
            )
            factor_coverage_pct = (
                float(len(window_factors)) / float(self.layer_b_window_months) * 100.0
            )
            weights_date = (
                weights_wide.loc[date_value]
                .reindex(returns_wide.columns)
                .fillna(0.0)
                .astype(float)
            )

            betas_for_date: Dict[str, np.ndarray] = {}
            alphas_for_date: Dict[str, float] = {}
            for bucket in returns_wide.columns:
                bucket_joined = (
                    pd.concat(
                        [returns_wide[[bucket]], factor_returns_aligned], axis=1, join="inner"
                    )
                    .dropna()
                    .loc[:date_value]
                    .tail(self.layer_b_window_months)
                )
                observations = int(len(bucket_joined))
                if observations < self.layer_b_min_observations:
                    betas_rows.append(
                        {
                            "date": date_value,
                            "window_months": self.layer_b_window_months,
                            "asset_bucket": bucket,
                            "alpha": math.nan,
                            "beta_growth": math.nan,
                            "beta_inflation": math.nan,
                            "beta_real_rates": math.nan,
                            "beta_credit_liquidity": math.nan,
                            "r2": math.nan,
                            "adj_r2": math.nan,
                        }
                    )
                    quality_rows.append(
                        {
                            "date": date_value,
                            "window_months": self.layer_b_window_months,
                            "asset_bucket": bucket,
                            "condition_number": math.nan,
                            "max_vif": math.nan,
                            "quality_flag": True,
                            "observations": observations,
                        }
                    )
                    continue

                y = bucket_joined[bucket].values.astype(float)
                x_factors = bucket_joined[factor_columns].values.astype(float)
                x_design = np.column_stack([np.ones(len(x_factors)), x_factors])
                coeffs, _, _, _ = np.linalg.lstsq(x_design, y, rcond=None)
                alpha = float(coeffs[0])
                betas = coeffs[1:].astype(float)
                predictions = x_design @ coeffs
                residuals = y - predictions
                sse = float((residuals**2).sum())
                sst = float(((y - y.mean()) ** 2).sum())
                r2 = 1.0 - (sse / sst) if sst > 0 else math.nan
                factor_count = x_factors.shape[1]
                if observations > factor_count + 1 and not pd.isna(r2):
                    adj_r2 = 1.0 - (1.0 - r2) * (observations - 1) / (
                        observations - factor_count - 1
                    )
                else:
                    adj_r2 = math.nan

                condition_number = (
                    float(np.linalg.cond(x_factors))
                    if x_factors.shape[0] > 0
                    else math.nan
                )
                max_vif = self._compute_max_vif(x_factors)
                collinearity_flag = (
                    condition_number > self.layer_b_collinearity_cond_threshold
                    or max_vif > self.layer_b_vif_threshold
                )

                betas_for_date[bucket] = betas
                alphas_for_date[bucket] = alpha
                betas_rows.append(
                    {
                        "date": date_value,
                        "window_months": self.layer_b_window_months,
                        "asset_bucket": bucket,
                        "alpha": alpha,
                        "beta_growth": float(betas[0]),
                        "beta_inflation": float(betas[1]),
                        "beta_real_rates": float(betas[2]),
                        "beta_credit_liquidity": float(betas[3]),
                        "r2": float(r2) if not pd.isna(r2) else math.nan,
                        "adj_r2": float(adj_r2) if not pd.isna(adj_r2) else math.nan,
                    }
                )
                quality_rows.append(
                    {
                        "date": date_value,
                        "window_months": self.layer_b_window_months,
                        "asset_bucket": bucket,
                        "condition_number": condition_number,
                        "max_vif": max_vif,
                        "quality_flag": bool(collinearity_flag),
                        "observations": observations,
                    }
                )

            factor_metrics = self._factor_metrics_for_date(
                date_value=date_value,
                window_factors=window_factors,
                weights_date=weights_date,
                returns_date=returns_wide.loc[date_value],
                betas_for_date=betas_for_date,
                alphas_for_date=alphas_for_date,
                factor_returns_aligned=factor_returns_aligned,
            )
            factor_rc_rows.extend(factor_metrics["factor_rows"])
            point_rows.append(
                {
                    "date": date_value,
                    "portfolio_return": factor_metrics["portfolio_return"],
                    "residual_return": factor_metrics["residual_return"],
                    "factor_coverage_pct": factor_coverage_pct,
                }
            )

        factor_betas = pd.DataFrame(betas_rows).sort_values(
            ["date", "asset_bucket"]
        ).reset_index(drop=True)
        factor_quality = pd.DataFrame(quality_rows).sort_values(
            ["date", "asset_bucket"]
        ).reset_index(drop=True)
        factor_risk_contribution = pd.DataFrame(factor_rc_rows).sort_values(
            ["date", "factor"]
        ).reset_index(drop=True)

        points = pd.DataFrame(point_rows).sort_values("date").reset_index(drop=True)
        residual_rows = []
        for date_value in points["date"].tolist():
            window_points = points.loc[points["date"] <= date_value].tail(
                self.layer_b_window_months
            )
            valid = window_points.dropna(subset=["portfolio_return", "residual_return"])
            if len(valid) >= self.layer_b_min_observations:
                portfolio_var = float(valid["portfolio_return"].var(ddof=1))
                residual_var = float(valid["residual_return"].var(ddof=1))
                portfolio_var = max(portfolio_var, 0.0)
                residual_var = max(residual_var, 0.0)
                factor_var = max(portfolio_var - residual_var, 0.0)
                factor_risk_share_pct = (
                    factor_var / portfolio_var * 100.0 if portfolio_var > 0 else math.nan
                )
                residual_risk_share_pct = (
                    residual_var / portfolio_var * 100.0
                    if portfolio_var > 0
                    else math.nan
                )
            else:
                portfolio_var = math.nan
                factor_var = math.nan
                residual_var = math.nan
                factor_risk_share_pct = math.nan
                residual_risk_share_pct = math.nan
            coverage = float(
                points.loc[points["date"] == date_value, "factor_coverage_pct"].iloc[0]
            )
            residual_rows.append(
                {
                    "date": date_value,
                    "window_months": self.layer_b_window_months,
                    "portfolio_var": portfolio_var,
                    "factor_var": factor_var,
                    "residual_var": residual_var,
                    "factor_risk_share_pct": factor_risk_share_pct,
                    "residual_risk_share_pct": residual_risk_share_pct,
                    "factor_coverage_pct": coverage,
                }
            )

        factor_residual = pd.DataFrame(residual_rows).sort_values("date").reset_index(drop=True)
        return factor_betas, factor_quality, factor_risk_contribution, factor_residual

    def _factor_metrics_for_date(
        self,
        date_value: pd.Timestamp,
        window_factors: pd.DataFrame,
        weights_date: pd.Series,
        returns_date: pd.Series,
        betas_for_date: Dict[str, np.ndarray],
        alphas_for_date: Dict[str, float],
        factor_returns_aligned: pd.DataFrame,
    ) -> Dict[str, object]:
        factor_columns = list(LAYER_B_FACTOR_COLUMNS)
        active_assets = [
            asset for asset in weights_date.index if abs(float(weights_date.loc[asset])) > 1e-12
        ]
        known_assets = [asset for asset in active_assets if asset in betas_for_date]

        exposure_vector = np.full(len(factor_columns), math.nan, dtype=float)
        alpha_portfolio = math.nan
        if known_assets:
            known_weights = weights_date.loc[known_assets].astype(float).values
            betas_matrix = np.vstack([betas_for_date[asset] for asset in known_assets])
            exposure_vector = known_weights @ betas_matrix
            alpha_portfolio = float(
                np.sum([known_weights[idx] * alphas_for_date[asset] for idx, asset in enumerate(known_assets)])
            )

        trc = np.full(len(factor_columns), math.nan, dtype=float)
        trc_share_signed = np.full(len(factor_columns), math.nan, dtype=float)
        trc_share_abs = np.full(len(factor_columns), math.nan, dtype=float)
        max_share_pct = math.nan
        factor_hhi = math.nan
        factor_n_rc = math.nan
        factor_gini = math.nan
        factor_volatility = math.nan

        if (
            len(window_factors) >= self.layer_b_min_observations
            and np.isfinite(exposure_vector).all()
        ):
            factor_cov = window_factors[factor_columns].cov().values.astype(float)
            factor_variance = float(exposure_vector @ factor_cov @ exposure_vector)
            factor_variance = max(factor_variance, 0.0)
            factor_volatility = math.sqrt(factor_variance)
            if factor_volatility > 0:
                marginal = (factor_cov @ exposure_vector) / factor_volatility
                trc = exposure_vector * marginal
                trc_share_signed = trc / factor_volatility
                abs_total = float(np.abs(trc).sum())
                if abs_total > 0:
                    trc_share_abs = np.abs(trc) / abs_total
                    max_share_pct = float(np.max(trc_share_abs)) * 100.0
                    factor_hhi = float((trc_share_abs**2).sum())
                    factor_n_rc = 1.0 / factor_hhi if factor_hhi > 0 else math.nan
                    factor_gini = self._gini_from_array(trc_share_abs)
            else:
                trc = np.zeros(len(factor_columns), dtype=float)
                trc_share_signed = np.zeros(len(factor_columns), dtype=float)

        factor_rows = []
        for idx, factor_name in enumerate(factor_columns):
            factor_rows.append(
                {
                    "date": date_value,
                    "window_months": self.layer_b_window_months,
                    "factor": factor_name,
                    "trc": float(trc[idx]) if np.isfinite(trc[idx]) else math.nan,
                    "trc_share_signed": (
                        float(trc_share_signed[idx])
                        if np.isfinite(trc_share_signed[idx])
                        else math.nan
                    ),
                    "trc_share_abs": (
                        float(trc_share_abs[idx])
                        if np.isfinite(trc_share_abs[idx])
                        else math.nan
                    ),
                    "max_share_pct": max_share_pct,
                    "factor_hhi": factor_hhi,
                    "factor_n_rc": factor_n_rc,
                    "factor_gini": factor_gini,
                }
            )

        portfolio_return = self._portfolio_return_for_date(returns_date, weights_date)
        predicted_factor_return = math.nan
        residual_return = math.nan
        if (
            date_value in factor_returns_aligned.index
            and np.isfinite(exposure_vector).all()
            and np.isfinite(alpha_portfolio)
            and not pd.isna(portfolio_return)
        ):
            factor_today = factor_returns_aligned.loc[date_value, factor_columns].values.astype(float)
            predicted_factor_return = float(alpha_portfolio + exposure_vector @ factor_today)
            residual_return = float(portfolio_return - predicted_factor_return)

        return {
            "factor_rows": factor_rows,
            "portfolio_return": portfolio_return,
            "residual_return": residual_return,
        }

    def _portfolio_return_for_date(
        self, returns_date: pd.Series, weights_date: pd.Series
    ) -> float:
        available = returns_date.dropna()
        if available.empty:
            return math.nan
        aligned_weights = weights_date.reindex(available.index).fillna(0.0).astype(float)
        return float((available.astype(float) * aligned_weights).sum())

    def _compute_max_vif(self, factors_matrix: np.ndarray) -> float:
        if factors_matrix.ndim != 2 or factors_matrix.shape[1] <= 1:
            return 1.0
        max_vif = 1.0
        for idx in range(factors_matrix.shape[1]):
            target = factors_matrix[:, idx]
            other_idx = [col for col in range(factors_matrix.shape[1]) if col != idx]
            predictors = factors_matrix[:, other_idx]
            x_design = np.column_stack([np.ones(len(predictors)), predictors])
            coeffs, _, _, _ = np.linalg.lstsq(x_design, target, rcond=None)
            predicted = x_design @ coeffs
            sse = float(((target - predicted) ** 2).sum())
            sst = float(((target - target.mean()) ** 2).sum())
            if sst <= 0:
                continue
            r2 = 1.0 - (sse / sst)
            r2 = min(max(r2, 0.0), 0.999999)
            vif = 1.0 / (1.0 - r2)
            max_vif = max(max_vif, float(vif))
        return max_vif

    def _gini_from_array(self, values: np.ndarray) -> float:
        clean = np.asarray(values, dtype=float)
        clean = clean[np.isfinite(clean)]
        if clean.size == 0:
            return math.nan
        clean = clean[clean >= 0.0]
        if clean.size == 0:
            return math.nan
        total = float(clean.sum())
        if total <= 0:
            return math.nan
        sorted_values = np.sort(clean)
        n = sorted_values.size
        index = np.arange(1, n + 1, dtype=float)
        gini = (2.0 * float((index * sorted_values).sum()) / (n * total)) - (
            (n + 1.0) / n
        )
        return max(min(float(gini), 1.0), 0.0)

    def _layer_b_alert_summary(
        self,
        factor_risk_contribution: pd.DataFrame,
        factor_residual_risk: pd.DataFrame,
        factor_model_quality: pd.DataFrame,
    ) -> Dict[str, object]:
        summary = self._default_layer_b_summary(
            enabled=True,
            deprecation_notice="",
            strict_required=self.layer_b_require_data,
        )
        if factor_residual_risk.empty:
            return summary

        latest_date = pd.Timestamp(factor_residual_risk["date"].max())
        latest_residual = factor_residual_risk.loc[
            factor_residual_risk["date"] == latest_date
        ].iloc[0]
        latest_factor = factor_risk_contribution.loc[
            factor_risk_contribution["date"] == latest_date
        ]
        latest_hhi_values = latest_factor["factor_hhi"].dropna()
        latest_max_share_values = latest_factor["max_share_pct"].dropna()
        latest_factor_hhi = (
            float(latest_hhi_values.iloc[0])
            if not latest_hhi_values.empty
            else math.nan
        )
        latest_max_share = (
            float(latest_max_share_values.iloc[0])
            if not latest_max_share_values.empty
            else math.nan
        )
        latest_residual_share = float(latest_residual["residual_risk_share_pct"])
        latest_coverage = float(latest_residual["factor_coverage_pct"])
        latest_collinearity = False
        latest_quality = factor_model_quality.loc[
            factor_model_quality["date"] == latest_date
        ]
        if not latest_quality.empty:
            latest_collinearity = bool(
                (
                    latest_quality["condition_number"] > self.layer_b_collinearity_cond_threshold
                ).fillna(False).any()
                or (latest_quality["max_vif"] > self.layer_b_vif_threshold)
                .fillna(False)
                .any()
            )

        alert_factor_concentration = (
            (not pd.isna(latest_max_share) and latest_max_share > self.layer_b_max_factor_trc_share * 100.0)
            or (
                not pd.isna(latest_factor_hhi)
                and latest_factor_hhi > self.layer_b_factor_hhi_threshold
            )
        )
        alert_high_residual = (
            not pd.isna(latest_residual_share)
            and latest_residual_share > self.layer_b_residual_share_threshold * 100.0
        )
        alert_low_coverage = (
            not pd.isna(latest_coverage)
            and latest_coverage < self.layer_b_min_coverage_pct
        )

        factor_by_date = (
            factor_risk_contribution.groupby("date", as_index=False)[
                ["max_share_pct", "factor_hhi"]
            ]
            .max()
            .rename(columns={"max_share_pct": "max_factor_share_pct"})
        )
        residual_by_date = factor_residual_risk[
            ["date", "residual_risk_share_pct", "factor_coverage_pct"]
        ]
        collinearity_by_date = (
            factor_model_quality.assign(
                collinearity_flag=(
                    (factor_model_quality["condition_number"] > self.layer_b_collinearity_cond_threshold)
                    | (factor_model_quality["max_vif"] > self.layer_b_vif_threshold)
                ).fillna(False)
            )
            .groupby("date", as_index=False)["collinearity_flag"]
            .max()
        )
        joined = factor_by_date.merge(residual_by_date, on="date", how="outer").merge(
            collinearity_by_date, on="date", how="left"
        )
        joined["collinearity_flag"] = joined["collinearity_flag"].fillna(False)
        joined = joined.sort_values("date").tail(12)
        if joined.empty:
            breach_rate = math.nan
        else:
            any_breach = (
                (joined["max_factor_share_pct"] > self.layer_b_max_factor_trc_share * 100.0)
                | (joined["factor_hhi"] > self.layer_b_factor_hhi_threshold)
                | (
                    joined["residual_risk_share_pct"]
                    > self.layer_b_residual_share_threshold * 100.0
                )
                | (joined["factor_coverage_pct"] < self.layer_b_min_coverage_pct)
                | joined["collinearity_flag"]
            )
            breach_rate = float(any_breach.fillna(False).mean() * 100.0)

        summary.update(
            {
                "layer_b_latest_factor_hhi": latest_factor_hhi,
                "layer_b_latest_max_factor_trc_share_pct": latest_max_share,
                "layer_b_latest_residual_risk_share_pct": latest_residual_share,
                "layer_b_latest_factor_coverage_pct": latest_coverage,
                "layer_b_alert_factor_concentration": bool(alert_factor_concentration),
                "layer_b_alert_high_residual": bool(alert_high_residual),
                "layer_b_alert_low_coverage": bool(alert_low_coverage),
                "layer_b_alert_collinearity": bool(latest_collinearity),
                "layer_b_breach_rate_last_12_obs_pct": breach_rate,
            }
        )
        return summary
    def _normalize_layer_a_windows(self, raw_windows: tuple[int, ...]) -> tuple[int, ...]:
        unique_windows = sorted(
            {
                int(window)
                for window in raw_windows
                if int(window) > 0
            }
        )
        if not unique_windows:
            raise ValueError("layer_a_windows must contain positive integers.")
        return tuple(unique_windows)

    def _validate_factor_mapping(self, normalized: pd.DataFrame) -> None:
        unmapped = sorted(
            normalized.loc[normalized["factor"] == "Unmapped", "asset_bucket"]
            .dropna()
            .unique()
            .tolist()
        )
        if unmapped and not self.allow_unmapped_factors:
            raise ValueError(
                "Unmapped asset_bucket values in factor map: {}. "
                "Provide factor_map entries or set allow_unmapped_factors=True.".format(
                    ", ".join(unmapped)
                )
            )

    def _aggregate_bucket_history(self, normalized: pd.DataFrame) -> pd.DataFrame:
        def _weighted_return(group: pd.DataFrame) -> float:
            with_returns = group[group["return_pct"].notna()]
            if with_returns.empty:
                return math.nan
            weights = with_returns["market_value_base"].astype(float)
            if float(weights.sum()) == 0.0:
                return float(with_returns["return_pct"].mean())
            return float(
                (with_returns["return_pct"].astype(float) * weights).sum()
                / weights.sum()
            )

        def _currency_label(series: pd.Series) -> str:
            unique_values = series.dropna().unique()
            if len(unique_values) == 0:
                return self.base_currency
            if len(unique_values) == 1:
                return str(unique_values[0])
            return "MIXED"

        records = []
        for (date_value, bucket), group in normalized.groupby(
            ["date", "asset_bucket"], sort=False
        ):
            records.append(
                {
                    "date": date_value,
                    "asset_bucket": bucket,
                    "market_value": float(group["market_value"].sum()),
                    "market_value_base": float(group["market_value_base"].sum()),
                    "provided_return_pct": _weighted_return(group),
                    "currency": _currency_label(group["currency"]),
                }
            )

        aggregated = pd.DataFrame.from_records(records)
        return aggregated.sort_values(["asset_bucket", "date"]).reset_index(drop=True)

    def _calculate_weights_by_date(self, normalized: pd.DataFrame) -> pd.DataFrame:
        grouped = (
            normalized.groupby(["date", "asset_bucket"], as_index=False)["market_value_base"]
            .sum()
            .sort_values(["date", "asset_bucket"])
            .reset_index(drop=True)
        )
        totals = grouped.groupby("date")["market_value_base"].sum().rename("total_market_value")
        gross_totals = grouped.groupby("date")["market_value_base"].apply(
            lambda values: float(values.abs().sum())
        ).rename("gross_market_value")
        grouped = grouped.join(totals, on="date")
        grouped = grouped.join(gross_totals, on="date")

        near_zero_net = grouped["total_market_value"].abs() < 1e-12
        if near_zero_net.any():
            bad_dates = (
                grouped.loc[near_zero_net, "date"]
                .drop_duplicates()
                .dt.strftime("%Y-%m-%d")
                .tolist()
            )
            raise ValueError(
                "Net market value is ~0 for dates: {}. "
                "Cannot compute portfolio weights under full netting.".format(
                    ", ".join(bad_dates)
                )
            )

        grouped["weight"] = grouped["market_value_base"] / grouped["total_market_value"]
        grouped["weight_pct"] = grouped["weight"] * 100.0
        grouped["gross_leverage"] = (
            grouped["gross_market_value"] / grouped["total_market_value"].abs()
        )
        grouped["net_to_gross"] = (
            grouped["total_market_value"].abs() / grouped["gross_market_value"]
        )
        return grouped

    def _build_returns_matrix(self, normalized: pd.DataFrame) -> pd.DataFrame:
        duplicates = normalized.duplicated(subset=["date", "asset_bucket"]).any()
        if duplicates:
            raise ValueError(
                "Expected unique (date, asset_bucket) rows after normalization."
            )
        returns = normalized.pivot(
            index="date", columns="asset_bucket", values="return_pct"
        ).sort_index()
        return returns

    def _resolve_analysis_frequency(
        self, dates: pd.Index, requested_frequency: str
    ) -> str:
        if requested_frequency in {"daily", "monthly"}:
            return requested_frequency
        date_index = pd.DatetimeIndex(dates).dropna().sort_values().unique()
        if len(date_index) < 2:
            return "monthly"
        day_steps = np.diff(date_index.values.astype("datetime64[D]")).astype(int)
        positive_steps = day_steps[day_steps > 0]
        if positive_steps.size == 0:
            return "monthly"
        median_step = float(np.median(positive_steps))
        return "daily" if median_step <= 3.0 else "monthly"

    def _resolve_covariance_window(
        self, total_rows: int, analysis_frequency: str
    ) -> int:
        if total_rows <= 0:
            return 0
        if self.covariance_window is not None:
            return min(self.covariance_window, total_rows)
        if analysis_frequency == "daily":
            return min(252, total_rows)
        return total_rows

    def _apply_covariance_window(
        self, returns_wide: pd.DataFrame, covariance_window: int
    ) -> pd.DataFrame:
        if covariance_window <= 0:
            return returns_wide.iloc[0:0].copy()
        return returns_wide.tail(covariance_window)

    def _build_asset_coverage_table(self, returns_wide: pd.DataFrame) -> pd.DataFrame:
        total_rows = int(len(returns_wide.index))
        if returns_wide.empty:
            return pd.DataFrame(
                columns=[
                    "asset_bucket",
                    "observations",
                    "coverage_pct",
                    "included_for_covariance",
                ]
            )
        observations = returns_wide.notna().sum(axis=0).astype(int)
        if total_rows > 0:
            coverage_pct = observations / float(total_rows) * 100.0
        else:
            coverage_pct = pd.Series(0.0, index=observations.index)
        table = pd.DataFrame(
            {
                "asset_bucket": observations.index,
                "observations": observations.values,
                "coverage_pct": coverage_pct.values,
            }
        )
        table["included_for_covariance"] = (
            table["coverage_pct"] >= self.min_asset_coverage_pct
        )
        return table.sort_values(
            ["included_for_covariance", "coverage_pct", "asset_bucket"],
            ascending=[False, False, True],
        ).reset_index(drop=True)

    def _compute_covariance_matrix(self, returns_wide: pd.DataFrame) -> pd.DataFrame:
        if returns_wide.empty:
            return pd.DataFrame(index=returns_wide.columns, columns=returns_wide.columns, dtype=float)
        if self.covariance_method == "ewma":
            return self._ewma_covariance(returns_wide, self.ewma_alpha)
        if self.covariance_method == "sample":
            return returns_wide.cov(min_periods=self.min_covariance_observations)
        return self._ledoit_wolf_covariance(returns_wide)

    def _empty_covariance_matrix(self, assets: list[str]) -> pd.DataFrame:
        return pd.DataFrame(
            math.nan,
            index=assets,
            columns=assets,
            dtype=float,
        )

    def _ledoit_wolf_covariance(self, returns_wide: pd.DataFrame) -> pd.DataFrame:
        try:
            from sklearn.covariance import LedoitWolf
        except ImportError as exc:
            raise ImportError(
                "covariance_method='ledoit-wolf' requires scikit-learn. "
                "Install scikit-learn to use this covariance method."
            ) from exc
        assets = list(returns_wide.columns)
        complete_rows = returns_wide.dropna()
        if len(complete_rows.index) < self.min_covariance_observations:
            return self._empty_covariance_matrix(assets)
        estimator = LedoitWolf()
        estimator.fit(complete_rows.values.astype(float))
        return pd.DataFrame(
            estimator.covariance_,
            index=assets,
            columns=assets,
            dtype=float,
        )

    def _returns_weights_for_layer_ab(
        self,
        returns_wide: pd.DataFrame,
        weights_by_date: pd.DataFrame,
        analysis_frequency: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if analysis_frequency != "daily":
            return returns_wide, weights_by_date
        monthly_returns = self._resample_returns_to_monthly(returns_wide)
        monthly_weights = self._resample_weights_to_monthly(weights_by_date)
        return monthly_returns, monthly_weights

    def _resample_returns_to_monthly(self, returns_wide: pd.DataFrame) -> pd.DataFrame:
        if returns_wide.empty:
            return returns_wide.copy()

        if self.return_type == "log":
            monthly = returns_wide.resample("ME").sum(min_count=1)
        else:
            def _compound(values: pd.Series) -> float:
                clean = values.dropna().astype(float)
                if clean.empty:
                    return math.nan
                return float(np.prod(1.0 + clean.values) - 1.0)

            monthly = returns_wide.resample("ME").apply(_compound)
        return monthly.sort_index()

    def _resample_weights_to_monthly(self, weights_by_date: pd.DataFrame) -> pd.DataFrame:
        if weights_by_date.empty:
            return weights_by_date.copy()
        weights_wide = (
            weights_by_date.pivot(index="date", columns="asset_bucket", values="weight")
            .sort_index()
            .resample("ME")
            .last()
        )
        stacked_weights = weights_wide.stack()
        monthly = (
            stacked_weights.dropna()
            .rename("weight")
            .reset_index()
            .sort_values(["date", "asset_bucket"])
            .reset_index(drop=True)
        )
        return monthly

    def _ewma_covariance(
        self, returns_wide: pd.DataFrame, alpha: float
    ) -> pd.DataFrame:
        if not 0 < alpha < 1:
            raise ValueError("ewma_alpha must be between 0 and 1.")

        assets = list(returns_wide.columns)
        R = returns_wide.to_numpy(dtype=float)
        n_obs, n_assets = R.shape
        nan_mask = np.isnan(R)
        cov = np.full((n_assets, n_assets), math.nan, dtype=float)
        for i in range(n_assets):
            for j in range(i, n_assets):
                valid_mask = ~nan_mask[:, i] & ~nan_mask[:, j]
                count = int(valid_mask.sum())
                if count < self.min_covariance_observations:
                    continue
                # Match the original: decay weights are arange(count-1, -1, -1)
                # applied to the dropped-NaN slice (i.e. count = remaining rows).
                w = np.power(1.0 - alpha, np.arange(count - 1, -1, -1))
                w = w / w.sum()
                li = R[valid_mask, i]
                rj = R[valid_mask, j]
                li_mean = float((li * w).sum())
                rj_mean = float((rj * w).sum())
                cov_value = float((w * (li - li_mean) * (rj - rj_mean)).sum())
                cov[i, j] = cov_value
                cov[j, i] = cov_value
        return pd.DataFrame(cov, index=assets, columns=assets)

    def _pairwise_confidence_flags(self, returns_wide: pd.DataFrame) -> pd.DataFrame:
        rows = []
        columns = list(returns_wide.columns)
        total_rows = len(returns_wide.index)
        for left_idx, left_asset in enumerate(columns):
            for right_asset in columns[left_idx + 1 :]:
                pair = returns_wide[[left_asset, right_asset]].dropna()
                overlap = int(len(pair))
                coverage = (overlap / total_rows) if total_rows > 0 else 0.0
                flag = (
                    "LOW"
                    if overlap < self.min_pair_overlap
                    else "HIGH"
                )
                rows.append(
                    {
                        "asset_left": left_asset,
                        "asset_right": right_asset,
                        "overlap_observations": overlap,
                        "coverage_ratio": coverage,
                        "confidence_flag": flag,
                    }
                )
        if not rows:
            return pd.DataFrame(
                columns=[
                    "asset_left",
                    "asset_right",
                    "overlap_observations",
                    "coverage_ratio",
                    "confidence_flag",
                ]
            )
        return pd.DataFrame(rows).sort_values(
            ["confidence_flag", "overlap_observations"],
            ascending=[True, False],
        ).reset_index(drop=True)

    def _tail_risk_metrics(
        self,
        returns_wide: pd.DataFrame,
        weights_by_date: pd.DataFrame,
        analysis_frequency: str,
    ) -> pd.DataFrame:
        rolling_window_observations_1y = 252 if analysis_frequency == "daily" else 12
        weights_wide = weights_by_date.pivot(
            index="date", columns="asset_bucket", values="weight"
        ).sort_index()
        common_assets = [asset for asset in returns_wide.columns if asset in weights_wide.columns]
        if not common_assets:
            return pd.DataFrame(
                [
                    {
                        "var_95_pct": math.nan,
                        "cvar_95_pct": math.nan,
                        "max_drawdown_pct": math.nan,
                        "worst_rolling_12m_drawdown_pct": math.nan,
                        "portfolio_return_observations": 0,
                        "tail_data_coverage_pct": 0.0,
                        "rolling_window_observations_1y": rolling_window_observations_1y,
                    }
                ]
            )

        aligned_returns = returns_wide[common_assets]
        aligned_weights = (
            weights_wide[common_assets]
            .reindex(aligned_returns.index)
            .shift(1)
        )
        complete_rows = aligned_returns.notna().all(axis=1) & aligned_weights.notna().all(axis=1)
        portfolio_returns = (aligned_returns.loc[complete_rows] * aligned_weights.loc[complete_rows]).sum(
            axis=1
        )
        total_candidate_rows = int(len(aligned_returns.index))
        coverage_pct = (
            float(len(portfolio_returns)) / total_candidate_rows * 100.0
            if total_candidate_rows > 0
            else 0.0
        )

        if portfolio_returns.empty:
            return pd.DataFrame(
                [
                    {
                        "var_95_pct": math.nan,
                        "cvar_95_pct": math.nan,
                        "max_drawdown_pct": math.nan,
                        "worst_rolling_12m_drawdown_pct": math.nan,
                        "portfolio_return_observations": 0,
                        "tail_data_coverage_pct": coverage_pct,
                        "rolling_window_observations_1y": rolling_window_observations_1y,
                    }
                ]
            )

        var_95 = float(portfolio_returns.quantile(0.05))
        tail = portfolio_returns[portfolio_returns <= var_95]
        cvar_95 = float(tail.mean()) if not tail.empty else var_95

        cumulative = (1.0 + portfolio_returns).cumprod()
        running_peak = cumulative.cummax()
        drawdown = cumulative / running_peak - 1.0
        max_drawdown = float(drawdown.min())

        rolling_peak_12m = cumulative.rolling(
            window=rolling_window_observations_1y,
            min_periods=1,
        ).max()
        rolling_drawdown_12m = cumulative / rolling_peak_12m - 1.0
        worst_rolling_12m_drawdown = float(rolling_drawdown_12m.min())

        return pd.DataFrame(
            [
                {
                    "var_95_pct": var_95 * 100.0,
                    "cvar_95_pct": cvar_95 * 100.0,
                    "max_drawdown_pct": max_drawdown * 100.0,
                    "worst_rolling_12m_drawdown_pct": worst_rolling_12m_drawdown
                    * 100.0,
                    "portfolio_return_observations": int(len(portfolio_returns)),
                    "tail_data_coverage_pct": coverage_pct,
                    "rolling_window_observations_1y": rolling_window_observations_1y,
                }
            ]
        )

    def _rolling_pairwise_correlation(
        self, returns_wide: pd.DataFrame, windows: tuple[int, int]
    ) -> pd.DataFrame:
        asset_pairs = list(combinations(returns_wide.columns, 2))
        records = []
        for date_idx, date_value in enumerate(returns_wide.index):
            for left_asset, right_asset in asset_pairs:
                record = {
                    "date": date_value,
                    "asset_left": left_asset,
                    "asset_right": right_asset,
                }
                for window in windows:
                    start_idx = date_idx - window + 1
                    if start_idx < 0:
                        record[f"corr_{window}m"] = math.nan
                        continue

                    left_window = returns_wide[left_asset].iloc[start_idx : date_idx + 1]
                    right_window = returns_wide[right_asset].iloc[start_idx : date_idx + 1]
                    record[f"corr_{window}m"] = left_window.corr(right_window)
                records.append(record)

        return pd.DataFrame(records).sort_values(
            ["date", "asset_left", "asset_right"]
        ).reset_index(drop=True)

    def _layer_a_rollup(
        self, returns_wide: pd.DataFrame, weights_by_date: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        metrics_rows = []
        trc_rows = []
        cluster_rows = []

        weights_wide = (
            weights_by_date.pivot(index="date", columns="asset_bucket", values="weight")
            .sort_index()
            .reindex(returns_wide.index)
            .fillna(0.0)
        )

        for date_value in returns_wide.index:
            current_weights = (
                weights_wide.loc[date_value]
                .reindex(returns_wide.columns)
                .fillna(0.0)
                .astype(float)
            )
            active_assets = [
                asset
                for asset, weight in current_weights.items()
                if abs(float(weight)) > 1e-12
            ]
            for window in self.layer_a_windows:
                window_returns = returns_wide.loc[:date_value].tail(window)
                (
                    metrics_row,
                    window_trc_rows,
                    window_cluster_rows,
                ) = self._layer_a_window_metrics(
                    date_value=date_value,
                    window=window,
                    window_returns=window_returns,
                    current_weights=current_weights,
                    active_assets=active_assets,
                )
                metrics_rows.append(metrics_row)
                trc_rows.extend(window_trc_rows)
                cluster_rows.extend(window_cluster_rows)

        if metrics_rows:
            metrics = pd.DataFrame(metrics_rows).sort_values(
                ["date", "window_months"]
            ).reset_index(drop=True)
        else:
            metrics = pd.DataFrame(
                columns=[
                    "date",
                    "window_months",
                    "asset_count",
                    "observation_count",
                    "covariance_coverage_pct",
                    "avg_corr",
                    "avg_abs_corr",
                    "high_corr_pair_share_pct",
                    "cluster_count",
                    "neff",
                    "portfolio_volatility",
                    "max_trc_share_pct",
                    "risk_hhi",
                    "n_rc",
                    "risk_gini",
                    "diversification_ratio",
                ]
            )

        if trc_rows:
            trc = pd.DataFrame(trc_rows).sort_values(
                ["date", "window_months", "asset_bucket"]
            ).reset_index(drop=True)
        else:
            trc = pd.DataFrame(
                columns=[
                    "date",
                    "window_months",
                    "asset_bucket",
                    "weight",
                    "trc",
                    "trc_share_signed",
                    "trc_share_abs",
                    "covariance_included",
                ]
            )

        if cluster_rows:
            clusters = pd.DataFrame(cluster_rows).sort_values(
                ["date", "window_months", "asset_bucket"]
            ).reset_index(drop=True)
        else:
            clusters = pd.DataFrame(
                columns=["date", "window_months", "asset_bucket", "cluster_id"]
            )
        return metrics, trc, clusters

    def _layer_a_window_metrics(
        self,
        date_value: pd.Timestamp,
        window: int,
        window_returns: pd.DataFrame,
        current_weights: pd.Series,
        active_assets: list[str],
    ) -> tuple[dict[str, object], list[dict[str, object]], list[dict[str, object]]]:
        observation_count = int(len(window_returns))
        correlation = window_returns.corr(
            min_periods=self.min_covariance_observations
        )
        if self.covariance_method == "ewma":
            covariance = self._ewma_covariance(window_returns, self.ewma_alpha)
        elif self.covariance_method == "ledoit-wolf":
            covariance = self._ledoit_wolf_covariance(window_returns)
        else:
            covariance = window_returns.cov(
                min_periods=self.min_covariance_observations
            )

        corr_assets = [asset for asset in active_assets if asset in correlation]
        corr_subset = (
            correlation.loc[corr_assets, corr_assets]
            if corr_assets
            else pd.DataFrame(dtype=float)
        )
        if corr_subset.empty:
            corr_complete = corr_subset
        else:
            valid_corr_mask = ~(corr_subset.isna().any(axis=0) | corr_subset.isna().any(axis=1))
            valid_corr_assets = corr_subset.index[valid_corr_mask].tolist()
            corr_complete = corr_subset.loc[valid_corr_assets, valid_corr_assets]

        pair_values = []
        pair_count = 0
        if not corr_complete.empty:
            corr_columns = list(corr_complete.columns)
            for left_idx, left_asset in enumerate(corr_columns):
                for right_asset in corr_columns[left_idx + 1 :]:
                    corr_value = corr_complete.loc[left_asset, right_asset]
                    if pd.isna(corr_value):
                        continue
                    pair_values.append(float(corr_value))
            pair_count = len(pair_values)
        avg_corr = float(np.mean(pair_values)) if pair_values else math.nan
        avg_abs_corr = float(np.mean(np.abs(pair_values))) if pair_values else math.nan
        high_corr_pair_share_pct = (
            float(
                100.0
                * sum(
                    abs(value) > self.layer_a_high_corr_threshold
                    for value in pair_values
                )
                / pair_count
            )
            if pair_count > 0
            else math.nan
        )
        neff = self._effective_bets_from_correlation(corr_complete)
        cluster_membership = self._hac_clusters_from_correlation(
            corr_complete, self.layer_a_cluster_corr_cutoff
        )
        cluster_count = int(cluster_membership.nunique()) if not cluster_membership.empty else 0

        cluster_rows = [
            {
                "date": date_value,
                "window_months": window,
                "asset_bucket": asset,
                "cluster_id": (
                    int(cluster_membership.loc[asset])
                    if asset in cluster_membership.index
                    else math.nan
                ),
            }
            for asset in active_assets
        ]

        cov_assets = [asset for asset in active_assets if asset in covariance]
        cov_subset = (
            covariance.loc[cov_assets, cov_assets]
            if cov_assets
            else pd.DataFrame(dtype=float)
        )
        if cov_subset.empty:
            valid_cov_assets: list[str] = []
        else:
            valid_cov_mask = ~(cov_subset.isna().any(axis=0) | cov_subset.isna().any(axis=1))
            valid_cov_assets = cov_subset.index[valid_cov_mask].tolist()

        active_abs_weight = (
            float(current_weights.loc[active_assets].abs().sum()) if active_assets else 0.0
        )
        included_abs_weight = (
            float(current_weights.loc[valid_cov_assets].abs().sum()) if valid_cov_assets else 0.0
        )
        coverage_pct = (
            included_abs_weight / active_abs_weight * 100.0
            if active_abs_weight > 0
            else 0.0
        )

        trc_lookup: Dict[str, float] = {}
        trc_signed_lookup: Dict[str, float] = {}
        trc_abs_lookup: Dict[str, float] = {}
        portfolio_volatility = math.nan
        max_trc_share_pct = math.nan
        risk_hhi = math.nan
        n_rc = math.nan
        risk_gini = math.nan
        diversification_ratio = math.nan

        if valid_cov_assets:
            valid_weights = current_weights.loc[valid_cov_assets].astype(float)
            valid_covariance = cov_subset.loc[valid_cov_assets, valid_cov_assets].astype(float)
            weight_vector = valid_weights.values
            cov_values = valid_covariance.values
            portfolio_variance, variance_contributions = portfolio_variance_contributions(
                weight_vector, cov_values
            )
            portfolio_variance = max(portfolio_variance, 0.0)
            portfolio_volatility = math.sqrt(portfolio_variance)

            if portfolio_volatility > 0:
                trc_values = variance_contributions / portfolio_volatility
                trc_share_signed = trc_values / portfolio_volatility
                trc_abs_total = float(np.abs(trc_values).sum())
                if trc_abs_total > 0:
                    trc_share_abs = np.abs(trc_values) / trc_abs_total
                    max_trc_share_pct = float(np.max(trc_share_abs)) * 100.0
                    risk_hhi = float((trc_share_abs**2).sum())
                    n_rc = (1.0 / risk_hhi) if risk_hhi > 0 else math.nan
                    risk_gini = self._gini_from_distribution(trc_share_abs)
                else:
                    trc_share_abs = np.repeat(math.nan, len(trc_values))

                asset_volatility = np.sqrt(np.clip(np.diag(cov_values), a_min=0.0, a_max=None))
                diversification_ratio = float(
                    (np.abs(weight_vector) * asset_volatility).sum() / portfolio_volatility
                )
            else:
                trc_values = np.zeros(len(valid_cov_assets), dtype=float)
                trc_share_signed = np.zeros(len(valid_cov_assets), dtype=float)
                trc_share_abs = np.repeat(math.nan, len(valid_cov_assets))

            for index, asset in enumerate(valid_cov_assets):
                trc_lookup[asset] = float(trc_values[index])
                trc_signed_lookup[asset] = float(trc_share_signed[index])
                trc_abs_lookup[asset] = float(trc_share_abs[index])

        trc_rows = [
            {
                "date": date_value,
                "window_months": window,
                "asset_bucket": asset,
                "weight": float(current_weights.loc[asset]),
                "trc": trc_lookup.get(asset, math.nan),
                "trc_share_signed": trc_signed_lookup.get(asset, math.nan),
                "trc_share_abs": trc_abs_lookup.get(asset, math.nan),
                "covariance_included": asset in valid_cov_assets,
            }
            for asset in active_assets
        ]

        metrics_row = {
            "date": date_value,
            "window_months": window,
            "asset_count": int(len(active_assets)),
            "observation_count": observation_count,
            "covariance_coverage_pct": coverage_pct,
            "avg_corr": avg_corr,
            "avg_abs_corr": avg_abs_corr,
            "high_corr_pair_share_pct": high_corr_pair_share_pct,
            "cluster_count": cluster_count,
            "neff": neff,
            "portfolio_volatility": portfolio_volatility,
            "max_trc_share_pct": max_trc_share_pct,
            "risk_hhi": risk_hhi,
            "n_rc": n_rc,
            "risk_gini": risk_gini,
            "diversification_ratio": diversification_ratio,
        }
        return metrics_row, trc_rows, cluster_rows

    def _effective_bets_from_correlation(self, correlation: pd.DataFrame) -> float:
        if correlation.empty:
            return math.nan
        corr_values = correlation.values.astype(float)
        try:
            eigenvalues = np.linalg.eigvalsh(corr_values)
        except np.linalg.LinAlgError:
            return math.nan
        clipped = np.clip(eigenvalues, a_min=0.0, a_max=None)
        eigen_sum = float(clipped.sum())
        if eigen_sum <= 0:
            return math.nan
        probabilities = clipped / eigen_sum
        probabilities = probabilities[probabilities > 0]
        if probabilities.size == 0:
            return math.nan
        entropy = float(-(probabilities * np.log(probabilities)).sum())
        return float(np.exp(entropy))

    @staticmethod
    def _hac_clusters_from_correlation(
        correlation: pd.DataFrame, corr_cutoff: float
    ) -> pd.Series:
        if correlation.empty:
            return pd.Series(dtype=int)

        assets = list(correlation.index)
        if len(assets) == 1:
            return pd.Series({assets[0]: 1}, dtype=int)

        corr_values = correlation.abs().clip(lower=0.0, upper=1.0).values.astype(float)
        distance_matrix = 1.0 - corr_values
        np.fill_diagonal(distance_matrix, 0.0)
        distance_cutoff = 1.0 - corr_cutoff

        clusters: Dict[int, set[int]] = {idx: {idx} for idx in range(len(assets))}
        next_cluster_id = len(assets)
        while True:
            candidate_pair: Optional[tuple[int, int]] = None
            candidate_distance = math.inf
            cluster_ids = sorted(clusters.keys())
            for left_idx, left_cluster_id in enumerate(cluster_ids):
                for right_cluster_id in cluster_ids[left_idx + 1 :]:
                    distance_value = DalioHolyGrailAnalyzer._average_linkage_distance(
                        distance_matrix,
                        clusters[left_cluster_id],
                        clusters[right_cluster_id],
                    )
                    if distance_value < candidate_distance:
                        candidate_distance = distance_value
                        candidate_pair = (left_cluster_id, right_cluster_id)

            if candidate_pair is None or candidate_distance > distance_cutoff:
                break

            left_cluster_id, right_cluster_id = candidate_pair
            merged_cluster = clusters[left_cluster_id] | clusters[right_cluster_id]
            del clusters[left_cluster_id]
            del clusters[right_cluster_id]
            clusters[next_cluster_id] = merged_cluster
            next_cluster_id += 1

        assignments: Dict[str, int] = {}
        ordered_clusters = sorted(clusters.values(), key=lambda values: min(values))
        for cluster_label, member_indices in enumerate(ordered_clusters, start=1):
            for member_idx in sorted(member_indices):
                assignments[assets[member_idx]] = cluster_label
        return pd.Series(assignments, dtype=int)

    @staticmethod
    def _average_linkage_distance(
        distance_matrix: np.ndarray,
        left_members: set[int],
        right_members: set[int],
    ) -> float:
        left_indices = np.array(sorted(left_members), dtype=int)
        right_indices = np.array(sorted(right_members), dtype=int)
        if left_indices.size == 0 or right_indices.size == 0:
            return math.inf
        pair_distances = distance_matrix[np.ix_(left_indices, right_indices)]
        if pair_distances.size == 0:
            return math.inf
        return float(pair_distances.mean())

    def _gini_from_distribution(self, values: np.ndarray) -> float:
        clean_values = np.asarray(values, dtype=float)
        clean_values = clean_values[np.isfinite(clean_values)]
        if clean_values.size == 0:
            return math.nan
        if (clean_values < 0).any():
            return math.nan
        total = float(clean_values.sum())
        if total <= 0:
            return math.nan

        sorted_values = np.sort(clean_values)
        n = sorted_values.size
        index = np.arange(1, n + 1, dtype=float)
        gini = (2.0 * float((index * sorted_values).sum()) / (n * total)) - (
            (n + 1.0) / n
        )
        return max(min(float(gini), 1.0), 0.0)

    def _run_quality_checks(
        self, normalized: pd.DataFrame, weights_by_date: pd.DataFrame
    ) -> pd.DataFrame:
        checks = []

        duplicate_pairs_after_aggregation = int(
            normalized.duplicated(subset=["date", "asset_bucket"]).sum()
        )
        checks.append(
            {
                "check": "unique_date_asset_bucket_after_aggregation",
                "passed": duplicate_pairs_after_aggregation == 0,
                "details": (
                    "No duplicate (date, asset_bucket) rows after aggregation."
                    if duplicate_pairs_after_aggregation == 0
                    else f"Found {duplicate_pairs_after_aggregation} duplicates."
                ),
            }
        )

        checks.append(
            {
                "check": "raw_duplicate_pairs_aggregated",
                "passed": True,
                "details": f"Raw duplicate (date, asset_bucket) rows aggregated: {self.raw_duplicate_pairs_count}",
            }
        )

        missing_months_by_bucket = {}
        for bucket, bucket_data in normalized.groupby("asset_bucket"):
            months = pd.PeriodIndex(bucket_data["month"].unique()).sort_values()
            expected_months = pd.period_range(months.min(), months.max(), freq="M")
            missing = expected_months.difference(months)
            if len(missing) > 0:
                missing_months_by_bucket[bucket] = [str(period) for period in missing]

        checks.append(
            {
                "check": "no_missing_monthly_dates",
                "passed": len(missing_months_by_bucket) == 0,
                "details": (
                    "All asset buckets have continuous monthly history."
                    if not missing_months_by_bucket
                    else str(missing_months_by_bucket)
                ),
            }
        )

        frequency = normalized.groupby("asset_bucket")["month"].nunique().sort_values()
        checks.append(
            {
                "check": "consistent_frequency",
                "passed": frequency.nunique() == 1,
                "details": (
                    "All buckets have the same number of monthly observations."
                    if frequency.nunique() == 1
                    else frequency.to_dict()
                ),
            }
        )

        weights_sum = weights_by_date.groupby("date")["weight"].sum()
        max_deviation = float((weights_sum - 1.0).abs().max()) if not weights_sum.empty else 0.0
        checks.append(
            {
                "check": "weights_sum_to_100",
                "passed": max_deviation < 1e-8,
                "details": f"Max deviation from 100%: {max_deviation:.10f}",
            }
        )

        history_months = int(normalized["month"].nunique())
        checks.append(
            {
                "check": "minimum_history_window",
                "passed": history_months >= self.min_history_months,
                "details": (
                    f"History months: {history_months} (required >= {self.min_history_months})"
                ),
            }
        )

        has_negative_exposure = bool((normalized["market_value_base"] < 0).any())
        checks.append(
            {
                "check": "short_exposure_policy",
                "passed": (not has_negative_exposure) or self.allow_shorts,
                "details": (
                    "No negative market values detected."
                    if not has_negative_exposure
                    else (
                        "Negative market values detected and shorts are allowed."
                        if self.allow_shorts
                        else "Negative market values detected while shorts are disabled."
                    )
                ),
            }
        )

        max_gross_leverage = float(weights_by_date["gross_leverage"].max()) if not weights_by_date.empty else 0.0
        checks.append(
            {
                "check": "gross_leverage_limit",
                "passed": max_gross_leverage <= self.max_gross_leverage,
                "details": (
                    f"Max gross leverage: {max_gross_leverage:.4f} "
                    f"(limit <= {self.max_gross_leverage:.4f})"
                ),
            }
        )

        min_net_to_gross = float(weights_by_date["net_to_gross"].min()) if not weights_by_date.empty else 1.0
        checks.append(
            {
                "check": "netting_risk_limit",
                "passed": min_net_to_gross >= self.min_net_to_gross,
                "details": (
                    f"Min net/gross: {min_net_to_gross:.4f} "
                    f"(limit >= {self.min_net_to_gross:.4f})"
                ),
            }
        )

        return pd.DataFrame(checks)

    def _latest_weights(self, weights_by_date: pd.DataFrame) -> pd.Series:
        latest_date = weights_by_date["date"].max()
        latest = (
            weights_by_date.loc[weights_by_date["date"] == latest_date, ["asset_bucket", "weight"]]
            .set_index("asset_bucket")
            .sort_index()["weight"]
        )
        return latest

    def _diversification_metrics(self, latest_weights: pd.Series) -> Dict[str, float]:
        hhi = float((latest_weights.pow(2)).sum())
        effective_bets = 1.0 / hhi if hhi > 0 else 0.0
        return {
            "hhi": hhi,
            "effective_bets": effective_bets,
            "bucket_count": int((latest_weights > 0).sum()),
        }

    def _risk_contribution_by_bucket(
        self, latest_weights: pd.Series, covariance_matrix: pd.DataFrame
    ) -> pd.DataFrame:
        common_buckets = [bucket for bucket in latest_weights.index if bucket in covariance_matrix]
        if not common_buckets:
            return pd.DataFrame(
                columns=[
                    "asset_bucket",
                    "weight",
                    "marginal_contribution",
                    "risk_contribution",
                    "risk_contribution_pct",
                    "portfolio_volatility",
                    "covariance_included",
                    "rc_weight_coverage_pct",
                    "rc_excluded_weight_pct",
                ]
            )

        covariance = covariance_matrix.loc[common_buckets, common_buckets]
        valid_mask = ~(covariance.isna().any(axis=0) | covariance.isna().any(axis=1))
        valid_buckets = covariance.index[valid_mask].tolist()
        excluded_buckets = [bucket for bucket in common_buckets if bucket not in valid_buckets]
        total_weight = float(latest_weights.loc[common_buckets].sum())
        included_weight = float(latest_weights.loc[valid_buckets].sum()) if valid_buckets else 0.0
        excluded_weight = max(total_weight - included_weight, 0.0)
        coverage_pct = (included_weight / total_weight * 100.0) if total_weight > 0 else 0.0
        excluded_pct = (excluded_weight / total_weight * 100.0) if total_weight > 0 else 0.0
        if not valid_buckets:
            result = pd.DataFrame(
                columns=[
                    "asset_bucket",
                    "weight",
                    "marginal_contribution",
                    "risk_contribution",
                    "risk_contribution_pct",
                    "portfolio_volatility",
                    "covariance_included",
                    "rc_weight_coverage_pct",
                    "rc_excluded_weight_pct",
                ]
            )
            for bucket in common_buckets:
                result.loc[len(result)] = {
                    "asset_bucket": bucket,
                    "weight": float(latest_weights.loc[bucket]),
                    "marginal_contribution": math.nan,
                    "risk_contribution": math.nan,
                    "risk_contribution_pct": math.nan,
                    "portfolio_volatility": math.nan,
                    "covariance_included": False,
                    "rc_weight_coverage_pct": coverage_pct,
                    "rc_excluded_weight_pct": excluded_pct,
                }
            return result.reset_index(drop=True)

        weights = latest_weights.loc[valid_buckets]
        covariance = covariance.loc[valid_buckets, valid_buckets]
        weight_vector = weights.values
        cov_values = covariance.values
        portfolio_variance = float(weight_vector @ cov_values @ weight_vector)
        portfolio_variance = max(portfolio_variance, 0.0)
        portfolio_volatility = math.sqrt(portfolio_variance)

        marginal_contribution = cov_values @ weight_vector
        if portfolio_volatility > 0:
            risk_contribution = weight_vector * marginal_contribution / portfolio_volatility
            risk_contribution_pct = risk_contribution / portfolio_volatility
        else:
            risk_contribution = weight_vector * 0.0
            risk_contribution_pct = weight_vector * 0.0

        result = pd.DataFrame(
            {
                "asset_bucket": valid_buckets,
                "weight": weight_vector,
                "marginal_contribution": marginal_contribution,
                "risk_contribution": risk_contribution,
                "risk_contribution_pct": risk_contribution_pct,
                "portfolio_volatility": portfolio_volatility,
                "covariance_included": True,
                "rc_weight_coverage_pct": coverage_pct,
                "rc_excluded_weight_pct": excluded_pct,
            }
        ).sort_values("risk_contribution_pct", ascending=False)
        if excluded_buckets:
            excluded_frame = pd.DataFrame(
                {
                    "asset_bucket": excluded_buckets,
                    "weight": latest_weights.loc[excluded_buckets].values,
                    "marginal_contribution": [math.nan] * len(excluded_buckets),
                    "risk_contribution": [math.nan] * len(excluded_buckets),
                    "risk_contribution_pct": [math.nan] * len(excluded_buckets),
                    "portfolio_volatility": [portfolio_volatility] * len(excluded_buckets),
                    "covariance_included": [False] * len(excluded_buckets),
                    "rc_weight_coverage_pct": [coverage_pct] * len(excluded_buckets),
                    "rc_excluded_weight_pct": [excluded_pct] * len(excluded_buckets),
                }
            )
            result = pd.concat([result, excluded_frame], ignore_index=True)
        return result.reset_index(drop=True)

    def _factor_exposure(
        self, latest_weights: pd.Series, risk_contribution: pd.DataFrame
    ) -> pd.DataFrame:
        factor_table = (
            latest_weights.rename("weight")
            .rename_axis("asset_bucket")
            .reset_index()
            .assign(factor=lambda frame: frame["asset_bucket"].map(self.factor_map).fillna("Unmapped"))
        )

        if risk_contribution.empty:
            factor_table["risk_contribution_pct"] = math.nan
            factor_table["covariance_included"] = False
        else:
            factor_table = factor_table.merge(
                risk_contribution[
                    ["asset_bucket", "risk_contribution_pct", "covariance_included"]
                ],
                on="asset_bucket",
                how="left",
            )
            factor_table["covariance_included"] = factor_table["covariance_included"].fillna(
                False
            )

        grouped_rows = []
        for factor_name, group in factor_table.groupby("factor", sort=False):
            total_weight = float(group["weight"].sum())
            known_weight = float(group.loc[group["covariance_included"], "weight"].sum())
            risk_complete = bool(group["covariance_included"].all())
            risk_pct = (
                float(
                    group.loc[group["covariance_included"], "risk_contribution_pct"].sum()
                )
                if risk_complete
                else math.nan
            )
            grouped_rows.append(
                {
                    "factor": factor_name,
                    "weight": total_weight,
                    "known_rc_weight": known_weight,
                    "risk_contribution_pct": risk_pct,
                }
            )

        grouped = (
            pd.DataFrame(grouped_rows)
            .sort_values("weight", ascending=False)
            .reset_index(drop=True)
        )
        grouped["unknown_rc_weight"] = grouped["weight"] - grouped["known_rc_weight"]
        grouped["risk_contribution_complete"] = grouped["unknown_rc_weight"].abs() < 1e-12
        grouped["weight_pct"] = grouped["weight"] * 100.0
        grouped["risk_contribution_pct"] = grouped["risk_contribution_pct"] * 100.0
        grouped["known_rc_weight_pct"] = grouped["known_rc_weight"] * 100.0
        grouped["unknown_rc_weight_pct"] = grouped["unknown_rc_weight"] * 100.0
        return grouped

    def _stress_tests(
        self, latest_weights: pd.Series, weights_by_date: pd.DataFrame
    ) -> pd.DataFrame:
        latest_date = weights_by_date["date"].max()
        latest_total_value = float(
            weights_by_date.loc[weights_by_date["date"] == latest_date, "total_market_value"].iloc[0]
        )
        weights_dict = latest_weights.to_dict()
        rows = []
        for scenario, shocks in self.scenario_shocks.items():
            missing_buckets = sorted(
                bucket for bucket in weights_dict if bucket not in shocks
            )
            if missing_buckets and not self.allow_partial_scenarios:
                raise ValueError(
                    f"Scenario '{scenario}' is missing shocks for buckets: "
                    f"{', '.join(missing_buckets)}"
                )
            portfolio_return = 0.0
            for bucket, weight in weights_dict.items():
                bucket_shock = float(shocks.get(bucket, 0.0))
                portfolio_return += weight * bucket_shock

            stressed_value = latest_total_value * (1.0 + portfolio_return)
            rows.append(
                {
                    "scenario": scenario,
                    "portfolio_return_pct": portfolio_return * 100.0,
                    "estimated_drawdown_pct": min(portfolio_return, 0.0) * 100.0,
                    "stressed_portfolio_value": stressed_value,
                    "absolute_pnl": stressed_value - latest_total_value,
                    "scenario_coverage_pct": (
                        (len(weights_dict) - len(missing_buckets)) / max(len(weights_dict), 1)
                    )
                    * 100.0,
                    "missing_shock_buckets": ",".join(missing_buckets),
                    "bonds_shock_pct": shocks.get("Bonds", 0.0) * 100.0,
                    "stocks_shock_pct": shocks.get("Stocks", 0.0) * 100.0,
                    "precious_metals_shock_pct": shocks.get("Precious Metals", 0.0) * 100.0,
                    "commodities_shock_pct": shocks.get("Commodities", 0.0) * 100.0,
                    "crypto_coins_shock_pct": shocks.get("Crypto Coins", 0.0) * 100.0,
                }
            )

        return pd.DataFrame(rows).sort_values("portfolio_return_pct").reset_index(drop=True)

    def _high_correlation_pairs(
        self, correlation_matrix: pd.DataFrame, threshold: float
    ) -> pd.DataFrame:
        rows = []
        columns = list(correlation_matrix.columns)
        for left_idx, left_bucket in enumerate(columns):
            for right_bucket in columns[left_idx + 1 :]:
                corr_value = correlation_matrix.loc[left_bucket, right_bucket]
                if pd.isna(corr_value):
                    continue
                if abs(float(corr_value)) >= threshold:
                    rows.append(
                        {
                            "asset_left": left_bucket,
                            "asset_right": right_bucket,
                            "correlation": float(corr_value),
                            "abs_correlation": abs(float(corr_value)),
                        }
                    )
        result = pd.DataFrame(rows)
        if result.empty:
            return pd.DataFrame(columns=["asset_left", "asset_right", "correlation", "abs_correlation"])
        return result.sort_values("abs_correlation", ascending=False).reset_index(drop=True)

    def _weight_drift(
        self,
        latest_weights: pd.Series,
        target_weights: Optional[Mapping[str, float]],
        threshold: float,
    ) -> pd.DataFrame:
        if not target_weights:
            return pd.DataFrame(
                columns=[
                    "asset_bucket",
                    "target_weight",
                    "current_weight",
                    "drift_ratio",
                    "drift_breach",
                ]
            )

        target_series = pd.Series({k: float(v) for k, v in target_weights.items()})
        if target_series.empty:
            return pd.DataFrame()
        if target_series.max() > 1.0:
            target_series = target_series / 100.0
        target_series = target_series / target_series.sum()

        current = latest_weights.reindex(target_series.index).fillna(0.0)
        safe_target = target_series.replace(0.0, pd.NA)
        drift_ratio = (current - target_series).abs() / safe_target
        drift_ratio = drift_ratio.fillna(0.0)

        drift = pd.DataFrame(
            {
                "asset_bucket": target_series.index,
                "target_weight": target_series.values,
                "current_weight": current.values,
                "drift_ratio": drift_ratio.values,
            }
        )
        drift["drift_breach"] = drift["drift_ratio"] > threshold
        return drift.sort_values("drift_ratio", ascending=False).reset_index(drop=True)

    def _management_rules_summary(
        self,
        normalized: pd.DataFrame,
        weights_by_date: pd.DataFrame,
        high_corr_pairs: pd.DataFrame,
        risk_contribution: pd.DataFrame,
        max_risk_contribution: float,
        weight_drift: pd.DataFrame,
        corr_threshold: float,
        drift_threshold: float,
        pairwise_confidence: pd.DataFrame,
        layer_b_summary: Dict[str, object],
        layer_a_metrics_rolling: pd.DataFrame,
        analysis_frequency: str,
        covariance_method_effective: str,
        covariance_window_effective: int,
        assets_excluded_low_coverage: list[str],
        layer_ab_input_frequency: str,
    ) -> Dict[str, object]:
        latest_date = pd.Timestamp(normalized["date"].max())
        excluded_weight_pct = (
            float(risk_contribution["rc_excluded_weight_pct"].max())
            if not risk_contribution.empty and "rc_excluded_weight_pct" in risk_contribution
            else 0.0
        )
        risk_data_complete = excluded_weight_pct < 1e-8
        risk_breaches: Optional[int]
        if risk_data_complete:
            risk_breaches = int(
                (risk_contribution["risk_contribution_pct"] > max_risk_contribution).sum()
            )
        else:
            risk_breaches = None
        drift_breaches = int(weight_drift.get("drift_breach", pd.Series(dtype=bool)).sum())
        low_conf_pairs = int(
            (pairwise_confidence["confidence_flag"] == "LOW").sum()
        ) if not pairwise_confidence.empty else 0
        total_pairs = int(len(pairwise_confidence))
        data_quality_penalty = (
            (low_conf_pairs / total_pairs) * 100.0 if total_pairs > 0 else 0.0
        )
        max_gross_leverage = (
            float(weights_by_date["gross_leverage"].max()) if not weights_by_date.empty else math.nan
        )
        min_net_to_gross = (
            float(weights_by_date["net_to_gross"].min()) if not weights_by_date.empty else math.nan
        )
        management_rules = {
            "corr_threshold": corr_threshold,
            "corr_breach_count": int(len(high_corr_pairs)),
            "max_risk_contribution": max_risk_contribution,
            "risk_contribution_breach_count": risk_breaches,
            "risk_contribution_data_complete": risk_data_complete,
            "rc_excluded_weight_pct": excluded_weight_pct,
            "drift_threshold": drift_threshold,
            "weight_drift_breach_count": drift_breaches,
            "min_pair_overlap": self.min_pair_overlap,
            "low_confidence_pair_count": low_conf_pairs,
            "data_quality_penalty_pct": data_quality_penalty,
            "allow_shorts": self.allow_shorts,
            "max_gross_leverage_observed": max_gross_leverage,
            "max_gross_leverage_limit": self.max_gross_leverage,
            "min_net_to_gross_observed": min_net_to_gross,
            "min_net_to_gross_limit": self.min_net_to_gross,
            "quarterly_rebalance_due": bool(latest_date.is_quarter_end),
            "next_rebalance_date": str(latest_date + pd.offsets.QuarterEnd()),
            "analysis_frequency": analysis_frequency,
            "covariance_method_effective": covariance_method_effective,
            "covariance_window_effective": covariance_window_effective,
            "assets_excluded_low_coverage": assets_excluded_low_coverage,
            "layer_ab_input_frequency": layer_ab_input_frequency,
        }
        management_rules.update(layer_b_summary)
        primary_window = self.layer_a_primary_window
        primary_rows = layer_a_metrics_rolling.loc[
            layer_a_metrics_rolling["window_months"] == primary_window
        ].sort_values("date")
        management_rules["layer_a_primary_window_months"] = primary_window

        latest_primary = primary_rows.iloc[-1] if not primary_rows.empty else None
        management_rules["layer_a_latest_avg_abs_corr"] = (
            float(latest_primary["avg_abs_corr"]) if latest_primary is not None else math.nan
        )
        management_rules["layer_a_latest_high_corr_pair_share_pct"] = (
            float(latest_primary["high_corr_pair_share_pct"])
            if latest_primary is not None
            else math.nan
        )
        management_rules["layer_a_latest_cluster_count"] = (
            int(latest_primary["cluster_count"]) if latest_primary is not None else math.nan
        )
        management_rules["layer_a_latest_neff"] = (
            float(latest_primary["neff"]) if latest_primary is not None else math.nan
        )
        management_rules["layer_a_latest_max_trc_share_pct"] = (
            float(latest_primary["max_trc_share_pct"])
            if latest_primary is not None
            else math.nan
        )
        management_rules["layer_a_latest_n_rc"] = (
            float(latest_primary["n_rc"]) if latest_primary is not None else math.nan
        )
        management_rules["layer_a_latest_diversification_ratio"] = (
            float(latest_primary["diversification_ratio"])
            if latest_primary is not None
            else math.nan
        )

        layer_a_alert_high_corr = False
        layer_a_alert_risk_concentration = False
        layer_a_alert_low_independent_bets = False
        if latest_primary is not None:
            high_corr_value = float(latest_primary["high_corr_pair_share_pct"])
            max_trc_value = float(latest_primary["max_trc_share_pct"])
            n_rc_value = float(latest_primary["n_rc"])
            neff_value = float(latest_primary["neff"])
            layer_a_alert_high_corr = (
                not pd.isna(high_corr_value)
                and high_corr_value > 30.0
            )
            layer_a_alert_risk_concentration = (
                not pd.isna(max_trc_value)
                and max_trc_value > self.layer_a_trc_max_share_threshold * 100.0
            )
            layer_a_alert_low_independent_bets = (
                (not pd.isna(n_rc_value) and n_rc_value < self.layer_a_min_n_rc)
                or (not pd.isna(neff_value) and neff_value < self.layer_a_min_n_rc)
            )

        management_rules["layer_a_alert_high_corr"] = layer_a_alert_high_corr
        management_rules["layer_a_alert_risk_concentration"] = layer_a_alert_risk_concentration
        management_rules["layer_a_alert_low_independent_bets"] = layer_a_alert_low_independent_bets

        primary_tail = primary_rows.tail(12)
        if primary_tail.empty:
            breach_rate = math.nan
        else:
            breach_flags = (
                (
                    primary_tail["high_corr_pair_share_pct"] > 30.0
                )
                | (
                    primary_tail["max_trc_share_pct"]
                    > self.layer_a_trc_max_share_threshold * 100.0
                )
                | (
                    primary_tail["n_rc"] < self.layer_a_min_n_rc
                )
            )
            breach_rate = float(breach_flags.mean() * 100.0)
        management_rules["layer_a_breach_rate_last_12_obs_pct"] = breach_rate
        return management_rules

    def _score_high(self, value: float, floor: float, target: float) -> float:
        if pd.isna(value):
            return math.nan
        if target <= floor:
            raise ValueError("score_high target must be greater than floor.")
        normalized = (float(value) - floor) / (target - floor)
        clipped = float(np.clip(normalized, 0.0, 1.0))
        return clipped * 100.0

    def _score_low(self, value: float, good: float, bad: float) -> float:
        if pd.isna(value):
            return math.nan
        if bad <= good:
            raise ValueError("score_low bad must be greater than good.")
        normalized = (bad - float(value)) / (bad - good)
        clipped = float(np.clip(normalized, 0.0, 1.0))
        return clipped * 100.0

    def _weighted_metric_score(
        self, metric_scores: Dict[str, float], metric_weights: Dict[str, float]
    ) -> float:
        weighted_sum = 0.0
        available_weight = 0.0
        for metric_name, metric_weight in metric_weights.items():
            score_value = metric_scores.get(metric_name, math.nan)
            if pd.isna(score_value):
                continue
            weighted_sum += float(score_value) * float(metric_weight)
            available_weight += float(metric_weight)
        if available_weight <= 0:
            return math.nan
        return weighted_sum / available_weight

    def _robustness_distribution(
        self, primary_rows: pd.DataFrame
    ) -> tuple[Dict[str, Dict[str, float]], pd.DataFrame]:
        tracked_metrics = [
            "neff",
            "avg_abs_corr",
            "high_corr_pair_share_pct",
            "max_trc_share_pct",
            "n_rc",
            "risk_gini",
        ]
        records: list[dict[str, object]] = []
        stats: Dict[str, Dict[str, float]] = {}
        for metric_name in tracked_metrics:
            series = (
                pd.to_numeric(primary_rows.get(metric_name), errors="coerce")
                .dropna()
                .astype(float)
            )
            if series.empty:
                p10 = math.nan
                median = math.nan
                p90 = math.nan
            else:
                p10 = float(series.quantile(0.10))
                median = float(series.median())
                p90 = float(series.quantile(0.90))
            stats[metric_name] = {"p10": p10, "median": median, "p90": p90}
            records.append(
                {
                    "metric": metric_name,
                    "p10": p10,
                    "median": median,
                    "p90": p90,
                    "window_months": self.layer_a_primary_window,
                }
            )
        return stats, pd.DataFrame(records)

    def _build_red_flags(
        self,
        latest_primary: Optional[pd.Series],
        primary_rows: pd.DataFrame,
        layer_a_trc_rolling: pd.DataFrame,
        robustness_stats: Dict[str, Dict[str, float]],
        macro_metrics: Dict[str, float],
        layer_b_enabled: bool,
    ) -> list[dict[str, object]]:
        flags: list[dict[str, object]] = []

        def _append_flag(
            code: str,
            severity: str,
            message: str,
            value: object,
            threshold: object,
            context: Dict[str, object],
        ) -> None:
            flags.append(
                {
                    "code": code,
                    "severity": severity,
                    "message": message,
                    "value": value,
                    "threshold": threshold,
                    "context": json.dumps(
                        context, ensure_ascii=True, sort_keys=True, default=str
                    ),
                }
            )

        latest_date: Optional[pd.Timestamp] = None
        if latest_primary is not None and "date" in latest_primary.index:
            latest_date = pd.Timestamp(latest_primary["date"])

        if latest_primary is not None:
            max_trc_share_pct = float(latest_primary.get("max_trc_share_pct", math.nan))
            if not pd.isna(max_trc_share_pct) and max_trc_share_pct > 35.0:
                top_bucket = "unknown"
                top_bucket_share_pct = math.nan
                if latest_date is not None:
                    latest_trc = layer_a_trc_rolling.loc[
                        (layer_a_trc_rolling["date"] == latest_date)
                        & (
                            layer_a_trc_rolling["window_months"]
                            == self.layer_a_primary_window
                        )
                    ].dropna(subset=["trc_share_abs"])
                    if not latest_trc.empty:
                        idx = latest_trc["trc_share_abs"].idxmax()
                        top_bucket = str(latest_trc.loc[idx, "asset_bucket"])
                        top_bucket_share_pct = float(
                            latest_trc.loc[idx, "trc_share_abs"]
                        ) * 100.0
                _append_flag(
                    code="RISK_CONCENTRATION_ASSET",
                    severity="HIGH",
                    message=(
                        "Most portfolio risk is concentrated in '{}' (max TRC share "
                        "{:.2f}%).".format(top_bucket, max_trc_share_pct)
                    ),
                    value=max_trc_share_pct,
                    threshold=35.0,
                    context={
                        "asset_bucket": top_bucket,
                        "asset_trc_share_pct": top_bucket_share_pct,
                        "window_months": self.layer_a_primary_window,
                    },
                )

            neff_value = float(latest_primary.get("neff", math.nan))
            n_rc_value = float(latest_primary.get("n_rc", math.nan))
            if (
                (not pd.isna(neff_value) and neff_value < 4.0)
                or (not pd.isna(n_rc_value) and n_rc_value < 4.0)
            ):
                low_independent_value = min(
                    value
                    for value in [neff_value, n_rc_value]
                    if not pd.isna(value)
                )
                _append_flag(
                    code="LOW_INDEPENDENT_BETS",
                    severity="HIGH",
                    message=(
                        "Effective independent bets are low (neff={:.2f}, n_rc={:.2f})."
                    ).format(neff_value, n_rc_value),
                    value=low_independent_value,
                    threshold=4.0,
                    context={"neff": neff_value, "n_rc": n_rc_value},
                )

        volatility_rows = primary_rows.dropna(
            subset=["portfolio_volatility", "avg_abs_corr"]
        )
        if not volatility_rows.empty:
            top_count = max(1, int(math.ceil(len(volatility_rows) * 0.10)))
            stress_rows = volatility_rows.nlargest(top_count, "portfolio_volatility")
            stress_median_corr = float(stress_rows["avg_abs_corr"].median())
            overall_median_corr = float(volatility_rows["avg_abs_corr"].median())
            delta_corr = stress_median_corr - overall_median_corr
            if stress_median_corr >= 0.75 and delta_corr >= 0.15:
                _append_flag(
                    code="CORR_COLLAPSE_IN_STRESS",
                    severity="MEDIUM",
                    message=(
                        "Correlations collapse in stress windows (stress median "
                        "avg_abs_corr={:.2f}, overall median={:.2f})."
                    ).format(stress_median_corr, overall_median_corr),
                    value=stress_median_corr,
                    threshold=">=0.75 and delta>=0.15",
                    context={
                        "stress_median_avg_abs_corr": stress_median_corr,
                        "overall_median_avg_abs_corr": overall_median_corr,
                        "delta_avg_abs_corr": delta_corr,
                        "stress_window_count": top_count,
                    },
                )

        p10_neff = robustness_stats.get("neff", {}).get("p10", math.nan)
        p90_max_trc = robustness_stats.get("max_trc_share_pct", {}).get("p90", math.nan)
        p90_high_corr = robustness_stats.get("high_corr_pair_share_pct", {}).get(
            "p90", math.nan
        )
        if (
            (not pd.isna(p10_neff) and p10_neff < 3.0)
            or (not pd.isna(p90_max_trc) and p90_max_trc > 45.0)
            or (not pd.isna(p90_high_corr) and p90_high_corr > 60.0)
        ):
            _append_flag(
                code="UNSTABLE_ROLLING_PROFILE",
                severity="MEDIUM",
                message=(
                    "Rolling profile is unstable: p10(neff)={:.2f}, "
                    "p90(max_trc_share_pct)={:.2f}, "
                    "p90(high_corr_pair_share_pct)={:.2f}."
                ).format(p10_neff, p90_max_trc, p90_high_corr),
                value=p90_max_trc if not pd.isna(p90_max_trc) else p10_neff,
                threshold="p10(neff)<3 or p90(max_trc)>45 or p90(high_corr)>60",
                context={
                    "p10_neff": p10_neff,
                    "p90_max_trc_share_pct": p90_max_trc,
                    "p90_high_corr_pair_share_pct": p90_high_corr,
                },
            )

        if layer_b_enabled:
            max_factor_share = float(
                macro_metrics.get("max_factor_trc_share_pct", math.nan)
            )
            factor_hhi = float(macro_metrics.get("factor_hhi", math.nan))
            residual_share = float(
                macro_metrics.get("residual_risk_share_pct", math.nan)
            )
            factor_coverage = float(macro_metrics.get("factor_coverage_pct", math.nan))
            if (
                (not pd.isna(max_factor_share) and max_factor_share > 35.0)
                or (not pd.isna(factor_hhi) and factor_hhi > 0.35)
            ):
                _append_flag(
                    code="FACTOR_CONCENTRATION",
                    severity="HIGH",
                    message=(
                        "Factor risk is concentrated (max_factor_trc_share_pct={:.2f}, "
                        "factor_hhi={:.3f})."
                    ).format(max_factor_share, factor_hhi),
                    value=max_factor_share if not pd.isna(max_factor_share) else factor_hhi,
                    threshold="max_factor_trc_share_pct>35 or factor_hhi>0.35",
                    context={
                        "max_factor_trc_share_pct": max_factor_share,
                        "factor_hhi": factor_hhi,
                    },
                )
            if (
                (not pd.isna(factor_coverage) and factor_coverage < 80.0)
                or (not pd.isna(residual_share) and residual_share > 40.0)
            ):
                _append_flag(
                    code="LOW_FACTOR_COVERAGE_OR_HIGH_RESIDUAL",
                    severity="HIGH",
                    message=(
                        "Layer B quality warning (factor_coverage_pct={:.2f}, "
                        "residual_risk_share_pct={:.2f})."
                    ).format(factor_coverage, residual_share),
                    value=residual_share if not pd.isna(residual_share) else factor_coverage,
                    threshold="factor_coverage_pct<80 or residual_risk_share_pct>40",
                    context={
                        "factor_coverage_pct": factor_coverage,
                        "residual_risk_share_pct": residual_share,
                    },
                )
        return flags

    def _holy_grail_class(self, score: float) -> str:
        if pd.isna(score):
            return "Unavailable"
        if score >= 85.0:
            return "Strong"
        if score >= 70.0:
            return "Good"
        if score >= 55.0:
            return "Watch"
        return "Weak"

    def _holy_grail_verdict(
        self,
        layer_a_metrics_rolling: pd.DataFrame,
        layer_a_trc_rolling: pd.DataFrame,
        factor_risk_contribution_rolling: pd.DataFrame,
        factor_residual_risk_rolling: pd.DataFrame,
        layer_b_enabled: bool,
    ) -> tuple[Dict[str, object], pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        primary_rows = layer_a_metrics_rolling.loc[
            layer_a_metrics_rolling["window_months"] == self.layer_a_primary_window
        ].sort_values("date")
        latest_primary = primary_rows.iloc[-1] if not primary_rows.empty else None

        independence_weights = {
            "neff": 0.50,
            "avg_abs_corr": 0.25,
            "high_corr_pair_share_pct": 0.25,
        }
        balance_weights = {
            "max_trc_share_pct": 0.40,
            "n_rc": 0.35,
            "risk_gini": 0.25,
        }
        macro_weights = {
            "max_factor_trc_share_pct": 0.35,
            "factor_hhi": 0.30,
            "factor_n_rc": 0.20,
            "factor_gini": 0.15,
        }

        latest_metrics = {
            "neff": (
                float(latest_primary["neff"]) if latest_primary is not None else math.nan
            ),
            "avg_abs_corr": (
                float(latest_primary["avg_abs_corr"])
                if latest_primary is not None
                else math.nan
            ),
            "high_corr_pair_share_pct": (
                float(latest_primary["high_corr_pair_share_pct"])
                if latest_primary is not None
                else math.nan
            ),
            "max_trc_share_pct": (
                float(latest_primary["max_trc_share_pct"])
                if latest_primary is not None
                else math.nan
            ),
            "n_rc": (
                float(latest_primary["n_rc"]) if latest_primary is not None else math.nan
            ),
            "risk_gini": (
                float(latest_primary["risk_gini"])
                if latest_primary is not None
                else math.nan
            ),
        }

        independence_metric_scores = {
            "neff": self._score_high(latest_metrics["neff"], floor=1.0, target=8.0),
            "avg_abs_corr": self._score_low(
                latest_metrics["avg_abs_corr"], good=0.20, bad=0.70
            ),
            "high_corr_pair_share_pct": self._score_low(
                latest_metrics["high_corr_pair_share_pct"], good=10.0, bad=30.0
            ),
        }
        balance_metric_scores = {
            "max_trc_share_pct": self._score_low(
                latest_metrics["max_trc_share_pct"], good=20.0, bad=35.0
            ),
            "n_rc": self._score_high(latest_metrics["n_rc"], floor=1.0, target=8.0),
            "risk_gini": self._score_low(
                latest_metrics["risk_gini"], good=0.20, bad=0.60
            ),
        }
        independence_score = self._weighted_metric_score(
            independence_metric_scores, independence_weights
        )
        balance_score = self._weighted_metric_score(
            balance_metric_scores, balance_weights
        )

        robustness_stats, robustness_table = self._robustness_distribution(primary_rows)
        independence_median_score = self._weighted_metric_score(
            {
                "neff": self._score_high(
                    robustness_stats["neff"]["median"], floor=1.0, target=8.0
                ),
                "avg_abs_corr": self._score_low(
                    robustness_stats["avg_abs_corr"]["median"], good=0.20, bad=0.70
                ),
                "high_corr_pair_share_pct": self._score_low(
                    robustness_stats["high_corr_pair_share_pct"]["median"],
                    good=10.0,
                    bad=30.0,
                ),
            },
            independence_weights,
        )
        balance_median_score = self._weighted_metric_score(
            {
                "max_trc_share_pct": self._score_low(
                    robustness_stats["max_trc_share_pct"]["median"],
                    good=20.0,
                    bad=35.0,
                ),
                "n_rc": self._score_high(
                    robustness_stats["n_rc"]["median"], floor=1.0, target=8.0
                ),
                "risk_gini": self._score_low(
                    robustness_stats["risk_gini"]["median"], good=0.20, bad=0.60
                ),
            },
            balance_weights,
        )
        median_composite = self._weighted_metric_score(
            {
                "independence": independence_median_score,
                "balance": balance_median_score,
            },
            {"independence": 0.50, "balance": 0.50},
        )

        independence_tail_score = self._weighted_metric_score(
            {
                "neff": self._score_high(
                    robustness_stats["neff"]["p10"], floor=1.0, target=8.0
                ),
                "avg_abs_corr": self._score_low(
                    robustness_stats["avg_abs_corr"]["p90"], good=0.20, bad=0.70
                ),
                "high_corr_pair_share_pct": self._score_low(
                    robustness_stats["high_corr_pair_share_pct"]["p90"],
                    good=10.0,
                    bad=30.0,
                ),
            },
            independence_weights,
        )
        balance_tail_score = self._weighted_metric_score(
            {
                "max_trc_share_pct": self._score_low(
                    robustness_stats["max_trc_share_pct"]["p90"],
                    good=20.0,
                    bad=35.0,
                ),
                "n_rc": self._score_high(
                    robustness_stats["n_rc"]["p10"], floor=1.0, target=8.0
                ),
                "risk_gini": self._score_low(
                    robustness_stats["risk_gini"]["p90"], good=0.20, bad=0.60
                ),
            },
            balance_weights,
        )
        tail_composite = self._weighted_metric_score(
            {
                "independence": independence_tail_score,
                "balance": balance_tail_score,
            },
            {"independence": 0.50, "balance": 0.50},
        )
        robustness_score = self._weighted_metric_score(
            {"median": median_composite, "tail": tail_composite},
            {"median": 0.60, "tail": 0.40},
        )

        latest_macro_metrics = {
            "max_factor_trc_share_pct": math.nan,
            "factor_hhi": math.nan,
            "factor_n_rc": math.nan,
            "factor_gini": math.nan,
            "residual_risk_share_pct": math.nan,
            "factor_coverage_pct": math.nan,
        }
        if layer_b_enabled and not factor_risk_contribution_rolling.empty:
            latest_factor_date = pd.Timestamp(
                factor_risk_contribution_rolling["date"].max()
            )
            latest_factor_rows = factor_risk_contribution_rolling.loc[
                factor_risk_contribution_rolling["date"] == latest_factor_date
            ]
            max_share_values = latest_factor_rows["max_share_pct"].dropna()
            factor_hhi_values = latest_factor_rows["factor_hhi"].dropna()
            factor_n_rc_values = latest_factor_rows["factor_n_rc"].dropna()
            factor_gini_values = latest_factor_rows["factor_gini"].dropna()
            latest_macro_metrics.update(
                {
                    "max_factor_trc_share_pct": (
                        float(max_share_values.iloc[0])
                        if not max_share_values.empty
                        else math.nan
                    ),
                    "factor_hhi": (
                        float(factor_hhi_values.iloc[0])
                        if not factor_hhi_values.empty
                        else math.nan
                    ),
                    "factor_n_rc": (
                        float(factor_n_rc_values.iloc[0])
                        if not factor_n_rc_values.empty
                        else math.nan
                    ),
                    "factor_gini": (
                        float(factor_gini_values.iloc[0])
                        if not factor_gini_values.empty
                        else math.nan
                    ),
                }
            )
        if layer_b_enabled and not factor_residual_risk_rolling.empty:
            latest_residual_row = factor_residual_risk_rolling.sort_values("date").iloc[-1]
            latest_macro_metrics.update(
                {
                    "residual_risk_share_pct": float(
                        latest_residual_row.get("residual_risk_share_pct", math.nan)
                    ),
                    "factor_coverage_pct": float(
                        latest_residual_row.get("factor_coverage_pct", math.nan)
                    ),
                }
            )

        macro_metric_scores = {
            "max_factor_trc_share_pct": self._score_low(
                latest_macro_metrics["max_factor_trc_share_pct"], good=25.0, bad=40.0
            ),
            "factor_hhi": self._score_low(
                latest_macro_metrics["factor_hhi"], good=0.20, bad=0.40
            ),
            "factor_n_rc": self._score_high(
                latest_macro_metrics["factor_n_rc"], floor=1.0, target=4.0
            ),
            "factor_gini": self._score_low(
                latest_macro_metrics["factor_gini"], good=0.20, bad=0.60
            ),
        }
        macro_score = self._weighted_metric_score(macro_metric_scores, macro_weights)
        macro_available = layer_b_enabled and not pd.isna(macro_score)

        component_scores = {
            "independence": independence_score,
            "balance": balance_score,
            "robustness": robustness_score,
            "macro": macro_score if macro_available else math.nan,
        }

        effective_weights = {name: 0.0 for name in HOLY_GRAIL_COMPONENT_WEIGHTS}
        available_components = [
            name
            for name, score in component_scores.items()
            if not pd.isna(score)
        ]
        if available_components:
            raw_weight_total = float(
                sum(HOLY_GRAIL_COMPONENT_WEIGHTS[name] for name in available_components)
            )
            for component_name in available_components:
                effective_weights[component_name] = (
                    HOLY_GRAIL_COMPONENT_WEIGHTS[component_name] / raw_weight_total * 100.0
                )
            holy_grail_score = float(
                sum(
                    component_scores[component_name]
                    * effective_weights[component_name]
                    / 100.0
                    for component_name in available_components
                )
            )
        else:
            holy_grail_score = math.nan

        rounded_score = round(float(holy_grail_score), 2) if not pd.isna(holy_grail_score) else math.nan
        red_flags = self._build_red_flags(
            latest_primary=latest_primary,
            primary_rows=primary_rows,
            layer_a_trc_rolling=layer_a_trc_rolling,
            robustness_stats=robustness_stats,
            macro_metrics=latest_macro_metrics,
            layer_b_enabled=layer_b_enabled,
        )
        red_flags_table = pd.DataFrame(
            red_flags,
            columns=["code", "severity", "message", "value", "threshold", "context"],
        )

        scorecard_rows = []
        component_order = ["independence", "balance", "robustness", "macro"]
        for component_name in component_order:
            component_score = component_scores[component_name]
            effective_weight = float(effective_weights.get(component_name, 0.0))
            weighted_score = (
                float(component_score) * effective_weight / 100.0
                if not pd.isna(component_score) and effective_weight > 0
                else math.nan
            )
            scorecard_rows.append(
                {
                    "component": component_name,
                    "available": component_name in available_components,
                    "score": component_score,
                    "weight_pct_raw": HOLY_GRAIL_COMPONENT_WEIGHTS[component_name],
                    "weight_pct_effective": effective_weight,
                    "weighted_score": weighted_score,
                }
            )
        scorecard_rows.append(
            {
                "component": "total",
                "available": True,
                "score": rounded_score,
                "weight_pct_raw": 100.0,
                "weight_pct_effective": 100.0,
                "weighted_score": rounded_score,
            }
        )
        scorecard = pd.DataFrame(scorecard_rows)

        verdict = {
            "holy_grail_score": rounded_score,
            "holy_grail_class": self._holy_grail_class(rounded_score),
            "macro_policy": "renormalize",
            "macro_available": macro_available,
            "component_scores": {
                component_name: (
                    round(float(component_scores[component_name]), 2)
                    if not pd.isna(component_scores[component_name])
                    else math.nan
                )
                for component_name in component_order
            },
            "component_weight_pct": dict(HOLY_GRAIL_COMPONENT_WEIGHTS),
            "effective_component_weight_pct": effective_weights,
            "latest_metrics": latest_metrics,
            "robustness_summary": {
                "median_composite": median_composite,
                "tail_composite": tail_composite,
                "robustness_score": robustness_score,
            },
            "macro_metrics_latest": latest_macro_metrics,
            "red_flag_count": int(len(red_flags)),
            "red_flags": red_flags,
        }
        return verdict, scorecard, robustness_table, red_flags_table


def format_holy_grail_cli_lines(
    verdict: Dict[str, object], max_red_flags: int = 3
) -> list[str]:
    score = verdict.get("holy_grail_score", math.nan)
    score_class = str(verdict.get("holy_grail_class", "Unavailable"))
    if pd.isna(score):
        score_line = f"Holy Grail score: n/a ({score_class})"
    else:
        score_line = f"Holy Grail score: {float(score):.2f} ({score_class})"

    component_scores = verdict.get("component_scores", {})
    component_line = (
        "Component scores: "
        "independence={independence}, balance={balance}, robustness={robustness}, macro={macro}".format(
            independence=_format_score_value(component_scores.get("independence", math.nan)),
            balance=_format_score_value(component_scores.get("balance", math.nan)),
            robustness=_format_score_value(component_scores.get("robustness", math.nan)),
            macro=_format_score_value(component_scores.get("macro", math.nan)),
        )
    )

    flags = verdict.get("red_flags", [])
    if isinstance(flags, list) and flags:
        lines = [score_line, component_line, "Red flags:"]
        for flag in flags[: max_red_flags]:
            code = str(flag.get("code", "UNKNOWN"))
            severity = str(flag.get("severity", "INFO"))
            message = str(flag.get("message", ""))
            lines.append(f"- [{severity}] {code}: {message}")
        return lines
    return [score_line, component_line, "Red flags: none"]


def _format_score_value(value: object) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):.2f}"


def _parse_fx_rates(fx_args: Optional[list[str]]) -> Dict[str, float]:
    if not fx_args:
        return {}
    rates = {}
    for item in fx_args:
        if "=" not in item:
            raise ValueError(f"Invalid --fx value: {item}. Expected format CURRENCY=RATE.")
        currency, rate = item.split("=", 1)
        rates[currency.strip().upper()] = float(rate.strip())
    return rates


def _parse_target_weights(raw_weights: Optional[str]) -> Optional[Dict[str, float]]:
    if not raw_weights:
        return None
    parsed = json.loads(raw_weights)
    if not isinstance(parsed, dict):
        raise ValueError("--target-weights must be a JSON object.")
    return {str(k): float(v) for k, v in parsed.items()}


def _parse_layer_a_windows(raw_windows: str) -> tuple[int, ...]:
    windows = []
    for token in raw_windows.split(","):
        token = token.strip()
        if not token:
            continue
        windows.append(int(token))
    if not windows:
        raise ValueError("Layer A windows must contain at least one integer.")
    unique = sorted({window for window in windows if window > 0})
    if not unique:
        raise ValueError("Layer A windows must be positive integers.")
    return tuple(unique)


def _load_fx_history(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    fx_history = pd.read_csv(path)
    if "fx_rate_to_base" not in fx_history.columns:
        if "fx_rate" in fx_history.columns:
            fx_history = fx_history.rename(columns={"fx_rate": "fx_rate_to_base"})
        else:
            raise ValueError(
                "FX history file must contain 'fx_rate_to_base' "
                "(or 'fx_rate') column."
            )
    return fx_history


def _load_factor_returns(path: Optional[str]) -> Optional[pd.DataFrame]:
    if not path:
        return None
    return pd.read_csv(path)


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dalio Holy Grail portfolio analyzer (8-12 uncorrelated risk sources)."
    )
    parser.add_argument("--input", required=True, help="Path to historical portfolio CSV.")
    parser.add_argument(
        "--output-dir",
        default="analytics/output",
        help="Directory where result tables will be saved as CSV.",
    )
    parser.add_argument(
        "--base-currency",
        default="USD",
        help="Base currency used for normalization.",
    )
    parser.add_argument(
        "--fx",
        action="append",
        help="Currency conversion rate to base currency, e.g. --fx EUR=1.08",
    )
    parser.add_argument(
        "--fx-file",
        default=None,
        help=(
            "Optional CSV with dated FX rates. Required columns: "
            "date,currency,fx_rate_to_base."
        ),
    )
    parser.add_argument(
        "--target-weights",
        default=None,
        help="JSON object for target weights, e.g. '{\"Stocks\":35,\"Bonds\":20}'.",
    )
    parser.add_argument(
        "--corr-threshold",
        type=float,
        default=0.6,
        help="Absolute correlation threshold for risk-source overlap.",
    )
    parser.add_argument(
        "--max-risk-contribution",
        type=float,
        default=0.25,
        help="Max risk contribution per bucket (fraction, e.g. 0.25 = 25 percent).",
    )
    parser.add_argument(
        "--drift-threshold",
        type=float,
        default=0.20,
        help="Allowed weight drift from target before rebalance flag.",
    )
    parser.add_argument(
        "--return-unit",
        choices=["decimal", "percent"],
        default="decimal",
        help="Input unit for return_pct column.",
    )
    parser.add_argument(
        "--return-type",
        choices=["simple", "log"],
        default="simple",
        help="Return transformation used for analysis.",
    )
    parser.add_argument(
        "--analysis-frequency",
        choices=["auto", "daily", "monthly"],
        default="auto",
        help="Analysis frequency. 'auto' detects daily vs monthly from date spacing.",
    )
    parser.add_argument(
        "--allow-partial-scenarios",
        action="store_true",
        help=(
            "Allow missing bucket shocks in scenario table. "
            "Without this flag, missing shocks raise an error."
        ),
    )
    parser.add_argument(
        "--allow-unmapped-factors",
        action="store_true",
        help=(
            "Allow asset buckets missing from factor_map. "
            "By default unmapped buckets raise an error."
        ),
    )
    parser.add_argument(
        "--allow-shorts",
        action="store_true",
        help=(
            "Allow negative market values/weights. "
            "By default short exposure fails quality checks."
        ),
    )
    parser.add_argument(
        "--max-gross-leverage",
        type=float,
        default=1.05,
        help="Maximum allowed gross leverage ratio (gross/net).",
    )
    parser.add_argument(
        "--min-net-to-gross",
        type=float,
        default=0.60,
        help="Minimum allowed net/gross ratio to limit excessive netting.",
    )
    parser.add_argument(
        "--covariance-method",
        choices=["ledoit-wolf", "sample", "ewma"],
        default="ledoit-wolf",
        help="Covariance estimator for risk contribution and volatility.",
    )
    parser.add_argument(
        "--ewma-alpha",
        type=float,
        default=0.06,
        help="EWMA decay alpha (used when --covariance-method ewma).",
    )
    parser.add_argument(
        "--min-pair-overlap",
        type=int,
        default=24,
        help="Minimum overlapping observations for HIGH confidence pairwise stats.",
    )
    parser.add_argument(
        "--min-asset-coverage-pct",
        type=float,
        default=80.0,
        help="Minimum per-asset coverage required for covariance inclusion.",
    )
    parser.add_argument(
        "--covariance-window",
        type=int,
        default=None,
        help=(
            "Optional trailing observation window for covariance estimation. "
            "Defaults to 252 for daily and full history for monthly."
        ),
    )
    parser.add_argument(
        "--factor-input-csv",
        default=None,
        help=(
            "Optional wide CSV with factor returns. Required columns: "
            "date,growth,inflation,real_rates,credit_liquidity."
        ),
    )
    parser.add_argument(
        "--layer-b-window-months",
        type=int,
        default=36,
        help="Rolling window size (months) for Layer B factor modeling.",
    )
    parser.add_argument(
        "--layer-b-min-observations",
        type=int,
        default=24,
        help="Minimum aligned observations needed for Layer B OLS.",
    )
    parser.add_argument(
        "--layer-b-require-data",
        action="store_true",
        help="Require factor input CSV and fail if Layer B cannot run.",
    )
    parser.add_argument(
        "--layer-b-collinearity-cond-threshold",
        type=float,
        default=30.0,
        help="Condition number threshold for Layer B collinearity flag.",
    )
    parser.add_argument(
        "--layer-b-vif-threshold",
        type=float,
        default=10.0,
        help="VIF threshold for Layer B collinearity flag.",
    )
    parser.add_argument(
        "--layer-b-max-factor-trc-share",
        type=float,
        default=0.35,
        help="Alert threshold for max factor TRC share (fraction).",
    )
    parser.add_argument(
        "--layer-b-factor-hhi-threshold",
        type=float,
        default=0.35,
        help="Alert threshold for factor HHI concentration.",
    )
    parser.add_argument(
        "--layer-b-residual-share-threshold",
        type=float,
        default=0.40,
        help="Alert threshold for residual risk share (fraction).",
    )
    parser.add_argument(
        "--layer-b-min-coverage-pct",
        type=float,
        default=80.0,
        help="Alert threshold for minimum factor coverage percentage.",
    )
    parser.add_argument(
        "--layer-a-windows",
        default="12,24,36",
        help="Comma-separated rolling windows (months) for Layer A metrics.",
    )
    parser.add_argument(
        "--layer-a-high-corr-threshold",
        type=float,
        default=0.70,
        help="Pair-level absolute correlation threshold used in Layer A metrics.",
    )
    parser.add_argument(
        "--layer-a-cluster-corr-cutoff",
        type=float,
        default=0.70,
        help="Correlation cutoff for NumPy HAC clustering in Layer A.",
    )
    parser.add_argument(
        "--layer-a-trc-max-share",
        type=float,
        default=0.35,
        help="Maximum allowed absolute TRC share (fraction) before Layer A alert.",
    )
    parser.add_argument(
        "--layer-a-min-n-rc",
        type=float,
        default=4.0,
        help="Minimum effective number of risk contributors before Layer A alert.",
    )
    parser.add_argument(
        "--layer-a-primary-window",
        type=int,
        default=36,
        help="Primary Layer A rolling window used for summary alerts.",
    )
    return parser


def main() -> int:
    parser = _build_cli()
    args = parser.parse_args()

    dataset = pd.read_csv(args.input)
    analyzer = DalioHolyGrailAnalyzer(
        dataset,
        base_currency=args.base_currency,
        fx_rates=_parse_fx_rates(args.fx),
        fx_history=_load_fx_history(args.fx_file),
        factor_returns=_load_factor_returns(args.factor_input_csv),
        return_unit=args.return_unit,
        return_type=args.return_type,
        analysis_frequency=args.analysis_frequency,
        allow_partial_scenarios=args.allow_partial_scenarios,
        allow_unmapped_factors=args.allow_unmapped_factors,
        allow_shorts=args.allow_shorts,
        max_gross_leverage=args.max_gross_leverage,
        min_net_to_gross=args.min_net_to_gross,
        covariance_method=args.covariance_method,
        ewma_alpha=args.ewma_alpha,
        min_pair_overlap=args.min_pair_overlap,
        min_asset_coverage_pct=args.min_asset_coverage_pct,
        covariance_window=args.covariance_window,
        layer_b_window_months=args.layer_b_window_months,
        layer_b_min_observations=args.layer_b_min_observations,
        layer_b_require_data=args.layer_b_require_data,
        layer_b_collinearity_cond_threshold=args.layer_b_collinearity_cond_threshold,
        layer_b_vif_threshold=args.layer_b_vif_threshold,
        layer_b_max_factor_trc_share=args.layer_b_max_factor_trc_share,
        layer_b_factor_hhi_threshold=args.layer_b_factor_hhi_threshold,
        layer_b_residual_share_threshold=args.layer_b_residual_share_threshold,
        layer_b_min_coverage_pct=args.layer_b_min_coverage_pct,
        layer_a_windows=_parse_layer_a_windows(args.layer_a_windows),
        layer_a_high_corr_threshold=args.layer_a_high_corr_threshold,
        layer_a_cluster_corr_cutoff=args.layer_a_cluster_corr_cutoff,
        layer_a_trc_max_share_threshold=args.layer_a_trc_max_share,
        layer_a_min_n_rc=args.layer_a_min_n_rc,
        layer_a_primary_window=args.layer_a_primary_window,
    )
    result = analyzer.run_analysis(
        corr_threshold=args.corr_threshold,
        max_risk_contribution=args.max_risk_contribution,
        target_weights=_parse_target_weights(args.target_weights),
        drift_threshold=args.drift_threshold,
    )
    analyzer.save_result_tables(result, args.output_dir)

    print("Analysis complete.")
    print("Diversification metrics:", result.diversification_metrics)
    print("Management rules:", result.management_rules)
    for line in format_holy_grail_cli_lines(result.holy_grail_verdict, max_red_flags=3):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
