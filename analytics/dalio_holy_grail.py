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
    covariance_matrix: pd.DataFrame
    risk_contribution_by_bucket: pd.DataFrame
    factor_exposure: pd.DataFrame
    stress_test_results: pd.DataFrame
    quality_checks: pd.DataFrame
    high_correlation_pairs: pd.DataFrame
    pairwise_confidence: pd.DataFrame
    tail_risk_metrics: pd.DataFrame
    weight_drift: pd.DataFrame
    diversification_metrics: Dict[str, float]
    management_rules: Dict[str, object]

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
            "covariance_matrix": self.covariance_matrix,
            "risk_contribution_by_bucket": self.risk_contribution_by_bucket,
            "factor_exposure": self.factor_exposure,
            "stress_test_results": self.stress_test_results,
            "quality_checks": self.quality_checks,
            "high_correlation_pairs": self.high_correlation_pairs,
            "pairwise_confidence": self.pairwise_confidence,
            "tail_risk_metrics": self.tail_risk_metrics,
            "weight_drift": self.weight_drift,
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
        covariance_method: str = "sample",
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
        self.covariance_method = covariance_method
        self.ewma_alpha = ewma_alpha
        self.min_pair_overlap = min_pair_overlap
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
        correlation_matrix = returns_wide.corr(
            min_periods=self.min_covariance_observations
        )
        if self.covariance_method == "ewma":
            covariance_matrix = self._ewma_covariance(returns_wide, self.ewma_alpha)
        else:
            covariance_matrix = returns_wide.cov(
                min_periods=self.min_covariance_observations
            )
        rolling_correlation = self._rolling_pairwise_correlation(returns_wide, (12, 36))
        layer_b_outputs = self._layer_b_analysis(returns_wide, weights_by_date)
        pairwise_confidence = self._pairwise_confidence_flags(returns_wide)
        quality_checks = self._run_quality_checks(normalized, weights_by_date)
        latest_weights = self._latest_weights(weights_by_date)
        diversification_metrics = self._diversification_metrics(latest_weights)
        risk_contribution = self._risk_contribution_by_bucket(
            latest_weights, covariance_matrix
        )
        factor_exposure = self._factor_exposure(latest_weights, risk_contribution)
        tail_risk_metrics = self._tail_risk_metrics(returns_wide, weights_by_date)
        stress_test_results = self._stress_tests(latest_weights, weights_by_date)
        high_corr_pairs = self._high_correlation_pairs(correlation_matrix, corr_threshold)
        weight_drift = self._weight_drift(latest_weights, target_weights, drift_threshold)
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
            covariance_matrix=covariance_matrix,
            risk_contribution_by_bucket=risk_contribution,
            factor_exposure=factor_exposure,
            stress_test_results=stress_test_results,
            quality_checks=quality_checks,
            high_correlation_pairs=high_corr_pairs,
            pairwise_confidence=pairwise_confidence,
            tail_risk_metrics=tail_risk_metrics,
            weight_drift=weight_drift,
            diversification_metrics=diversification_metrics,
            management_rules=management_rules,
        )

    def save_result_tables(self, result: DalioAnalysisResult, output_dir: str) -> None:
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        for table_name, table in result.to_tables().items():
            table.to_csv(out_path / f"{table_name}.csv", index=True)

        summary = {
            "diversification_metrics": result.diversification_metrics,
            "management_rules": result.management_rules,
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
        aggregated["return_pct"] = aggregated["provided_return_pct"].combine_first(
            computed_returns
        )
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

    def _ewma_covariance(
        self, returns_wide: pd.DataFrame, alpha: float
    ) -> pd.DataFrame:
        if not 0 < alpha < 1:
            raise ValueError("ewma_alpha must be between 0 and 1.")

        assets = list(returns_wide.columns)
        covariance = pd.DataFrame(index=assets, columns=assets, dtype=float)
        for left_idx, left_asset in enumerate(assets):
            for right_idx, right_asset in enumerate(assets):
                pair = pd.concat(
                    [
                        returns_wide.iloc[:, left_idx],
                        returns_wide.iloc[:, right_idx],
                    ],
                    axis=1,
                ).dropna()
                if len(pair) < self.min_covariance_observations:
                    covariance.loc[left_asset, right_asset] = math.nan
                    continue

                left_values = pair.iloc[:, 0].values.astype(float)
                right_values = pair.iloc[:, 1].values.astype(float)
                count = len(pair)
                decay_weights = np.power(1.0 - alpha, np.arange(count - 1, -1, -1))
                decay_weights = decay_weights / decay_weights.sum()
                left_mean = float((left_values * decay_weights).sum())
                right_mean = float((right_values * decay_weights).sum())
                cov_value = float(
                    (
                        decay_weights
                        * (left_values - left_mean)
                        * (right_values - right_mean)
                    ).sum()
                )
                covariance.loc[left_asset, right_asset] = cov_value
        return covariance

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
        self, returns_wide: pd.DataFrame, weights_by_date: pd.DataFrame
    ) -> pd.DataFrame:
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

        rolling_peak_12m = cumulative.rolling(window=12, min_periods=1).max()
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
        }
        management_rules.update(layer_b_summary)
        return management_rules


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
        choices=["sample", "ewma"],
        default="sample",
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
        allow_partial_scenarios=args.allow_partial_scenarios,
        allow_unmapped_factors=args.allow_unmapped_factors,
        allow_shorts=args.allow_shorts,
        max_gross_leverage=args.max_gross_leverage,
        min_net_to_gross=args.min_net_to_gross,
        covariance_method=args.covariance_method,
        ewma_alpha=args.ewma_alpha,
        min_pair_overlap=args.min_pair_overlap,
        layer_b_window_months=args.layer_b_window_months,
        layer_b_min_observations=args.layer_b_min_observations,
        layer_b_require_data=args.layer_b_require_data,
        layer_b_collinearity_cond_threshold=args.layer_b_collinearity_cond_threshold,
        layer_b_vif_threshold=args.layer_b_vif_threshold,
        layer_b_max_factor_trc_share=args.layer_b_max_factor_trc_share,
        layer_b_factor_hhi_threshold=args.layer_b_factor_hhi_threshold,
        layer_b_residual_share_threshold=args.layer_b_residual_share_threshold,
        layer_b_min_coverage_pct=args.layer_b_min_coverage_pct,
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
