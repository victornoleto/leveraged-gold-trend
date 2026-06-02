"""Transaction-cost model for XAUUSD.

Fractions of traded notional. Defaults are a tight-spread retail/ECN gold quote: ~0.2 bps
commission + ~1 bps spread per side. ``round_trip_cost`` is charged on turnover (|Δexposure|).

NOTE — overnight carry (``SWAP``) is intentionally NOT charged in the returns model. For a
multi-day-holding system this UNDERSTATES the true cost; treat the headline as a slightly
optimistic upper bound and read the cost-stress columns (1×/2×/3×). See README "Limitations".
"""

from __future__ import annotations

FEES = 0.00002      # ~0.2 bps commission per side
SLIPPAGE = 0.0001   # ~1 bps spread/slippage per side
SWAP = 0.00003      # ~daily overnight carry — documented, NOT applied (see note above)


def round_trip_cost(mult: float = 1.0) -> float:
    """Cost charged per unit of turnover (fees + slippage), optionally stress-scaled by ``mult``."""
    return (FEES + SLIPPAGE) * mult
