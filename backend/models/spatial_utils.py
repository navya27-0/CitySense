"""Spatial utilities for PostGIS geometry conversions and coordinates handling."""

from typing import Optional, Tuple
from geoalchemy2 import WKTElement
from geoalchemy2.shape import to_shape
from shapely.geometry import Point


def point_from_lat_lon(latitude: float, longitude: float) -> WKTElement:
    """Create a PostGIS WKT POINT geometry (EPSG:4326) from latitude and longitude.
    
    Note: Standard GIS coordinate order in WKT is (longitude latitude).
    """
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def lat_lon_from_point(geometry: Optional[object]) -> Tuple[Optional[float], Optional[float]]:
    """Extract (latitude, longitude) tuple from a GeoAlchemy2 geometry, WKT, or Shapely Point."""
    if geometry is None:
        return None, None
    try:
        # Check for WKTElement or objects with .data string
        data_val = getattr(geometry, "data", None)
        if isinstance(data_val, str) and "POINT" in data_val.upper():
            coords_str = data_val.upper().replace("POINT(", "").replace(")", "").strip()
            lon_str, lat_str = coords_str.split()
            return float(lat_str), float(lon_str)

        if isinstance(geometry, str) and "POINT" in geometry.upper():
            coords_str = geometry.upper().replace("POINT(", "").replace(")", "").strip()
            lon_str, lat_str = coords_str.split()
            return float(lat_str), float(lon_str)

        if isinstance(geometry, WKTElement):
            wkt_str = str(getattr(geometry, "data", geometry))
            coords_str = wkt_str.upper().replace("POINT(", "").replace(")", "").strip()
            lon_str, lat_str = coords_str.split()
            return float(lat_str), float(lon_str)
        
        # GeoAlchemy2 WKBElement or Shapely object
        shape = to_shape(geometry)
        if isinstance(shape, Point):
            return float(shape.y), float(shape.x)
    except Exception:
        pass
    return None, None

