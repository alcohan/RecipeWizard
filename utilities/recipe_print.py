'''What a printed recipe page says: calculated amounts, portion tools,
and which rows print. Pure Python with no database or Qt, so it's tested
on its own; db.recipe_print_data() feeds it and gui/printing paints it.

Amounts: a row's quantity times its ingredient's unit, in the unit's own
measure, as a kitchen fraction — 1/3 × "3 cups" prints "1 cup",
1/2 × "8 f.oz" prints "4 fl oz".

Portion tools (table portion_tools): an ingredient links to a tool when
its Portion text is the tool's name, ignoring case. A sized tool (a
colored disher) is worked out again from the calculated amount, within
the tool's family only:
  - one scoop of any tool in the family that is exactly the amount
  - else a whole number of the ingredient's own tool ("2 × Grey")
  - else a whole number of another tool in the family, fewest scoops
  - else nothing: a blank beats a misleading scoop.
A tool with no size (tongs, bottle) prints its name. Portion text that
links to no tool prints only when the quantity is 1, since the text
describes one unit ("Half" for ".5 ea").
'''

import math
import re
from dataclasses import dataclass
from fractions import Fraction

from utilities import portions

# Kitchen fractions: denominators tried in order, so 0.5 is 1/2 not 2/4.
_DENOMINATORS = (2, 3, 4, 8)
_FRACTION_TOL = 0.01
_GLYPHS = {
    Fraction(1, 2): '½', Fraction(1, 3): '⅓', Fraction(2, 3): '⅔',
    Fraction(1, 4): '¼', Fraction(3, 4): '¾', Fraction(1, 8): '⅛',
    Fraction(3, 8): '⅜', Fraction(5, 8): '⅝', Fraction(7, 8): '⅞',
}
# How a measure prints: (singular, plural).
_MEASURE_LABELS = {
    'f.oz': ('fl oz', 'fl oz'),
    'cup': ('cup', 'cups'),
    'tbsp': ('tbsp', 'tbsp'),
    'tsp': ('tsp', 'tsp'),
    'pt': ('pint', 'pints'),
    'qt': ('quart', 'quarts'),
    'ea': ('each', 'each'),
    'each': ('each', 'each'),
    'w.oz': ('wt oz', 'wt oz'),
    'wt oz': ('wt oz', 'wt oz'),
}
_SCOOP_TOL = 0.02   # relative: 1.98 scoops is 2 scoops


@dataclass(frozen=True)
class Tool:
    id: int
    name: str
    family: str = ''
    size_floz: float | None = None
    color: str | None = None
    pattern: str = 'solid'

    @property
    def sized(self):
        return self.size_floz is not None and self.size_floz > 0


@dataclass(frozen=True)
class ToolUse:
    '''What the Portion tool column prints for one row.'''
    count: int | None    # scoops of `tool`; None for an unsized tool or plain text
    tool: Tool | None
    text: str            # "1 Grey", "2 × Red slotted", "Tongs", "Half"


def fraction_text(value):
    '''1.5 → "1½", 0.333 → "⅓", 2 → "2", 0.3 → "0.3".'''
    if value is None:
        return ''
    value = float(value)
    whole = int(value)
    frac = value - whole
    if abs(frac) < _FRACTION_TOL:
        return str(whole)
    if 1 - frac < _FRACTION_TOL:
        return str(whole + 1)
    for den in _DENOMINATORS:
        num = round(frac * den)
        if 0 < num < den and abs(frac - num / den) < _FRACTION_TOL:
            glyph = _GLYPHS.get(Fraction(num, den), f'{num}/{den}')
            return f'{whole}{glyph}' if whole else glyph
    return f'{value:.2f}'.rstrip('0').rstrip('.')


def _measure_label(measure, amount):
    key = (measure or '').strip().lower()
    singular, plural = _MEASURE_LABELS.get(key, (measure or '', measure or ''))
    return singular if abs(float(amount) - 1) < _FRACTION_TOL else plural


@dataclass(frozen=True)
class Amount:
    value: float | None     # in the unit's measure; None when the unit has no amount
    measure: str            # canonical measure or the unit's own word
    floz: float | None      # the amount in f.oz, when it's a volume
    text: str               # "1 cup", "4 fl oz", "2 × each"


def amount(quantity, unit_text):
    '''The calculated amount of `quantity` units of `unit_text`.'''
    qty = float(quantity or 0)
    unit = portions.parse_unit(unit_text)
    if unit is None:
        # "each", blank: no amount in the unit, so the quantity is the amount.
        word = (unit_text or '').strip()
        label = _measure_label(word, qty) if word else ''
        return Amount(None, word, None, f'{fraction_text(qty)} {label}'.strip())
    total = qty * unit.amount
    floz = qty * unit.floz if unit.is_volume else None
    return Amount(total, unit.measure, floz,
                  f'{fraction_text(total)} {_measure_label(unit.measure, total)}'.strip())


def find_tool(portion_text, tools):
    '''The tool an ingredient's Portion text names, or None.'''
    key = ' '.join((portion_text or '').split()).casefold()
    if not key:
        return None
    for tool in tools:
        if tool.name.casefold() == key:
            return tool
    return None


def _whole(n):
    r = round(n)
    return r if r >= 1 and abs(n - r) <= _SCOOP_TOL * max(1.0, n) else None


def resolve_tool(quantity, unit_text, portion_text, tools):
    '''The ToolUse for one row, or None when the column stays blank.'''
    text = (portion_text or '').strip()
    tool = find_tool(text, tools)
    qty = float(quantity or 0)
    if tool is None:
        return ToolUse(None, None, text) if text and abs(qty - 1) < 1e-6 else None
    if not tool.sized:
        return ToolUse(None, tool, tool.name)
    amt = amount(qty, unit_text)
    if amt.floz is None:
        # Not a volume: only the one-unit case is safe to name.
        return ToolUse(1, tool, f'1 {tool.name}') if abs(qty - 1) < 1e-6 else None
    family = [t for t in tools if t.sized and t.family.casefold() == tool.family.casefold()] or [tool]
    for t in family:
        if _whole(amt.floz / t.size_floz) == 1:
            return ToolUse(1, t, f'1 {t.name}')
    n = _whole(amt.floz / tool.size_floz)
    if n:
        return ToolUse(n, tool, f'{n} × {tool.name}')
    best = None
    for t in family:
        n = _whole(amt.floz / t.size_floz)
        if n and (best is None or n < best[0]):
            best = (n, t)
    if best:
        return ToolUse(best[0], best[1], f'{best[0]} × {best[1].name}')
    return None


# --- linking existing Portion text to tools (Configure › Portion tools) ---

_ALIASES = {'btl': 'bottle', 'gray': 'grey'}
_MULTIPLE_RE = re.compile(r'^\s*(\d+)\s*[x×]\s*(.+)$', re.IGNORECASE)


def suggest_tool(portion_text, unit_text, tools):
    '''A tool to link some unlinked Portion text to, or None.
    "2 x grey", "Blue Scoop", "btl" → Grey, Blue, Bottle. A sized
    suggestion must fit the unit: a whole number of scoops.'''
    key = ' '.join((portion_text or '').split()).casefold()
    if not key:
        return None
    m = _MULTIPLE_RE.match(key)
    if m:
        key = m.group(2).strip()
    if key.endswith(' scoop'):
        key = key[:-len(' scoop')].strip()
    key = _ALIASES.get(key, key)
    tool = find_tool(key, tools)
    if tool is None:
        return None
    if tool.sized and size_problem(unit_text, tool):
        return None
    return tool


def size_problem(unit_text, tool):
    '''Why `tool` doesn't fit one unit of `unit_text`, or None if it
    does (or isn't sized, or the unit isn't a volume).'''
    if tool is None or not tool.sized:
        return None
    unit = portions.parse_unit(unit_text)
    if unit is None or not unit.is_volume:
        return None
    if _whole(unit.floz / tool.size_floz):
        return None
    return (f'{tool.name} is {fraction_text(tool.size_floz)} fl oz; one unit is '
            f'{fraction_text(unit.floz)} fl oz')


# --- nutrition cards ---------------------------------------------------------

# A component can get a Nutrition Facts panel of its own beside the
# recipe's (a dressing served on the side). By default, ingredients in
# these categories do; the recipe's Print view turns any component on
# or off. Then the recipe's main panel is titled "<name> (dressed)",
# unless the recipe gives its own title.
CARD_CATEGORIES = ('Dressing',)


def card_by_default(row):
    '''Whether a component row gets a card when the recipe hasn't said.'''
    return row.get('Type') == 'ingredient' and (row.get('TagName') or '') in CARD_CATEGORIES


def card_label(name, unit_text, unit_weight, unit_nutrition):
    '''{name, serving, weight, nutrition} for one card: per 1 fl oz when
    the unit is a volume, otherwise per one unit ("½ each").'''
    unit = portions.parse_unit(unit_text)
    if unit is not None and unit.is_volume and unit.floz:
        scale, serving = 1.0 / unit.floz, '1 fl oz'
    else:
        scale, serving = 1.0, amount(1, unit_text).text or '1 serving'
    weight = float(unit_weight or 0) * scale
    if weight:
        serving += f' ({weight:.0f} g)'
    return {
        'name': name,
        'serving': serving,
        'weight': weight,
        'nutrition': {k: float(v or 0) * scale for k, v in unit_nutrition.items()},
    }


def nutrition_title(recipe_name, has_cards, override=None):
    '''The subtitle of the recipe's main panel, or None for none.'''
    override = (override or '').strip()
    if override:
        return override
    return f'{recipe_name} (dressed)' if has_cards else None


# --- which rows print -----------------------------------------------------

# Hardcoded for now: a wrap's tortilla is Packaging (it's a freebie of
# the format) but belongs on the page. Packaging that carries calories
# prints on these formats; napkins, paper and stickers don't. To be
# replaced by a per-recipe show/hide for template-added rows.
FORMATS_SHOWING_FOOD_PACKAGING = ('wrap',)


def prints_row(row, format_name):
    '''Whether a component row belongs on the printed page.'''
    if (row.get('TagName') or '') != 'Packaging':
        return True
    if (format_name or '').casefold() not in FORMATS_SHOWING_FOOD_PACKAGING:
        return False
    return (row.get('UnitCalories') or 0) > 0


def without_portions(data):
    '''A copy of db.recipe_print_data() for the page without portion
    information: no Amount or Portion tool column and no scoop key.
    Ingredients, allergens and nutrition stay.'''
    out = dict(data)
    out['rows'] = [dict(r, tool=None) for r in data['rows']]
    out['tools_used'] = []
    out['portions'] = False
    return out


# --- nutrition label rounding ------------------------------------------------
# Calories to the nearest 5, sodium to the nearest 10 mg, every other
# nutrient to a whole gram (or milligram). Halves round up.

def _round_to(value, step):
    try:
        v = float(value or 0)
    except (TypeError, ValueError):
        v = 0.0
    return int(math.floor(v / step + 0.5) * step)


def label_calories(value):
    return _round_to(value, 5)


def label_amount(key, value):
    '''A nutrient's amount as the label prints it (a whole number).'''
    return _round_to(value, 10 if key == 'SodiumMilligrams' else 1)
