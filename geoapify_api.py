import requests
import os
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

# --- Custom Exceptions for Clearer Error Handling ---
class GeoapifyError(Exception):
    """Base exception for this module."""
    pass

class GeoapifyAPIKeyError(GeoapifyError):
    """Raised when the API key is missing."""
    pass

class GeoapifyRequestError(GeoapifyError):
    """Raised for network or HTTP errors."""
    pass

class GeoapifyResponseError(GeoapifyError):
    """Raised for unexpected or empty API responses."""
    pass


def get_api_key() -> Optional[str]:
    """
    Load Geoapify API key from environment.
    Assumes load_dotenv() has been called by the application's entry point.
    """
    key = os.environ.get("GEOAPIFY_API_KEY")
    if key and key != "YOUR_GEOAPIFY_API_KEY_HERE":
        return key

    # Fallback to reading .env manually if not in environment
    env_file = Path(__file__).with_name('.env')
    if env_file.exists():
        for line in env_file.read_text(encoding='utf-8').splitlines():
            if line.startswith('GEOAPIFY_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"').strip("'")
                if key and key != "YOUR_GEOAPIFY_API_KEY_HERE":
                    return key
    return None


# Load the API key once at the module level for efficiency.
API_KEY = get_api_key()

def _check_api_key():
    """Raises an exception if the API key is not configured."""
    if not API_KEY:
        raise GeoapifyAPIKeyError("Missing or invalid GEOAPIFY_API_KEY. Please check your .env file.")

def _make_request(url: str, params: Dict[str, Any], timeout: int) -> Dict[str, Any]:
    """A centralized request handler with unified error handling."""
    try:
        resp = requests.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        body = f" body={e.response.text[:180]}" if e.response else ""
        raise GeoapifyRequestError(f"Geoapify HTTP error: {e}{body}") from e
    except requests.exceptions.RequestException as e:
        raise GeoapifyRequestError(f"Geoapify network error: {e}") from e

def reverse_geocode(latitude: float, longitude: float) -> Dict[str, Any]:
    """
    Convert lat/lon to address using Geoapify reverse geocoding.
    Returns dict with address info or raises an exception on error.
    """
    _check_api_key()
    url = "https://api.geoapify.com/v1/geocode/reverse"
    params = {"lat": latitude, "lon": longitude, "apiKey": API_KEY}
    data = _make_request(url, params, timeout=5)

    try:
        if data.get('features'):
            props = data['features'][0]['properties']
            return {
                'address': props.get('address_line1'),
                'city': props.get('city'),
                'state': props.get('state'),
                'country': props.get('country'),
                'postcode': props.get('postcode'),
                'lat': latitude,
                'lon': longitude
            }
        raise GeoapifyResponseError("Reverse geocode returned no results.")
    except (KeyError, IndexError) as e:
        raise GeoapifyResponseError("Unexpected Geoapify reverse geocode response format.") from e


def forward_geocode(address: str) -> Tuple[float, float]:
    """
    Convert address to lat/lon using Geoapify forward geocoding.
    Returns (lat, lon) tuple or raises an exception on error.
    """
    _check_api_key()
    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": address, "apiKey": API_KEY, "limit": 1}
    data = _make_request(url, params, timeout=5)

    try:
        if data.get('features'):
            coords = data['features'][0]['geometry']['coordinates']
            return (coords[1], coords[0])  # [lon, lat] -> (lat, lon)
        raise GeoapifyResponseError("Forward geocode returned no results.")
    except (KeyError, IndexError) as e:
        raise GeoapifyResponseError("Unexpected Geoapify forward geocode response format.") from e


def search_places(latitude: float, longitude: float, categories: List[str], radius: int = 2000, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Search for nearby places by category using the Geoapify Places API.
    Returns a list of places or raises an exception on error.
    """
    _check_api_key()
    url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": ",".join(categories),
        "filter": f"circle:{longitude},{latitude},{radius}",
        "limit": limit,
        "apiKey": API_KEY
    }
    data = _make_request(url, params, timeout=7)

    try:
        places = []
        if data.get('features'):
            for feature in data['features']:
                props = feature['properties']
                address = props.get('address_line2') or props.get('address_line1') or 'N/A'
                places.append({
                    'name': props.get('name', 'Unnamed Business'),
                    'address': address,
                    'lat': props.get('lat'),
                    'lon': props.get('lon'),
                    'categories': props.get('categories')
                })
        # An empty list is a valid result (no places found)
        return places
    except KeyError as e:
        raise GeoapifyResponseError("Unexpected Geoapify places response format.") from e


def search_address_candidates(address: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Search for an address and return a list of candidates with details.
    Returns a list of candidates or raises an exception on error.
    """
    _check_api_key()
    url = "https://api.geoapify.com/v1/geocode/search"
    params = {"text": address, "apiKey": API_KEY, "limit": limit}
    data = _make_request(url, params, timeout=5)

    try:
        candidates = []
        if data.get('features'):
            for feature in data['features']:
                props = feature['properties']
                coords = feature['geometry']['coordinates']
                candidates.append({
                    'formatted': props.get('formatted') or props.get('address_line1', 'Unknown'),
                    'lat': coords[1],
                    'lon': coords[0]
                })
        # An empty list is a valid result (no candidates found)
        return candidates
    except (KeyError, IndexError) as e:
        raise GeoapifyResponseError("Unexpected Geoapify address response format.") from e
