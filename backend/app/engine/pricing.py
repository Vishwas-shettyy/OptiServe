"""Instance prices and INR helpers. Pure: no I/O."""

import math
from typing import Optional

from app.engine.common import HOURS_PER_MONTH

# On-demand Linux USD/hour. Defaults, verify against the AWS pricing page (prices vary by region).
# Edit this table freely; users can also override the price per server in Settings.
PRICES_USD_HOUR: dict[str, float] = {
    "t2.micro": 0.0116,
    "t2.small": 0.023,
    "t2.medium": 0.0464,
    "t3.nano": 0.0052,
    "t3.micro": 0.0104,
    "t3.small": 0.0208,
    "t3.medium": 0.0416,
    "t3.large": 0.0832,
    "t3.xlarge": 0.1664,
    "t3a.micro": 0.0094,
    "t3a.small": 0.0188,
    "t3a.medium": 0.0376,
    "t3a.large": 0.0752,
    "t4g.micro": 0.0084,
    "t4g.small": 0.0168,
    "t4g.medium": 0.0336,
    "t4g.large": 0.0672,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m5.2xlarge": 0.384,
    "m6i.large": 0.096,
    "m6i.xlarge": 0.192,
    "m7g.large": 0.0816,
    "c5.large": 0.085,
    "c5.xlarge": 0.17,
    "c6i.large": 0.085,
    "c6i.xlarge": 0.17,
    "c7g.large": 0.0725,
    "r5.large": 0.126,
    "r6i.large": 0.126,
}


def hourly_usd(instance_type: Optional[str], override_usd: Optional[float] = None) -> Optional[float]:
    """Return the hourly USD price: the user's override first, then the table, else None."""
    if override_usd is not None and not (isinstance(override_usd, float) and math.isnan(override_usd)) and override_usd >= 0:
        return float(override_usd)
    if not instance_type:
        return None
    return PRICES_USD_HOUR.get(str(instance_type).strip().lower())


def usd_to_inr(usd: float, usd_inr: float) -> float:
    """Convert USD to INR at the configured rate."""
    return float(usd) * float(usd_inr)


def monthly_inr(hourly_usd_price: float, usd_inr: float, servers: float = 1.0) -> float:
    """Return the monthly INR cost of running `servers` machines at an hourly USD price."""
    return round(usd_to_inr(hourly_usd_price, usd_inr) * HOURS_PER_MONTH * float(servers), 2)


def format_inr(amount: float) -> str:
    """Format rupees with Indian digit grouping, e.g. 420000 → '₹4,20,000'."""
    sign = "-" if amount < 0 else ""
    digits = str(int(round(abs(float(amount)))))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        parts: list[str] = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        digits = ",".join(parts + [tail])
    return f"{sign}₹{digits}"
