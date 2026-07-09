"""
Timezone Resolver: Converts UTC timestamps to local time using GPS coordinates.
"""

import logging
from datetime import datetime
from typing import Optional
import pytz
from timezonefinder import TimezoneFinder

logger = logging.getLogger(__name__)

# Initialize once at module level to save memory/time
_tf = TimezoneFinder()

class TimezoneResolver:
    @staticmethod
    def get_local_timestamp(utc_timestamp: float, latitude: float, longitude: float) -> Optional[datetime]:
        """
        Converts a UTC unix timestamp to a localized datetime object 
        based on GPS coordinates.
        """
        try:
            tz_str = _tf.timezone_at(lat=latitude, lng=longitude)
            if not tz_str:
                logger.warning(f"Could not determine timezone for lat={latitude}, lon={longitude}")
                return datetime.fromtimestamp(utc_timestamp, tz=pytz.utc)
                
            local_tz = pytz.timezone(tz_str)
            utc_dt = datetime.fromtimestamp(utc_timestamp, tz=pytz.utc)
            return utc_dt.astimezone(local_tz)
            
        except Exception as e:
            logger.error(f"Timezone resolution failed: {e}")
            return datetime.fromtimestamp(utc_timestamp, tz=pytz.utc)