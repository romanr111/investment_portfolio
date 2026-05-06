from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class IBPosition:
    contractDesc: str
    mktValue: float
    position: float
    avgPrice: float
    mktPrice: float
    unrealizedPNL: float
    realizedPNL: Optional[float]
    currency: Optional[str]
    conId: Optional[int]
    secType: Optional[str]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IBPerformanceYTD:
    period: str = "YTD"
    rate_of_return_pct: Optional[float] = None
    measure: str = "TWR"
    source: str = "ib_flex_activity_statement"
    error: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
