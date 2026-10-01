import pytest
from datetime import datetime, timezone
import pytz
from core.timezone_resolver import TimezoneResolver

def test_timezone_resolution_valid_coords():
    """Verifies GPS coordinate lookup converts UTC to expected local timezone (Rome, Europe/Rome)."""
    # 2021-05-03 12:00:00 UTC
    utc_ts = 1620043200.0
    # Coordinates of Colosseum in Rome (UTC+2 in May daylight saving)
    lat, lon = 41.8902, 12.4922
    
    local_dt = TimezoneResolver.get_local_timestamp(utc_ts, lat, lon)
    assert local_dt is not None
    # Europe/Rome is UTC+2 in May
    assert local_dt.hour == 14
    assert local_dt.tzinfo.zone == "Europe/Rome"

def test_timezone_resolution_none_coords():
    """Verifies that missing (None) coordinates gracefully fall back to UTC."""
    utc_ts = 1620043200.0
    local_dt = TimezoneResolver.get_local_timestamp(utc_ts, None, None)
    assert local_dt is not None
    assert local_dt.hour == 12

def test_timezone_resolution_invalid_coords():
    """Verifies invalid coordinates (e.g. out of range) gracefully fall back to UTC."""
    utc_ts = 1620043200.0
    local_dt = TimezoneResolver.get_local_timestamp(utc_ts, 999.0, 999.0)
    assert local_dt is not None
    assert local_dt.hour == 12
