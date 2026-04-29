"""Normalize heterogeneous Korean/English rating strings to BUY / HOLD / SELL."""
from typing import Dict, Optional

_RATING_MAP: Dict[str, str] = {
    # Korean
    "강력매수": "BUY",
    "적극매수": "BUY",
    "매수": "BUY",
    "시장수익률상회": "BUY",
    "보유": "HOLD",
    "중립": "HOLD",
    "시장수익률": "HOLD",
    "매도": "SELL",
    "시장수익률하회": "SELL",
    # English
    "buy": "BUY",
    "strong buy": "BUY",
    "outperform": "BUY",
    "overweight": "BUY",
    "market outperform": "BUY",
    "hold": "HOLD",
    "neutral": "HOLD",
    "market perform": "HOLD",
    "equal weight": "HOLD",
    "sell": "SELL",
    "underperform": "SELL",
    "underweight": "SELL",
    "reduce": "SELL",
}


def normalize_rating(raw: Optional[str]) -> str:
    if not raw:
        return "UNKNOWN"
    key = raw.strip()
    return _RATING_MAP.get(key) or _RATING_MAP.get(key.lower(), "UNKNOWN")
