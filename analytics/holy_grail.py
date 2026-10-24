"""Pure, versioned progress toward risk-balanced independent return streams.

This is a statistical model, not Dalio's proprietary methodology or a forecast.
Collection and output adapters must not recalculate its saved results.
"""
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math

import numpy as np
import pandas as pd

from analytics.dalio_holy_grail import (
    correlation_clusters,
    portfolio_variance_contributions,
)

METHOD_VERSION = "holy_grail_progress_v1"
TARGET_STREAMS = 15


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def holdings_fingerprint(data):
    """Identify saved financial inputs without including the derived metric."""
    keys = ("IB_DATA", "CRYPTO_DATA", "POSITION_DATA", "CASH_DATA", "TOTAL_ASSETS",
            "FIXED_INCOME_DATA", "OTHER_ASSETS", "DATA_QUALITY")
    def normalize(value, numeric_strings=False):
        # final_data serializes Decimal as text; dated snapshots use floats.
        # Instrument identifiers remain strings even when they look numeric.
        if isinstance(value, dict):
            return {key: normalize(item, numeric_strings) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [normalize(item, numeric_strings) for item in value]
        if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
            return float(value)
        if numeric_strings and isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        return value
    return fingerprint({key: normalize(data.get(key), key == "CASH_DATA") for key in keys})


def completed_month_end(as_of_date):
    stamp = pd.Timestamp(as_of_date).normalize()
    month = stamp.to_period("M")
    if stamp != month.end_time.normalize():
        month -= 1
    return month.end_time.normalize()


def qualification_reviewed(record):
    required = ("rationale", "costs", "principal_risks", "reviewer", "reviewed_at")
    if not isinstance(record, dict) or record.get("status") != "reviewed":
        return False
    if not all(isinstance(record.get(key), str) and record[key].strip() for key in required):
        return False
    try:
        datetime.fromisoformat(record["reviewed_at"])
    except ValueError:
        return False
    return True


def _statistics(frame, values):
    covariance = frame.cov().to_numpy(dtype=float)
    sigma = np.sqrt(np.diag(covariance))
    if not np.isfinite(covariance).all() or (sigma <= 0).any():
        return None
    weights = np.asarray(values, dtype=float)
    variance, contributions = portfolio_variance_contributions(weights, covariance)
    gross_risk = float((np.abs(weights) * sigma).sum())
    if variance <= gross_risk ** 2 * 1e-12:
        return None
    risk_total = float(np.abs(contributions).sum())
    if risk_total <= 0:
        return None
    shares = np.abs(contributions) / risk_total
    correlation = covariance / np.outer(sigma, sigma)
    correlation = np.clip(correlation, -1.0, 1.0)
    effective = float(1.0 / (shares @ np.square(correlation) @ shares))
    clusters = correlation_clusters(pd.DataFrame(correlation, index=frame.columns, columns=frame.columns))
    cluster_risk = pd.Series(shares, index=frame.columns).groupby(clusters).sum()
    return {
        "effective_streams": effective,
        "max_cluster_risk_share_pct": float(cluster_risk.max() * 100),
        "cluster_count": int(len(cluster_risk)),
        "risk_shares": dict(zip(frame.columns, (shares * 100).tolist())),
        "diversification_ratio": float(gross_risk / math.sqrt(variance)),
    }


def calculate_progress(exposures, monthly_returns, *, as_of_date, total_assets,
                       cash_value=0.0, input_flags=(), config_hash="", generated_at=None):
    """Calculate a JSON-safe summary from dated holdings and monthly USD returns.

    Exposure dictionaries carry id, series, value_usd, category, kind,
    weak_proxy and qualification. Missing exposures remain in coverage totals.
    Identical series are aggregated before estimating risk.
    """
    cutoff = completed_month_end(as_of_date)
    flags = set(input_flags)
    result = {
        "method_version": METHOD_VERSION, "as_of_date": str(as_of_date),
        "calculated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "return_window_start": None, "return_window_end": None,
        "observation_count": 0, "effective_streams": None,
        "estimated_progress_pct": None, "target_streams": TARGET_STREAMS,
        "target_range": [15, 20], "target_achieved": False,
        "qualification_status": "pending", "status": "unavailable",
        "scope": "covered_subset", "modeled": any(e.get("kind") == "proxy" for e in exposures),
        "coverage": {"direct_pct": 0.0, "proxy_pct": 0.0, "uncovered_pct": 0.0, "cash_pct": 0.0},
        "concentration": {}, "stability": {}, "constraints": [],
        "input_fingerprint": None,
        "configuration_fingerprint": config_hash,
    }
    if not math.isfinite(float(total_assets)) or total_assets <= 0:
        result["constraints"] = ["invalid_portfolio_total"]
        return result
    total_assets, cash_value = float(total_assets), float(cash_value)
    try:
        values = [float(e["value_usd"]) for e in exposures]
    except (ValueError, TypeError, KeyError):
        values = [math.nan]
    if not all(math.isfinite(v) and v >= 0 for v in values) or not math.isfinite(cash_value) or cash_value < 0:
        result["constraints"] = ["invalid_or_short_exposure"]
        return result
    result["input_fingerprint"] = fingerprint({"exposures": exposures, "as_of_date": as_of_date})
    # DataSource truncates TOTAL_ASSETS to whole USD; components retain cents.
    if abs(sum(values) + cash_value - total_assets) > max(1.0, total_assets * 1e-6):
        flags.add("unreconciled_valuations")
    coverage = result["coverage"]
    coverage["cash_pct"] = cash_value / total_assets * 100
    active = [e for e in exposures if e["value_usd"] > 0]
    if not active and abs(cash_value - total_assets) <= 0.02:
        result.update(effective_streams=0.0, estimated_progress_pct=0.0, status="available",
                      scope="whole_portfolio", qualification_status="not_applicable")
        result["constraints"] = sorted(flags | {"cash_has_no_independent_streams"})
        return result

    frame = monthly_returns.copy()
    frame.index = pd.to_datetime(frame.index).tz_localize(None).normalize()
    if frame.index.has_duplicates or not frame.index.is_month_end.all():
        flags.add("invalid_monthly_history")
        frame = pd.DataFrame()
    else:
        frame = frame.loc[frame.index <= cutoff].sort_index()
        # Restrict the calendar window, not merely the number of nonmissing rows.
        frame = frame.loc[frame.index.to_period("M") >= cutoff.to_period("M") - 59]
        frame = frame.apply(pd.to_numeric, errors="coerce").replace([np.inf, -np.inf], np.nan)

    grouped = {}
    for exposure in active:
        series = exposure.get("series")
        eligible = (series in frame.columns and frame[series].notna().sum() >= 36
                    and frame[series].dropna().std() > 0)
        kind = exposure.get("kind", "direct")
        if eligible:
            coverage["proxy_pct" if kind == "proxy" else "direct_pct"] += exposure["value_usd"] / total_assets * 100
            grouped[series] = grouped.get(series, 0.0) + exposure["value_usd"]
        else:
            coverage["uncovered_pct"] += exposure["value_usd"] / total_assets * 100
        if not qualification_reviewed(exposure.get("qualification")):
            flags.add("qualification_pending")
        if exposure.get("weak_proxy"):
            flags.add("weak_proxy")
        flags.update(exposure.get("risk_flags", []))
    for key in coverage:
        coverage[key] = round(coverage[key], 10)
    if coverage["uncovered_pct"] > 1e-8:
        flags.add("uncovered_exposures")
    else:
        result["scope"] = "whole_portfolio"
    result["qualification_status"] = "pending" if "qualification_pending" in flags else "reviewed"
    if not grouped:
        result["constraints"] = sorted(flags | {"insufficient_history"})
        return result
    aligned = frame[list(grouped)].dropna()
    result["observation_count"] = len(aligned)
    if len(aligned) < 36:
        result["constraints"] = sorted(flags | {"insufficient_common_history"})
        return result
    if aligned.index[-1] != cutoff:
        flags.add("stale_return_history")
    if len(aligned) < 60:
        flags.add("short_history")
    statistics = _statistics(aligned, list(grouped.values()))
    recent_frame = aligned.loc[aligned.index.to_period("M") >= cutoff.to_period("M") - 35]
    recent = _statistics(recent_frame, list(grouped.values())) if len(recent_frame) == 36 else None
    if statistics is None:
        result["constraints"] = sorted(flags | {"degenerate_covariance"})
        return result
    count = statistics["effective_streams"]
    stability_ratio = recent["effective_streams"] / count if recent else None
    if statistics["max_cluster_risk_share_pct"] > 10.0 + 1e-9:
        flags.add("risk_concentration")
    if stability_ratio is None:
        flags.add("insufficient_recent_history")
    elif stability_ratio < 0.75:
        flags.add("unstable_diversification")
    result.update(
        return_window_start=aligned.index[0].date().isoformat(),
        return_window_end=aligned.index[-1].date().isoformat(),
        effective_streams=count,
        estimated_progress_pct=min(100.0, 100.0 * count / TARGET_STREAMS),
        concentration=statistics,
        stability={"recent_36m_effective_streams": recent["effective_streams"] if recent else None, "ratio": stability_ratio},
        target_achieved=bool(count >= TARGET_STREAMS - 1e-9 and not flags),
        status="provisional" if flags else "available",
        constraints=sorted(flags),
    )
    return result


CONSTRAINT_LABELS = {
    "qualification_pending": "Очікувана дохідність після витрат ще потребує перевірки.",
    "weak_proxy": "Проксі лише частково відображають ризики фактичних інвестицій.",
    "uncovered_exposures": "Частина портфеля не має придатної історії дохідностей.",
    "insufficient_history": "Немає достатньої історії дохідностей.",
    "insufficient_common_history": "Потрібно щонайменше 36 спільних місячних спостережень.",
    "short_history": "Для підтвердження цілі потрібно 60 спільних місячних спостережень.",
    "risk_concentration": "Один спільний кластер перевищує 10% ризику портфеля.",
    "unstable_diversification": "Диверсифікація за останні 36 місяців погіршилася.",
    "stale_return_history": "Історія не охоплює останній завершений місяць.",
    "partial_valuations": "Частина оцінок активів має неповне підтвердження.",
    "unreconciled_valuations": "Оцінки позицій не узгоджені із загальною вартістю портфеля.",
    "unreconciled_positions": "Не всі активи розкладені на окремі позиції.",
    "valuation_date_mismatch": "Дати вихідних оцінок активів відрізняються.",
    "valuation_date_unverified": "Дата вихідних оцінок активів не підтверджена.",
    "stale_valuations": "Частина балансів відновлена із застарілих або неповних даних.",
    "insufficient_recent_history": "Не вистачає даних за останні 36 календарних місяців.",
    "counterparty_risk_unmodeled": "Кредитний ризик окремих контрагентів не виміряний повністю.",
    "liquidity_risk_unmodeled": "Обмеження виведення коштів не відображені ринковою історією.",
    "depeg_risk_unmodeled": "Проксі не відображає можливу втрату прив'язки стейблкоїнів.",
    "resale_execution_risk_unmodeled": "Індекс цін не вимірює прибутковість операцій перепродажу.",
    "local_market_risk_unmodeled": "Ризики місцевого ринку відрізняються від індексного проксі.",
    "cash_equivalent_counterparty_risk": "Еквіваленти кешу зберігають ризик емітента або платформи.",
    "history_collection_incomplete": "Частина ринкових даних недоступна.",
    "publication_vintage_unverified": "Для економічних рядів не підтверджена початкова дата публікації.",
    "cash_has_no_independent_streams": "Кеш не додає незалежних джерел інвестиційної дохідності.",
    "degenerate_covariance": "За цією історією неможливо надійно оцінити ризик.",
}


def saved_progress_view(data, expected_date=None):
    """A privacy-safe shared display contract; no collection or risk calculation."""
    data = data.get("data", data)
    metric = data.get("HOLY_GRAIL_DATA")
    unavailable = {"headline": "Дані недоступні", "fraction": None, "effective": "-",
                   "as_of": "-", "status": "Немає збереженої оцінки", "sheet_status": "Дані недоступні",
                   "rows": [], "coverage_text": "-"}
    expected = expected_date or str(data.get("DATA_METADATA", {}).get("last_updated")
                                    or data.get("POSITION_DATA", {}).get("as_of_date") or "")[:10]
    if not isinstance(metric, dict) or metric.get("method_version") != METHOD_VERSION:
        return unavailable
    try:
        if expected and metric.get("as_of_date") != expected:
            return dict(unavailable, status="Оцінка не відповідає даті портфеля")
        if metric.get("holdings_fingerprint") != holdings_fingerprint(data):
            return dict(unavailable, status="Оцінка не відповідає складу портфеля")
        stamp = datetime.fromisoformat(metric["as_of_date"]).strftime("%d.%m.%Y")
        raw = metric.get("estimated_progress_pct")
        count = metric.get("effective_streams")
        if raw is not None and (not math.isfinite(float(raw)) or not 0 <= raw <= 100):
            return unavailable
        if count is not None and (not math.isfinite(float(count)) or count < 0):
            return unavailable
    except (ValueError, TypeError, KeyError):
        return unavailable
    achieved = metric.get("target_achieved") is True and not metric.get("constraints")
    blocked_target = raw is not None and raw >= 100 - 1e-8 and not achieved
    displayed = min(raw, 99.9) if raw is not None and not achieved else raw
    pct = lambda value: "-" if value is None else f"{float(value):.1f}%".replace(".", ",")
    headline = ("Ціль не підтверджена" if blocked_target else
                pct(displayed) if displayed is not None else "Недостатньо даних")
    status = "Ціль досягнута за моделлю" if achieved else "Попередня оцінка"
    if metric.get("modeled"):
        status += " - з використанням проксі"
    if metric.get("scope") == "covered_subset":
        status += " - лише покрита частина портфеля"
    if metric.get("retrospective"):
        status += " - ретроспективний розрахунок"
    coverage = metric.get("coverage", {})
    concentration = metric.get("concentration", {})
    stability = metric.get("stability", {})
    count_text = "-" if count is None else f"{count:.2f}".replace(".", ",")
    rows = [
        ("Ефективні джерела дохідності", count_text), ("Ціль", "15-20"),
        ("Дата оцінки", stamp), ("Статус оцінки", status),
        ("Період дохідностей", f"{metric.get('return_window_start') or '-'} - {metric.get('return_window_end') or '-'}"),
        ("Місячних спостережень", str(metric.get("observation_count", 0))),
        ("Прямі дані / проксі / без історії", " / ".join(pct(coverage.get(key)) for key in ("direct_pct", "proxy_pct", "uncovered_pct"))),
        ("Частка кешу", pct(coverage.get("cash_pct"))),
        ("Найбільший кластер ризику", pct(concentration.get("max_cluster_risk_share_pct"))),
        ("Збереження диверсифікації за 36 міс.", pct(stability.get("ratio") * 100 if stability.get("ratio") is not None else None)),
        ("Статистична оцінка прогресу", pct(raw)),
    ]
    if coverage.get("cash_pct", 0) > 0:
        rows.append(("Ризики кешу", "Валютний ризик залежить від валюти кешу; депозити й стейблкоїни зберігають ризики контрагента та втрати прив'язки. Ці ризики не створюють додаткових джерел."))
    constraints = [CONSTRAINT_LABELS.get(code, "Потрібна перевірка вихідних даних.") for code in metric.get("constraints", [])]
    rows.extend(("Обмеження", label) for label in dict.fromkeys(constraints))
    return {"headline": headline, "fraction": None if blocked_target or displayed is None else displayed / 100,
            "effective": count_text, "as_of": stamp, "status": status, "rows": rows,
            "sheet_status": "Ціль досягнута за моделлю" if achieved else
                            "Попередня · частина" if metric.get("scope") == "covered_subset" else "Попередня оцінка",
            "coverage_text": pct(coverage.get("proxy_pct")) + " / " + pct(coverage.get("uncovered_pct"))}
