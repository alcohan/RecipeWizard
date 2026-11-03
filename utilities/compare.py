'''The numbers behind Analytics: a few recipes compared side by side.

Framework-agnostic. The input is db.get_recipe_category_details() (one
row per ingredient appearance, already per serving) plus the Library's
recipe rows (menu price, allergens). build() pivots them into one entry
per recipe for a metric (cost, calories, ...), a basis (per serving,
per 100 g, per $1 of menu price) and a values mode (amounts or % of the
recipe's total); insight() says the one or two things worth noticing,
and matrix() lays out the side-by-side table, which is also what
Export CSV writes.
'''
from collections import defaultdict


UNCATEGORIZED = '(uncategorized)'

# key, label, unit, decimals. The key is the column in the details query.
METRICS = [
    ('cost', 'Cost', '$', 2),
    ('calories', 'Calories', '', 0),
    ('protein', 'Protein', 'g', 0),
    ('fat', 'Fat', 'g', 0),
    ('carbs', 'Carbs', 'g', 0),
    ('sodium', 'Sodium', 'mg', 0),
    ('weight', 'Weight', 'g', 0),
]
BASES = [('serving', 'serving'), ('100g', '100 g'), ('price', '$1 of menu price')]
VALUES = [('amount', 'amount'), ('pct', '% of total')]
DEFAULT_SETTINGS = {'metric': 'cost', 'basis': 'serving', 'values': 'amount'}

# The Nutrition rows of the matrix: label, keys (a second key joins with " · "), unit.
NUTRITION_ROWS = [
    ('Calories', ('calories',), ''),
    ('Protein', ('protein',), 'g'),
    ('Fat', ('fat',), 'g'),
    ('Carbs · fiber', ('carbs', 'fiber'), 'g'),
    ('Sodium', ('sodium',), 'mg'),
    ('Cholesterol', ('cholesterol',), 'mg'),
]
_SUMMED = ('cost', 'weight', 'calories', 'protein', 'fat', 'carbs', 'fiber', 'sodium', 'cholesterol')


def metric_info(key):
    return next(m for m in METRICS if m[0] == key)


def basis_label(basis):
    return 'Per ' + dict(BASES)[basis]


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


def fmt_metric(value, metric, values='amount'):
    if values == 'pct':
        return fmt(value, '%')
    _key, _label, unit, decimals = metric_info(metric)
    return fmt(value, unit, decimals)


def category_order(ingredient_tags):
    '''Category names in wedge order (Configure's order), uncategorized last.'''
    return [t['name'] for t in ingredient_tags] + [UNCATEGORIZED]


def build(detail_rows, recipe_rows, recipe_ids, categories, colors=None,
          metric='cost', basis='serving', values='amount'):
    '''One entry per recipe id (in the order given, unknown ids dropped):

        {id, name, unit, archived, menu_price, allergens,
         totals: {nutrient: per serving}, factor (None = no basis),
         total (the metric on the basis, None without one),
         segments: [(category, value, share)] in category order, value on
             the basis (or a % in pct mode), share of the recipe's total,
         items: {category: [(ingredient, value)]} on the basis}

    plus the categories that appear and their colors:
    {'recipes': [...], 'categories': [(name, color)]}.
    '''
    by_id = {r['Id']: r for r in recipe_rows}
    colors = dict(colors or {})
    wanted = [rid for rid in recipe_ids if rid in by_id]
    per = {rid: {'totals': defaultdict(float), 'cats': defaultdict(float), 'items': defaultdict(list)}
           for rid in wanted}
    for d in detail_rows:
        entry = per.get(d['recipe_id'])
        if entry is None:
            continue
        for key in _SUMMED:
            entry['totals'][key] += float(d.get(key) or 0)
        value = float(d.get(metric) or 0)
        entry['cats'][d['category']] += value
        entry['items'][d['category']].append((d['ingredient_name'], value))
        colors.setdefault(d['category'], d.get('color') or '#888888')

    order = {name: i for i, name in enumerate(categories)}
    recipes = []
    used = set()
    for rid in wanted:
        row, entry = by_id[rid], per[rid]
        factor = basis_factor(basis, entry['totals'].get('weight', 0.0), row.get('MenuPrice'))
        raw_total = sum(entry['cats'].values())
        cats = sorted((c for c, v in entry['cats'].items() if v > 0), key=lambda c: (order.get(c, 1e6), c))
        used.update(cats)
        segments = []
        for c in cats:
            raw = entry['cats'][c]
            share = raw / raw_total if raw_total > 0 else 0.0
            if values == 'pct':
                value = share * 100
            else:
                value = raw * factor if factor is not None else None
            segments.append((c, value, share))
        items = {c: sorted(((n, v * factor if factor is not None else None) for n, v in entry['items'][c]),
                           key=lambda x: -(x[1] or 0))
                 for c in cats}
        recipes.append({
            'id': rid, 'name': row['Name'], 'unit': row.get('Unit'), 'archived': bool(row.get('Archived')),
            'menu_price': _num(row.get('MenuPrice')), 'allergens': list(row.get('Allergens') or []),
            'totals': dict(entry['totals']), 'factor': factor,
            'total': raw_total * factor if factor is not None else None,
            'segments': segments, 'items': items,
        })
    cats = [(c, colors.get(c, '#888888')) for c in sorted(used, key=lambda c: (order.get(c, 1e6), c))]
    return {'recipes': recipes, 'categories': cats, 'metric': metric, 'basis': basis, 'values': values}


def basis_factor(basis, weight_g, menu_price):
    '''What a per-serving value is multiplied by; None when the recipe
    has no weight (per 100 g) or no menu price (per $1).'''
    if basis == '100g':
        return 100.0 / weight_g if weight_g and weight_g > 0 else None
    if basis == 'price':
        price = _num(menu_price)
        return 1.0 / price if price else None
    return 1.0


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _names(names):
    names = list(names)
    if len(names) <= 2:
        return ' and '.join(names)
    return ', '.join(names[:-1]) + ' and ' + names[-1]


def _count_word(n):
    return {2: 'both', 3: 'all three', 4: 'all four', 5: 'all five'}.get(n, f'all {n}')


def insight(data):
    '''A sentence or two about the comparison: which category is the
    largest slice, who is highest and lowest, and which category
    differs most between them. '' when there's nothing to say.'''
    recipes = [r for r in data['recipes'] if r['segments'] and r['total']]
    if not recipes:
        return ''
    metric = data['metric']
    label = metric_info(metric)[1].lower()
    show = lambda v: fmt_metric(v, metric)
    tops = {}
    for r in recipes:
        top = max(r['segments'], key=lambda s: s[2])[0]
        tops.setdefault(top, []).append(r['name'])
    parts = []
    if len(tops) == 1:
        (top, names), = tops.items()
        if len(recipes) == 1:
            share = max(s[2] for s in recipes[0]['segments'])
            parts.append(f'{top} is the largest slice of {label}, {share * 100:.0f}% of the total.')
        else:
            parts.append(f'{top} is the largest slice of {label} in {_count_word(len(recipes))}.')
    else:
        bits = [f'{top} in {_names(names)}' for top, names in tops.items()]
        parts.append(f'The largest slice of {label} is ' + '; '.join(bits) + '.')
    if len(recipes) >= 2:
        hi = max(recipes, key=lambda r: r['total'])
        lo = min(recipes, key=lambda r: r['total'])
        if hi['total'] > lo['total']:
            parts.append(f"{hi['name']} is highest at {show(hi['total'])}, {lo['name']} lowest at "
                         f"{show(lo['total'])}.")
            # The category whose amount differs most explains the gap.
            amounts = defaultdict(dict)
            for r in recipes:
                for c, _v, share in r['segments']:
                    amounts[c][r['id']] = share * r['total']
            spread = {c: max(v.get(r['id'], 0.0) for r in recipes) - min(v.get(r['id'], 0.0) for r in recipes)
                      for c, v in amounts.items()}
            cat = max(spread, key=spread.get)
            if spread[cat] > 0:
                low = min(amounts[cat].get(r['id'], 0.0) for r in recipes)
                high = max(amounts[cat].values())
                parts.append(f'{cat} differs most, from {show(low)} to {show(high)}.')
    return ' '.join(parts)


def matrix(data):
    '''The side-by-side table as rows of
    {kind: 'section'|'category'|'total'|'price'|'nutrient'|'allergens',
     label, color (categories), values: [number or None per recipe],
     text: [display text per recipe], warn: [bool per recipe] (price)}.'''
    recipes, metric, values = data['recipes'], data['metric'], data['values']
    _key, mlabel, unit, decimals = metric_info(metric)
    rows = []
    for cat, color in data['categories']:
        vals = []
        for r in recipes:
            seg = next((s for s in r['segments'] if s[0] == cat), None)
            vals.append(seg[1] if seg else None)
        rows.append({'kind': 'category', 'label': cat, 'color': color, 'values': vals,
                     'text': [fmt_metric(v, metric, values) if v is not None else '—' for v in vals]})
    totals = [r['total'] for r in recipes]
    rows.append({'kind': 'total', 'label': f'Total {mlabel.lower()}', 'values': totals,
                 'text': [fmt(v, unit, decimals) for v in totals]})
    target = data.get('target')
    price_text, warn, pct_vals = [], [], []
    for r in recipes:
        cost = r['totals'].get('cost', 0.0)
        if r['menu_price']:
            pct = cost / r['menu_price'] * 100
            price_text.append(f"{fmt(r['menu_price'], '$')} · {pct:.1f}%")
            warn.append(target is not None and pct > target)
            pct_vals.append(pct)
        else:
            price_text.append('No menu price')
            warn.append(False)
            pct_vals.append(None)
    rows.append({'kind': 'price', 'label': 'Menu price · food cost', 'values': pct_vals, 'text': price_text,
                 'warn': warn})

    rows.append({'kind': 'section', 'label': 'Nutrition'})
    for label, keys, nunit in NUTRITION_ROWS:
        vals, text = [], []
        for r in recipes:
            nums = [r['totals'].get(k, 0.0) * r['factor'] if r['factor'] is not None else None for k in keys]
            vals.append(nums[0])
            if nums[0] is None:
                text.append('—')
            elif len(nums) == 1:
                text.append(fmt(nums[0], nunit))
            else:
                text.append(' · '.join(f'{n:,.0f}' for n in nums) + f' {nunit}')
        rows.append({'kind': 'nutrient', 'label': label, 'values': vals, 'text': text})

    rows.append({'kind': 'section', 'label': 'Allergens'})
    rows.append({'kind': 'allergens', 'label': 'Contains', 'values': [None] * len(recipes),
                 'text': [', '.join(r['allergens']) or 'None' for r in recipes]})
    return rows


def csv_rows(data):
    '''The matrix as plain rows for a CSV: a header of recipe names, then
    one row per line of the table with raw numbers (rounded), section
    rows included as labels.'''
    recipes = data['recipes']
    out = [[basis_label(data['basis'])] + [r['name'] for r in recipes]]
    for row in matrix(data):
        if row['kind'] == 'section':
            out.append([row['label']] + [''] * len(recipes))
        elif row['kind'] in ('allergens', 'price'):
            out.append([row['label']] + row['text'])
        elif row['kind'] == 'nutrient' and row['label'] == 'Carbs · fiber':
            out.append([row['label']] + [t if t != '—' else '' for t in row['text']])
        else:
            out.append([row['label']] + ['' if v is None else round(v, 2) for v in row['values']])
    return out


def nice_ticks(maximum, count=3):
    '''Axis ticks from 0 covering `maximum` in about `count` steps of
    1, 1.5, 2, 2.5 or 5 × a power of ten.'''
    if not maximum or maximum <= 0:
        return [0.0, 1.0]
    raw = maximum / count
    power = 10 ** _floor_log10(raw)
    step = next(m * power for m in (1, 1.5, 2, 2.5, 5, 10) if m * power >= raw)
    ticks = [0.0]
    while ticks[-1] < maximum - 1e-9:
        ticks.append(round(ticks[-1] + step, 10))
    return ticks


def _floor_log10(x):
    n = 0
    while x >= 10:
        x /= 10
        n += 1
    while x < 1:
        x *= 10
        n -= 1
    return n
