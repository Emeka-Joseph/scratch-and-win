from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app


def tz():
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def to_local(dt):
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(tz())


def fmt_dt(dt, fmt="%d %b %Y, %H:%M"):
    local = to_local(dt)
    return local.strftime(fmt) if local else "—"


def local_to_utc(dt):
    """Naive local datetime (from a form) -> naive UTC for storage."""
    if dt is None:
        return None
    return dt.replace(tzinfo=tz()).astimezone(timezone.utc).replace(tzinfo=None)


def local_day_bounds_utc(days_back=0):
    """UTC start/end of a local calendar day."""
    now_local = datetime.now(tz())
    start = (now_local - timedelta(days=days_back)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    conv = lambda d: d.astimezone(timezone.utc).replace(tzinfo=None)  # noqa: E731
    return conv(start), conv(end)
