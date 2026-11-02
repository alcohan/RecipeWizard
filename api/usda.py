"""USDA FoodData Central API client, plus portion scaling.

Search and detail calls return FDC payloads; the helpers below turn a
food into what RecipeWizard stores — nutrition per *our* unit:

  nutrients_per_100g(food)   FDC nutrient amounts are per 100 g for
                             Foundation, SR Legacy, Survey and Branded.
  portions(food)             the food's measured portions ("1 cup,
                             chopped = 67 g"), normalised across the
                             four data types' different shapes.
  grams_per_unit(unit, ...)  how many grams one of our units weighs:
                             from mass units directly ("1 w.oz"), from
                             a matching USDA portion ("3 cups"), or by
                             converting between volume units ("2 f.oz"
                             from a cup portion).
  scale(per_100g, grams)     nutrition for that many grams.

No Qt here: the GUI runs these calls on a worker thread.

Key resolution (highest priority first):
  1. set_api_key(value) — what the GUI Preferences dialog calls.
  2. USDA_API_KEY env var — for dev/CI runs.
  3. DEMO_KEY — public-fallback, capped at 30 req/hr per IP.

Users can get a free unlimited key at
https://fdc.nal.usda.gov/api-key-signup.html
"""
import re
from fractions import Fraction
from functools import lru_cache
from os import getenv

import requests

DEMO_KEY = 'DEMO_KEY'
SIGNUP_URL = 'https://fdc.nal.usda.gov/api-key-signup.html'

_override_key = None  # set by the GUI from QSettings; None = fall through to env/DEMO

BASE_URL = 'https://api.nal.usda.gov/fdc/v1'
TIMEOUT = 15  # seconds; a hung request shouldn't hang the lookup forever

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
# Some Foundation foods report energy only as Atwater factors.
_ENERGY_FALLBACKS = (2048, 2047)
# Total sugars has a second id in newer Foundation data.
_SUGAR_FALLBACKS = (1063,)

# Search ordering: lab-measured generic foods first, Branded last.
DATA_TYPES = ('Foundation', 'SR Legacy', 'Survey (FNDDS)', 'Branded')
_TYPE_RANK = {t: i for i, t in enumerate(DATA_TYPES)}

# --- units ------------------------------------------------------------------

# grams per unit
MASS_UNITS = {'g': 1.0, 'kg': 1000.0, 'mg': 0.001, 'oz': 28.349523125, 'lb': 453.59237}
# millilitres per unit (US customary)
VOLUME_UNITS = {
    'ml': 1.0, 'l': 1000.0, 'tsp': 4.92892, 'tbsp': 14.7868, 'floz': 29.5735,
    'cup': 236.588, 'pint': 473.176, 'quart': 946.353, 'gallon': 3785.41,
}
_ALIASES = {
    'g': 'g', 'gr': 'g', 'gram': 'g', 'grams': 'g', 'grm': 'g',
    'kg': 'kg', 'kilogram': 'kg', 'mg': 'mg',
    'oz': 'oz', 'ounce': 'oz', 'ounces': 'oz', 'w.oz': 'oz', 'woz': 'oz', 'wt.oz': 'oz', 'wt oz': 'oz',
    'lb': 'lb', 'lbs': 'lb', 'pound': 'lb', 'pounds': 'lb',
    'ml': 'ml', 'milliliter': 'ml', 'millilitre': 'ml', 'mlt': 'ml',
    'l': 'l', 'liter': 'l', 'litre': 'l',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp', 't': 'tsp',
    'tbsp': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp', 'tbs': 'tbsp', 'tbl': 'tbsp',
    'f.oz': 'floz', 'fl.oz': 'floz', 'fl oz': 'floz', 'floz': 'floz', 'fluid ounce': 'floz',
    'fl. oz': 'floz', 'fl oz.': 'floz',
    'cup': 'cup', 'cups': 'cup', 'c': 'cup',
    'pint': 'pint', 'pints': 'pint', 'pt': 'pint',
    'quart': 'quart', 'quarts': 'quart', 'qt': 'quart',
    'gallon': 'gallon', 'gallons': 'gallon', 'gal': 'gallon',
    'ea': 'each', 'each': 'each', 'piece': 'each', 'pieces': 'each', 'pc': 'each', 'whole': 'each',
}

_QTY = re.compile(r'^\s*(\d+\s+\d+/\d+|\d+/\d+|\d*\.\d+|\d+)(?:st|nd|rd|th)?\s*(.*)$')
_UNICODE_FRACTIONS = {'½': '1/2', '⅓': '1/3', '⅔': '2/3', '¼': '1/4', '¾': '3/4', '⅛': '1/8'}


def parse_quantity(text):
    '''"1 1/2" → 1.5, "1/40" → 0.025, ".5" → 0.5. None if not a number.'''
    s = str(text).strip()
    for k, v in _UNICODE_FRACTIONS.items():
        s = s.replace(k, f' {v}')
    s = s.strip()
    try:
        return float(sum(Fraction(p) for p in s.split()))
    except (ValueError, ZeroDivisionError):
        return None


def parse_unit(text):
    '''Split one of our unit strings into (quantity, unit key, word).

    "3 cups" → (3.0, 'cup', 'cups'); "2 f.oz" → (2.0, 'floz', 'f.oz');
    "1 w.oz" → (1.0, 'oz', 'w.oz'); ".5 ea" → (0.5, 'each', 'ea');
    "1/40th loaf" → (0.025, None, 'loaf'); "oz" → (1.0, 'oz', 'oz').
    The key is None for words we can't convert (loaf, wedge, …).'''
    s = (text or '').strip()
    for k, v in _UNICODE_FRACTIONS.items():
        s = s.replace(k, f' {v}').strip()
    qty, rest = 1.0, s
    m = _QTY.match(s)
    if m:
        q = parse_quantity(m.group(1))
        if q is not None:
            qty, rest = q, m.group(2)
    word = rest.strip().lower()
    key = _ALIASES.get(word) or _ALIASES.get(word.rstrip('.')) or _ALIASES.get(word.rstrip('s'))
    return qty, key, rest.strip()


def unit_kind(key):
    if key in MASS_UNITS:
        return 'mass'
    if key in VOLUME_UNITS:
        return 'volume'
    if key == 'each':
        return 'count'
    return None


# --- API --------------------------------------------------------------------

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


def _raise_for(response):
    if response.status_code == 429:
        raise Exception(_rate_limit_message())
    if response.status_code in (401, 403):
        raise Exception('USDA rejected the API key. Check it in Tools > Preferences.')
    raise Exception(f'USDA error: {response.status_code} {response.reason}')


@lru_cache(maxsize=128)
def search(query, include_branded=True, page_size=25):
    """Hit FDC /foods/search. Returns the food hits, generic data types
    (Foundation, SR Legacy, Survey) ahead of Branded and otherwise in
    USDA's relevance order. Experimental foods are left out.

    POST + JSON body: FDC rejects multi-valued dataType query params over
    GET. Cached: repeat queries within the session don't re-hit the API
    (DEMO_KEY caps at 30 requests/hour per IP).
    """
    types = list(DATA_TYPES if include_branded else DATA_TYPES[:3])
    try:
        response = requests.post(
            f'{BASE_URL}/foods/search',
            params={'api_key': _current_api_key()},
            json={'query': query, 'pageSize': page_size, 'dataType': types},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise Exception(f'Could not reach USDA: {exc.__class__.__name__}') from exc
    if not response.ok:
        _raise_for(response)
    foods = response.json().get('foods', [])
    if not foods:
        raise Exception('No results')
    order = {f['fdcId']: i for i, f in enumerate(foods)}
    return sorted(foods, key=lambda f: (_TYPE_RANK.get(f.get('dataType'), 9), order[f['fdcId']]))


@lru_cache(maxsize=128)
def get_food_details(fdc_id):
    """Fetch full nutrient and portion data for a single FDC food. Cached
    per session — re-selecting the same result is a free lookup."""
    try:
        response = requests.get(f'{BASE_URL}/food/{fdc_id}',
                                params={'api_key': _current_api_key()}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise Exception(f'Could not reach USDA: {exc.__class__.__name__}') from exc
    if not response.ok:
        _raise_for(response)
    return response.json()


# --- nutrition + portions ---------------------------------------------------

def nutrients_per_100g(food):
    '''{field: amount per 100 g} for the app's nutrition fields. Missing
    nutrients are 0. Works on detail payloads and on search hits (whose
    nutrient list is abridged).'''
    by_id = {}
    for nut in food.get('foodNutrients', []):
        # Detail payloads nest the id under "nutrient"; search hits don't.
        nid = (nut.get('nutrient') or {}).get('id') or nut.get('nutrientId')
        value = nut.get('amount') if nut.get('amount') is not None else nut.get('value')
        if nid is not None and value is not None:
            by_id[nid] = float(value)
    result = {}
    for nid, field in NUTRIENT_FIELDS.items():
        value = by_id.get(nid)
        if value is None and field == 'Calories':
            value = next((by_id[i] for i in _ENERGY_FALLBACKS if i in by_id), None)
        if value is None and field == 'SugarGrams':
            value = next((by_id[i] for i in _SUGAR_FALLBACKS if i in by_id), None)
        result[field] = value or 0.0
    return result


def portions(food):
    '''Measured portions as dicts {label, grams, amount, key}: `grams`
    is the weight of `amount` of the measure, `key` the unit key when
    the measure is one we can convert (cup, tbsp, oz, each…), else None.

    Foundation puts the measure in measureUnit; SR Legacy in modifier
    (measureUnit "undetermined"); Survey in portionDescription; Branded
    has only a serving size plus household text ("2 1/2 cup").'''
    out = []
    for p in food.get('foodPortions', []) or []:
        grams = p.get('gramWeight')
        if not grams:
            continue
        amount = float(p.get('amount') or 1.0)
        unit_name = ((p.get('measureUnit') or {}).get('name') or '').strip()
        modifier = (p.get('modifier') or '').strip()
        desc = (p.get('portionDescription') or '').strip()
        if desc and desc.lower() != 'quantity not specified':
            q, key, word = parse_unit(desc)
            label, amount = desc, q
        else:
            if unit_name.lower() in ('', 'undetermined'):
                word = modifier
                q, key, _w = parse_unit(modifier)
                label = f'{_fmt(amount)} {modifier}'.strip()
            else:
                word = unit_name
                key = _ALIASES.get(unit_name.lower())
                label = f'{_fmt(amount)} {unit_name}' + (f', {modifier}' if modifier else '')
        if key is None and unit_name.upper() == 'RACC':
            label = f'Reference serving ({_fmt(grams)} g)'
        out.append({'label': label, 'grams': float(grams), 'amount': amount or 1.0, 'key': key})
    size, size_unit = food.get('servingSize'), (food.get('servingSizeUnit') or '').lower()
    if size and size_unit in ('g', 'grm', 'gram', 'grams'):
        household = (food.get('householdServingFullText') or '').strip()
        if household:
            q, key, _w = parse_unit(household)
            out.append({'label': f'{household} (serving)', 'grams': float(size),
                        'amount': q or 1.0, 'key': key})
        else:
            out.append({'label': f'Serving ({_fmt(size)} g)', 'grams': float(size), 'amount': 1.0, 'key': None})
    return out


def grams_per_unit(unit_text, food_portions=()):
    '''Grams in one of our units, or None, plus how it was worked out.

    Mass units convert directly. A volume or count unit uses a USDA
    portion of the same measure, or of another volume measure converted
    through millilitres ("2 f.oz" from a "1 cup = 21 g" portion).'''
    qty, key, word = parse_unit(unit_text)
    kind = unit_kind(key)
    if kind == 'mass':
        grams = qty * MASS_UNITS[key]
        return grams, f'{_fmt(qty)} {word or key} = {_fmt(grams)} g'
    if kind is None:
        return None, f'"{unit_text}" isn\'t a measure USDA portions use — enter its weight'
    same = [p for p in food_portions if p['key'] == key]
    if same:
        p = same[0]
        grams = qty * p['grams'] / p['amount']
        return grams, f'{_fmt(qty)} {word} = {_fmt(grams)} g, from USDA "{p["label"]}"'
    if kind == 'volume':
        vol = [p for p in food_portions if unit_kind(p['key']) == 'volume']
        if vol:
            p = vol[0]
            g_per_ml = p['grams'] / (p['amount'] * VOLUME_UNITS[p['key']])
            grams = qty * VOLUME_UNITS[key] * g_per_ml
            return grams, f'{_fmt(qty)} {word} = {_fmt(grams)} g, converted from USDA "{p["label"]}"'
    return None, f'USDA has no {word} portion for this food — enter the weight of {_fmt(qty)} {word}'


def scale(per_100g, grams):
    '''Nutrition for `grams` of the food, rounded to 2 decimals.'''
    factor = float(grams) / 100.0
    return {field: round(value * factor, 2) for field, value in per_100g.items()}


def describe(food):
    '''One-line description for a result list: name, plus brand for
    Branded foods.'''
    name = food.get('description') or '(no description)'
    brand = food.get('brandName') or food.get('brandOwner')
    if food.get('dataType') == 'Branded' and brand:
        return f'{name} — {brand}'
    return name


def _fmt(value):
    try:
        return '{:.2f}'.format(float(value)).rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return str(value)
