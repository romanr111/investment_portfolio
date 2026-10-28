"""Fingerprints and historical progress views for saved portfolio records."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import math

import pandas as pd

METHOD_VERSION = "holy_grail_progress_v1"


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


CONSTRAINT_LABELS = {
    "unsupported_borrowing": "Виявлено позиковий залишок; модель не підтримує оцінку з кредитним плечем.",
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
