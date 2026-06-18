import requests
import logging

logger = logging.getLogger(__name__)

NOMINATIM_URL  = 'https://nominatim.openstreetmap.org/search'
DEFAULT_COUNTRY = 'India'

def geocode_address(address: str) -> dict | None:
    """
    Convert address text to GPS coordinates.
    Returns { 'latitude': float, 'longitude': float } or None.
    """
    if not address or not address.strip():
        return None

    full_query = f"{address.strip()}, {DEFAULT_COUNTRY}"

    try:
        response = requests.get(
            NOMINATIM_URL,
            params={
                'q':            full_query,
                'format':       'json',
                'limit':        1,
                'addressdetails': 0,
                'countrycodes': 'in',
            },
            headers={'User-Agent': 'FixIt-ServiceMarketplace/1.0'},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json()

        if not results:
            logger.warning(f'Geocoding found no results for: {full_query}')
            return None

        best = results[0]
        return {
            'latitude':  round(float(best['lat']), 6),
            'longitude': round(float(best['lon']), 6),
        }

    except requests.Timeout:
        logger.error(f'Geocoding timeout for: {address}')
        return None
    except requests.RequestException as e:
        logger.error(f'Geocoding request failed: {e}')
        return None
    except (KeyError, ValueError, IndexError) as e:
        logger.error(f'Geocoding parse failed: {e}')
        return None