"""
JSON Parser for Google Takeout sidecar files.
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

@dataclass
class ParsedMetadata:
    """Represents extracted metadata fields from a Google Takeout JSON sidecar."""
    title: Optional[str]
    description: Optional[str]
    taken_timestamp: Optional[float] # Unix timestamp
    latitude: Optional[float]
    longitude: Optional[float]
    altitude: Optional[float]

class JSONParser:
    @staticmethod
    def parse(json_path: Path) -> Optional[ParsedMetadata]:
        """Parses a Google Takeout JSON sidecar file."""
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Extract basic info
            title = data.get('title')
            description = data.get('description')
            
            # Extract timestamp
            taken_time = data.get('photoTakenTime')
            taken_timestamp = None
            if taken_time and 'timestamp' in taken_time:
                taken_timestamp = float(taken_time['timestamp'])
            
            # Extract GPS (prefer geoDataExif, fallback to geoData)
            geo_data = data.get('geoDataExif') or data.get('geoData')
            latitude = None
            longitude = None
            altitude = None
            
            if geo_data:
                latitude = geo_data.get('latitude')
                longitude = geo_data.get('longitude')
                altitude = geo_data.get('altitude')
                
            return ParsedMetadata(
                title=title,
                description=description,
                taken_timestamp=taken_timestamp,
                latitude=latitude,
                longitude=longitude,
                altitude=altitude
            )
        except Exception as e:
            logger.error(f"Failed to parse JSON {json_path}: {e}")
            return None