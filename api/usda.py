"""USDA FoodData Central API client.

Returns ingredient nutrition pre-filled in the shape expected by
modules.ingredients.ingredient.create().

Requires USDA_API_KEY in the environment. Falls back to DEMO_KEY (capped
at 30 req/hour per IP) so the feature works without setup; users can get
a free unlimited key at https://fdc.nal.usda.gov/api-key-signup.html
"""
from functools import lru_cache
from os import getenv

import requests

api_key = getenv('USDA_API_KEY') or 'DEMO_KEY'

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
        params={'api_key': api_key},
        json={
            'query': query,
            'pageSize': 5,
            'dataType': ['Foundation', 'SR Legacy', 'Survey (FNDDS)'],
        },
    )
    if not response.ok:
        if response.status_code == 429:
            raise Exception('USDA rate limit hit. Set USDA_API_KEY in your .env for a free unlimited key.')
        raise Exception(f'{response.status_code} {response.reason}')
    foods = response.json().get('foods', [])
    if not foods:
        raise Exception('No results')
    return foods


@lru_cache(maxsize=128)
def get_food_details(fdc_id):
    """Fetch full nutrient data for a single FDC food. Cached per session —
    re-selecting the same result in the picker is a free lookup."""
    response = requests.get(f'{BASE_URL}/food/{fdc_id}', params={'api_key': api_key})
    if not response.ok:
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
