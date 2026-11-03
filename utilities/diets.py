'''Diets a recipe fits, worked out from its allergens and nutrition.

A diet rule excludes recipes containing any of its allergens and/or
needs a nutrient at least (or at most) some amount per serving. A
serving is one unit of the recipe's yield. Rules live in the library
(diets / diet_allergens, edited in Configure › Diets); DEFAULT_DIETS
seeds them once.

The current rules are a small registry: the Library model calls
set_rules(db.get_diets()) on refresh, and the filter pane, cards and
inspector read rules() / names(). No Qt here.
'''

# key, label, unit — the per-serving nutrients a rule can use.
NUTRIENTS = (
    ('Calories', 'Calories', 'kcal'),
    ('Protein', 'Protein', 'g'),
    ('Fiber', 'Fiber', 'g'),
    ('Carbs', 'Carbs', 'g'),
    ('Sugar', 'Sugar', 'g'),
    ('Fat', 'Fat', 'g'),
    ('SatFat', 'Saturated fat', 'g'),
    ('Sodium', 'Sodium', 'mg'),
    ('Cholesterol', 'Cholesterol', 'mg'),
)
NUTRIENT_LABELS = {k: label for k, label, _u in NUTRIENTS}
NUTRIENT_UNITS = {k: unit for k, _l, unit in NUTRIENTS}

# Seeds: key, name, excluded allergen names, nutrient, op ('min'/'max'), amount.
DEFAULT_DIETS = (
    ('vegan', 'Vegan', ('Meat', 'Fish', 'Shellfish', 'Dairy', 'Eggs'), None, 'min', None),
    ('vegetarian', 'Vegetarian', ('Meat', 'Fish', 'Shellfish'), None, 'min', None),
    ('dairy_free', 'Dairy-free', ('Dairy',), None, 'min', None),
    ('gluten_free', 'Gluten-free', ('Gluten',), None, 'min', None),
    ('high_protein', 'High protein', (), 'Protein', 'min', 30.0),
    ('high_fiber', 'High fiber', (), 'Fiber', 'min', 8.0),
)


def _rule(key, name, excluded=(), nutrient=None, op='min', amount=None):
    return {'key': key, 'name': name, 'excluded': list(excluded), 'nutrient': nutrient,
            'op': op or 'min', 'amount': amount}


_rules = [_rule(*d) for d in DEFAULT_DIETS]


def set_rules(rules):
    '''rules: [{key, name, excluded: [allergen names], nutrient, op, amount}].'''
    global _rules
    _rules = [dict(r) for r in rules]


def rules():
    return list(_rules)


def names():
    return {r['key']: r['name'] for r in _rules}


def _list(words):
    words = [w.lower() for w in words]
    return words[0] if len(words) == 1 else ', '.join(words[:-1]) + ' or ' + words[-1]


def describe(rule):
    '''"No meat, fish or dairy · 30 g protein or more per serving".'''
    parts = []
    if rule.get('excluded'):
        parts.append('No ' + _list(rule['excluded']))
    if rule.get('nutrient') and rule.get('amount') is not None:
        amount = '{:g}'.format(float(rule['amount']))
        unit = NUTRIENT_UNITS.get(rule['nutrient'], '')
        label = NUTRIENT_LABELS.get(rule['nutrient'], rule['nutrient']).lower()
        more = 'or more' if rule.get('op', 'min') == 'min' else 'or less'
        parts.append(f'{amount} {unit} {label} {more} per serving'.replace('  ', ' '))
    return ' · '.join(parts) or 'Every recipe fits (no rule yet)'


def fits(rule, allergens, per_serving):
    have = set(allergens or ())
    if rule.get('excluded') and have.intersection(rule['excluded']):
        return False
    if rule.get('nutrient') and rule.get('amount') is not None:
        value = float(per_serving.get(rule['nutrient']) or 0)
        amount = float(rule['amount'])
        if (rule.get('op', 'min') == 'min' and value < amount) or (rule.get('op') == 'max' and value > amount):
            return False
    return True


def diets_for(allergens, per_serving, rule_list=None):
    '''Keys of the diets a recipe fits, in rule order. `allergens` is
    an iterable of allergen names in the recipe's tree; `per_serving`
    maps NUTRIENTS keys to amounts per serving (missing = 0).'''
    return [r['key'] for r in (rule_list if rule_list is not None else _rules)
            if fits(r, allergens, per_serving)]


def excluded_by(allergen_names, rule_list=None):
    '''Names of the diets an ingredient with these allergens rules out.'''
    have = set(allergen_names or ())
    return [r['name'] for r in (rule_list if rule_list is not None else _rules)
            if have.intersection(r.get('excluded') or ())]
