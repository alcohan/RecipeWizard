"""USDA FoodData Central API client.

Returns ingredient nutrition pre-filled in the shape expected by
modules.ingredients.ingredient.create().

Key resolution (highest priority first):
  1. set_api_key(value) — what the GUI Preferences dialog calls.
  2. USDA_API_KEY env var — for dev/CI runs.
  3. DEMO_KEY — public-fallback, capped at 30 req/hr per IP.

Users can get a free unlimited key at
https://fdc.nal.usda.gov/api-key-signup.html
"""
from functools import lru_cache
from os import getenv

import requests

DEMO_KEY = 'DEMO_KEY'
SIGNUP_URL = 'https://fdc.nal.usda.gov/api-key-signup.html'

_override_key = None  # set by the GUI from QSettings; None = fall through to env/DEMO

BASE_URL = 'https://api.nal.usda.gov/fdc/v1'

# USDA nutrient IDs -> app ingredient field names. Nutrients absent from a
# food are treated as 0.
NUTRIENT_FIELDS = {
    1008: 'Calories',
    1004: 'TTLFatGrams',
    1258: 'SatFatGrams',
    1253: 'CholesterolMilligrams',
    1093: 'SodiumMilligrams',
    1005: 'CarbGrams',
    1079: 'FiberGrams',
    2000: 'SugarGrams',
    1003: 'ProteinGrams',
}


def set_api_key(value):
    '''Push a user-supplied key into the client. Pass '' or None to clear
    the override (the client will then use USDA_API_KEY or DEMO_KEY).
    Clears the response cache so a stale 429 retry can succeed under the
    new key.'''
    global _override_key
    _override_key = (value or '').strip() or None
    search.cache_clear()
    get_food_details.cache_clear()


def _current_api_key():
    if _override_key:
        return _override_key
    return getenv('USDA_API_KEY') or DEMO_KEY


def is_using_demo_key():
    '''True when the client is falling back to the public DEMO_KEY. Used by
    the GUI to tailor the 429 message (the fix is "get a key", not "wait").'''
    return _current_api_key() == DEMO_KEY


def _rate_limit_message():
    if is_using_demo_key():
        return (
            'USDA rate limit hit on the shared DEMO_KEY (30 requests/hour). '
            'Get a free unlimited key from fdc.nal.usda.gov/api-key-signup.html '
            'and paste it into Tools > Preferences.'
        )
    return 'USDA rate limit hit. Try again in an hour, or check your API key in Tools > Preferences.'


@lru_cache(maxsize=128)
def search(query):
    """Hit FDC /foods/search. Returns the list of food hits.

    Uses POST + JSON body since FDC rejects multi-valued dataType query
    params over GET, and unfiltered queries return only Branded results
    (which use per-serving rather than per-100g nutrition).

    Cached: repeat queries within the session don't re-hit the API.
    DEMO_KEY caps at 30 req/hour per IP, so this matters — clicking
    through 5 results triggers 5 detail fetches, and re-running a
    search would otherwise burn the search budget too.
    """
    response = requests.post(
        f'{BASE_URL}/foods/search',
        params={'api_key': _current_api_key()},
        json={
            'query': query,
            'pageSize': 5,
            'dataType': ['Foundation', 'SR Legacy', 'Survey (FNDDS)'],
        },
    )
    if not response.ok:
        if response.status_code == 429:
            raise Exception(_rate_limit_message())
        if response.status_code in (401, 403):
            raise Exception('USDA rejected the API key. Check it in Tools > Preferences.')
        raise Exception(f'{response.status_code} {response.reason}')
    foods = response.json().get('foods', [])
    if not foods:
        raise Exception('No results')
    return foods


@lru_cache(maxsize=128)
def get_food_details(fdc_id):
    """Fetch full nutrient data for a single FDC food. Cached per session —
    re-selecting the same result in the picker is a free lookup."""
    response = requests.get(f'{BASE_URL}/food/{fdc_id}', params={'api_key': _current_api_key()})
    if not response.ok:
        if response.status_code == 429:
            raise Exception(_rate_limit_message())
        if response.status_code in (401, 403):
            raise Exception('USDA rejected the API key. Check it in Tools > Preferences.')
        raise Exception(f'{response.status_code} {response.reason}')
    return response.json()


def build_prefill(food, fallback_description=None):
    """Convert a USDA food-detail payload into a prefill dict for ingredient.create().

    All Foundation / SR Legacy / FNDDS nutrients are per-100g, so the default
    100g portion needs no further scaling. Missing nutrients default to 0.
    """
    result = {
        'Name': food.get('description', fallback_description or ''),
        'Unit': '100 g',
        'Weight': 100,
    }
    for field in NUTRIENT_FIELDS.values():
        result[field] = 0

    for nut in food.get('foodNutrients', []):
        # Detail payload nests the nutrient ID one level deeper than search results
        nut_id = nut.get('nutrient', {}).get('id') or nut.get('nutrientId')
        if nut_id in NUTRIENT_FIELDS:
            value = nut.get('amount') if nut.get('amount') is not None else nut.get('value', 0)
            result[NUTRIENT_FIELDS[nut_id]] = round(value or 0, 2)

    return result


def get_simple(query):
    """Take the top USDA hit and return a prefill dict for ingredient.create().

    The search endpoint truncates foodNutrients per food, so we follow up
    with a /food/{fdcId} call to get the complete set.
    """
    hits = search(query)
    food = get_food_details(hits[0]['fdcId'])
    return build_prefill(food, fallback_description=hits[0]['description'])
