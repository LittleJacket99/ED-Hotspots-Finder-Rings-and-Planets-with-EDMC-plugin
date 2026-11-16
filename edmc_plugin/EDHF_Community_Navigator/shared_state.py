"""Presentation only: the Worker alone decides Community Deposits state."""
from datetime import datetime, timezone, date
import re


def shared_state_display(record, now=None):
    shared = record.get("shared_state")
    if not isinstance(shared, dict) or shared.get("state") not in ("active", "depleted"):
        # Compatibility with the currently deployed pre-aggregation Worker.
        raw = record.get("depleted_at")
        shared = dict(state="depleted" if raw not in (None, "") else "active", at=raw,
                      source="legacy", quality="legacy", commander=None, conflict=False)
    state, original = shared["state"], shared.get("at")
    legacy = shared.get("quality") == "legacy"
    source = shared.get("source") or "unknown"
    owner = shared.get("commander")
    description = f"{source}" + (f" — {owner}" if owner else " — Commander unknown")
    if legacy:
        description += " (legacy)"
    if shared.get("conflict"):
        description += " — conflicting reports"
    if state == "active":
        return "Active", str(original or ""), description
    label = "Depleted"
    try:
        reference_now = now or datetime.now(timezone.utc)
        if isinstance(original, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", original):
            day = date.fromisoformat(original)
            if day <= reference_now.astimezone(timezone.utc).date():
                months = ("Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec")
                label += f" — {months[day.month-1]} {day.day}, {day.year}"
        elif isinstance(original, str):
            stamp = datetime.fromisoformat(original.replace("Z", "+00:00"))
            if stamp.utcoffset() is not None and stamp <= reference_now:
                days = (reference_now.astimezone(timezone.utc).date()-stamp.astimezone(timezone.utc).date()).days
                label += " — today" if days == 0 else f" — {days} day{'' if days == 1 else 's'} ago"
    except (ValueError, TypeError, OverflowError):
        pass
    return label, str(original or ""), description
