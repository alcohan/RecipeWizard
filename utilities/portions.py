'''Portion rules: how a recipe format sizes the ingredients of a category.

A format (recipe-kind tag) can carry one rule per ingredient category
(`tag_portion_rules`):

  base   the category shares one total amount — a salad's greens are
         3 cups however many greens it uses, split by each row's share
  fixed  every ingredient of the category gets the same amount — rice on
         a salad is a 3 f.oz topping

A Connections row follows its format's rule when `portion_share` is set;
NULL means pinned, i.e. its Quantity is typed by hand. Quantities are
always derived from (rule, shares, the ingredient's unit), never from the
row's previous quantity, so working them out again gives the same answer.

Amounts are volumes. Every "oz" in the app is a fluid (portion) ounce, so
cups and ounces convert between each other but never to grams; the gram
Weight on an ingredient is per unit and just scales with the quantity.

This module is pure Python with no database access, so the migration in
setup.py and the db layer share one implementation.
'''

import re
from dataclasses import dataclass

MODES = ('base', 'fixed')

# Volume measures in fluid ounces. Keys are the canonical names stored in
# tag_portion_rules.measure; aliases map what people type in Unit text.
_FLOZ_PER = {
    'f.oz': 1.0,
    'cup': 8.0,
    'tbsp': 0.5,
    'tsp': 1.0 / 6.0,
    'pt': 16.0,
    'qt': 32.0,
}
_ALIASES = {
    'f.oz': 'f.oz', 'fl.oz': 'f.oz', 'fl oz': 'f.oz', 'floz': 'f.oz', 'fz': 'f.oz',
    'oz': 'f.oz', 'ounce': 'f.oz', 'ounces': 'f.oz',
    'cup': 'cup', 'cups': 'cup', 'c': 'cup',
    'tbsp': 'tbsp', 'tbs': 'tbsp', 'tablespoon': 'tbsp', 'tablespoons': 'tbsp',
    'tsp': 'tsp', 'teaspoon': 'tsp', 'teaspoons': 'tsp',
    'pt': 'pt', 'pint': 'pt', 'pints': 'pt',
    'qt': 'qt', 'quart': 'qt', 'quarts': 'qt',
}
# The measures offered when writing a rule, in display order.
RULE_MEASURES = ('cup', 'f.oz', 'tbsp', 'tsp')

# "1", "1.5", ".5", "1/2", "1 1/2", optionally followed by an ordinal
# suffix as in "1/6th wedge".
_AMOUNT_RE = re.compile(
    r'^\s*(?:(?P<whole>\d+)\s+(?=\d+\s*/))?'
    r'(?P<num>\d*\.?\d+)(?:\s*/\s*(?P<den>\d+)(?:st|nd|rd|th)?)?\s*(?P<rest>.*)$',
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedUnit:
    amount: float          # how much one unit of the ingredient is
    measure: str           # canonical measure ('cup', 'f.oz'…) or the raw word
    floz: float | None     # the unit's volume in f.oz; None if not a volume

    @property
    def is_volume(self):
        return self.floz is not None


def parse_unit(text):
    '''Read an ingredient's Unit text ("3 cups", "8 f.oz", "1/2 tsp").
    Returns a ParsedUnit, or None when there's no leading amount at all
    (blank, "each"). A unit with an amount but a non-volume measure
    ("1 ea", "1 w.oz", "1/40th loaf") parses with floz=None.'''
    if not text:
        return None
    m = _AMOUNT_RE.match(text)
    if not m:
        return None
    try:
        amount = float(m['num'])
        if m['den']:
            amount /= float(m['den'])
        if m['whole']:
            amount += float(m['whole'])
    except (ValueError, ZeroDivisionError):
        return None
    if amount <= 0:
        return None
    word = re.sub(r'\s+', ' ', (m['rest'] or '').strip().lower()).rstrip('.')
    measure = _ALIASES.get(word) or _ALIASES.get(word.replace(' ', ''))
    if measure is None:
        return ParsedUnit(amount, word, None)
    return ParsedUnit(amount, measure, amount * _FLOZ_PER[measure])


# Weight measures an ingredient can be portioned in, besides volumes.
_WEIGHT_WORDS = {'w.oz', 'wt.oz', 'wt oz', 'g', 'gram', 'grams', 'lb', 'lbs', 'kg'}


def portioned_by_weight(unit_text, weight):
    '''True for an ingredient portioned by an amount ("3 f.oz", "1 cup",
    "1 w.oz") that has a weight: its nutrition and prices are kept per
    gram. Eggs, avocados, lemon wedges and packaging ("1 ea",
    "1/6th wedge", blank) are portioned per each.'''
    try:
        if not weight or float(weight) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    unit = parse_unit(unit_text)
    return unit is not None and (unit.floz is not None or unit.measure in _WEIGHT_WORDS)


def to_floz(amount, measure):
    '''A rule amount in fluid ounces, or None for an unknown measure.'''
    per = _FLOZ_PER.get(_ALIASES.get((measure or '').lower(), measure))
    return None if per is None or amount is None else float(amount) * per


@dataclass(frozen=True)
class Rule:
    mode: str              # 'base' | 'fixed'
    amount: float
    measure: str           # canonical measure, see RULE_MEASURES

    @property
    def floz(self):
        return to_floz(self.amount, self.measure)


def rule_quantities(rule, rows):
    '''Quantities for the rows of one category under one rule.

    `rows` is a list of (key, unit_text, share) for the rows that follow
    the rule. Returns {key: quantity}, with None for a row whose unit
    isn't a volume (it can't be sized and keeps its own quantity). For a
    base rule the total is split among the sizable rows by share; rows
    with a zero or missing share count as an equal 1.'''
    total = rule.floz
    out = {}
    sizable = []
    for key, unit_text, share in rows:
        unit = parse_unit(unit_text)
        if total is None or unit is None or not unit.is_volume:
            out[key] = None
        else:
            sizable.append((key, unit.floz, share if share and share > 0 else 1.0))
    if rule.mode == 'fixed':
        for key, unit_floz, _share in sizable:
            out[key] = total / unit_floz
    else:
        shares = sum(s for _k, _u, s in sizable)
        for key, unit_floz, share in sizable:
            out[key] = total * share / shares / unit_floz
    return out


def shares_from_quantities(rows):
    '''Shares that reproduce the current split of a category, by volume.
    `rows` is a list of (key, unit_text, quantity). Returns {key: share}
    for the rows with a volume unit, the shares summing to 1; rows that
    can't be sized are left out.'''
    volumes = {}
    for key, unit_text, qty in rows:
        unit = parse_unit(unit_text)
        if unit is not None and unit.is_volume and qty is not None:
            volumes[key] = max(float(qty), 0.0) * unit.floz
    total = sum(volumes.values())
    if not volumes:
        return {}
    if total <= 0:
        return {k: 1.0 / len(volumes) for k in volumes}
    return {k: v / total for k, v in volumes.items()}


def matches(current, derived, rel_tol=0.01, abs_tol=1e-6):
    '''True when a stored quantity already equals the rule's quantity.'''
    if current is None or derived is None:
        return False
    return abs(float(current) - derived) <= max(abs_tol, rel_tol * abs(derived))


def describe_unit(text):
    '''How portion rules read a Unit, for the ingredient editor:
    (True, "one unit = 24 f.oz (3 cups)") or (False/None, why not).'''
    unit = parse_unit(text)
    if unit is None:
        return None, 'This unit has no amount'
    if not unit.is_volume:
        return False, f'“{unit.measure or text.strip()}” isn’t a volume'
    cups = unit.floz / 8.0
    return True, f'one unit = {unit.floz:g} f.oz ({cups:.3g} cup{"" if cups == 1 else "s"})'


def format_amount(amount, measure):
    '''"3 cups", "0.5 cup", "3 f.oz".'''
    qty = f'{float(amount):.4f}'.rstrip('0').rstrip('.')
    unit = 'cups' if measure == 'cup' and float(amount) > 1 else measure
    return f'{qty} {unit}'


def describe_rule(category, mode, amount, measure):
    '''A rule in words, for the template editor and summaries.'''
    if mode == 'fixed':
        return f'Each {category} ingredient gets {format_amount(amount, measure)}.'
    return f'A recipe’s {category} share {format_amount(amount, measure)}.'


# Default rules, seeded once per format that has none (see migrateDB).
# (format name, category name, mode, amount, measure)
DEFAULT_RULES = (
    ('Salad', 'Greens', 'base', 3.0, 'cup'),
    ('Salad', 'Grains', 'fixed', 3.0, 'f.oz'),
    ('Bowl', 'Grains', 'base', 8.0, 'f.oz'),
    ('Bowl', 'Greens', 'fixed', 0.5, 'cup'),
    ('Wrap', 'Greens', 'base', 1.0, 'cup'),
    ('Wrap', 'Grains', 'base', 4.0, 'f.oz'),
)
