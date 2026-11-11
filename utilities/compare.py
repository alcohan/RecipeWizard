'''The numbers behind Analytics › Pricing and Nutrition: recipes as rows,
per serving.

Framework-agnostic. The input is db.get_recipe_category_details() (one
row per ingredient appearance, already per serving) plus the Library's
recipe rows (menu price, allergens). build() pivots them into one entry
per recipe; pricing_csv() and nutrition_csv() are what Export CSV
writes, and averages() is the footer row.
'''
from collections import defaultdict


UNCATEGORIZED = '(uncategorized)'

# The Nutrition columns, in Nutrition Facts order: key (a column of the
# details query), label, unit.
NUTRIENTS = [
    ('weight', 'Weight', 'g'),
    ('calories', 'Calories', ''),
    ('fat', 'Fat', 'g'),
    ('sat_fat', 'Sat fat', 'g'),
    ('cholesterol', 'Cholesterol', 'mg'),
    ('sodium', 'Sodium', 'mg'),
    ('carbs', 'Carbs', 'g'),
    ('fiber', 'Fiber', 'g'),
    ('sugar', 'Sugar', 'g'),
    ('protein', 'Protein', 'g'),
]
_SUMMED = ('cost',) + tuple(k for k, _l, _u in NUTRIENTS)


def fmt(value, unit, decimals=0):
    '''"$3.42", "1,340 mg", "640"; None is "—".'''
    if value is None:
        return '—'
    if unit == '$':
        return f'${value:,.2f}'
    if unit == '%':
        return f'{value:.1f}%'
    if decimals == 0 and 0 < abs(value) < 10 and unit:
        text = f'{value:.1f}'
    else:
        text = f'{value:,.{decimals}f}'
    return f'{text} {unit}' if unit else text


def category_order(ingredient_tags):
    '''Category names in wedge order (Configure's order), uncategorized last.'''
    return [t['name'] for t in ingredient_tags] + [UNCATEGORIZED]


def build(detail_rows, recipe_rows, recipe_ids, categories):
    '''One entry per recipe id (in the order given, unknown ids dropped):

        {id, name, format, archived, menu_price, allergens, facility,
         totals: {cost and each nutrient, per serving},
         cost, pct (food cost %, None without a menu price),
         categories: {category: cost},
         items: {category: [ingredient name]} (sorted, distinct),
         ingredients: [ingredient name] (distinct, in category order)}

    plus the categories that appear, in category order:
    {'recipes': [...], 'categories': [name]}.'''
    by_id = {r['Id']: r for r in recipe_rows}
    wanted = [rid for rid in recipe_ids if rid in by_id]
    per = {rid: {'totals': defaultdict(float), 'cats': defaultdict(float), 'items': defaultdict(set)}
           for rid in wanted}
    for d in detail_rows:
        entry = per.get(d['recipe_id'])
        if entry is None:
            continue
        for key in _SUMMED:
            entry['totals'][key] += float(d.get(key) or 0)
        entry['cats'][d['category']] += float(d.get('cost') or 0)
        entry['items'][d['category']].add(d['ingredient_name'])

    order = {name: i for i, name in enumerate(categories)}
    sort_cats = lambda cats: sorted(cats, key=lambda c: (order.get(c, 1e6), c))
    recipes, used = [], set()
    for rid in wanted:
        row, entry = by_id[rid], per[rid]
        cats = sort_cats(entry['items'])
        used.update(cats)
        items = {c: sorted(entry['items'][c], key=str.lower) for c in cats}
        cost = entry['totals'].get('cost', 0.0)
        price = _num(row.get('MenuPrice'))
        recipes.append({
            'id': rid, 'name': row['Name'], 'format': row.get('TagName'),
            'archived': bool(row.get('Archived')), 'menu_price': price,
            'allergens': list(row.get('Allergens') or []),
            'facility': list(row.get('FacilityAllergens') or []),
            'totals': {k: entry['totals'].get(k, 0.0) for k in _SUMMED},
            'cost': cost, 'pct': cost / price * 100 if price else None,
            'categories': {c: entry['cats'][c] for c in cats},
            'items': items,
            'ingredients': [n for c in cats for n in items[c]],
        })
    return {'recipes': recipes, 'categories': sort_cats(used)}


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def averages(data):
    '''The footer: {'cost', 'menu_price', 'pct', 'categories': {c: avg},
    nutrient keys...}. Category averages count recipes without that
    category as $0; price and % average only the priced recipes.'''
    recipes = data['recipes']
    if not recipes:
        return {'cost': None, 'menu_price': None, 'pct': None, 'categories': {},
                **{k: None for k, _l, _u in NUTRIENTS}}
    out = {'cost': _mean([r['cost'] for r in recipes]),
           'menu_price': _mean([r['menu_price'] for r in recipes]),
           'pct': _mean([r['pct'] for r in recipes]),
           'categories': {c: _mean([r['categories'].get(c, 0.0) for r in recipes]) for c in data['categories']}}
    for key, _label, _unit in NUTRIENTS:
        out[key] = _mean([r['totals'][key] for r in recipes])
    return out


def nutrient_header(label, unit):
    return f'{label} ({unit})' if unit else label


def _round(v, places=2):
    return '' if v is None else round(v, places)


def pricing_csv(data):
    '''Recipe, Template, Ingredients, Ingredient list, a cost column per
    category, Food cost, Menu price, Food cost %; an Average row last.'''
    cats = data['categories']
    out = [['Recipe', 'Template', 'Ingredients', 'Ingredient list'] + cats
           + ['Food cost', 'Menu price', 'Food cost %']]
    for r in data['recipes']:
        out.append([r['name'], r['format'] or '', len(r['ingredients']), '; '.join(r['ingredients'])]
                   + [_round(r['categories'].get(c)) if c in r['categories'] else '' for c in cats]
                   + [_round(r['cost']), _round(r['menu_price']), _round(r['pct'], 1)])
    if data['recipes']:
        avg = averages(data)
        out.append(['Average', '', '', ''] + [_round(avg['categories'][c]) for c in cats]
                   + [_round(avg['cost']), _round(avg['menu_price']), _round(avg['pct'], 1)])
    return out


def nutrition_csv(data):
    '''Recipe, Template, each nutrient per serving, Contains, Facility;
    an Average row last.'''
    out = [['Recipe', 'Template'] + [nutrient_header(label, unit) for _k, label, unit in NUTRIENTS]
           + ['Contains', 'Facility']]
    for r in data['recipes']:
        out.append([r['name'], r['format'] or ''] + [_round(r['totals'][k], 1) for k, _l, _u in NUTRIENTS]
                   + [', '.join(r['allergens']), ', '.join(r['facility'])])
    if data['recipes']:
        avg = averages(data)
        out.append(['Average', ''] + [_round(avg[k], 1) for k, _l, _u in NUTRIENTS] + ['', ''])
    return out
