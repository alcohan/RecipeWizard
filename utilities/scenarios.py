'''Scenarios: what-if layers over the baseline (an airport store's
packaging and menu prices, take-out vs in-store packaging).

A scenario is a list of rules, each scoped to one format (template) or
to every recipe:

  substitute   use `to` wherever the recipe uses `from`; quantity is the
               ratio of the replaced amount (NULL: the same amount)
  add          add `to` x quantity, counted like a template item
  remove       drop `from`
  price_adjust menu price + amount ($)

Recipes carrying an excluded tag skip a rule, or with a scenario-level
exclusion are left out of the scenario. A per-recipe scenario price
wins over price_adjust.

Precedence: on the same target (a `from` ingredient for substitute /
remove, a `to` ingredient for add, the price for price_adjust) a rule
for the recipe's format beats a rule for every recipe; among equals the
first in order wins.

The matrix is computed from a read-only connection: scenarios never
change recipes, components, ingredients or menu prices. Only the CRUD
functions below write, and only to the scenario tables.
'''
import pathlib
import sqlite3

import config

ACTIONS = ('substitute', 'add', 'remove', 'price_adjust')


# --- connections ----------------------------------------------------------

def _connect(path=None):
    con = sqlite3.connect(path or config.DATABASE)
    con.row_factory = sqlite3.Row
    return con


def _connect_ro(path=None):
    uri = pathlib.Path(path or config.DATABASE).resolve().as_uri() + '?mode=ro'
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _marks(values):
    return ', '.join('?' for _ in values)


# --- the matrix -----------------------------------------------------------

def matrix(recipe_ids=None, scenario_ids=None, path=None):
    '''Cost, menu price and food cost % for each recipe under the
    baseline and each scenario.

    recipe_ids: None = every active recipe. scenario_ids: None = all,
    in their order.

    {'scenarios': [{id, name}],
     'recipes': [{id, name, format_id,
                  'base': {cost, price, pct},
                  'cells': {scenario_id: {cost, price, pct, excluded,
                            applied: [{rule_id, action, delta}]}}}]}

    pct is None without a menu price; an excluded cell has cost, price
    and pct None.'''
    con = _connect_ro(path)
    try:
        data = _load(con, recipe_ids, scenario_ids)
    finally:
        con.close()
    return compute(data)


def _load(con, recipe_ids, scenario_ids):
    if scenario_ids is None:
        scenarios = [dict(r) for r in con.execute(
            'SELECT id, name FROM scenarios ORDER BY COALESCE(sortOrder, id), id;')]
    else:
        ids = list(scenario_ids)
        found = {r['id']: dict(r) for r in con.execute(
            f'SELECT id, name FROM scenarios WHERE id IN ({_marks(ids)});', ids)}
        scenarios = [found[i] for i in ids if i in found]
    sids = [s['id'] for s in scenarios]

    if recipe_ids is None:
        rows = con.execute(
            "SELECT r.Id, r.Name, r.OutputQty, r.menu_price, COALESCE(t.Cost, 0) AS Cost"
            " FROM Recipes r LEFT JOIN RecipeTotalValues t ON t.Id = r.Id"
            " WHERE COALESCE(r.status, 'active') = 'active' ORDER BY r.Name COLLATE NOCASE;").fetchall()
    else:
        ids = list(recipe_ids)
        found = {r['Id']: r for r in con.execute(
            "SELECT r.Id, r.Name, r.OutputQty, r.menu_price, COALESCE(t.Cost, 0) AS Cost"
            f" FROM Recipes r LEFT JOIN RecipeTotalValues t ON t.Id = r.Id WHERE r.Id IN ({_marks(ids)});",
            ids)}
        rows = [found[i] for i in ids if i in found]
    recipes = [{'id': r['Id'], 'name': r['Name'], 'output': r['OutputQty'],
                'price': r['menu_price'], 'cost': float(r['Cost'] or 0)} for r in rows]
    rids = [r['id'] for r in recipes]

    tags, formats = {}, {}
    if rids:
        for row in con.execute(
                'SELECT m.recipe_id, m.tag_id, t.kind FROM recipe_tags_mapping m'
                f' JOIN tags t ON t.id = m.tag_id WHERE m.recipe_id IN ({_marks(rids)});', rids):
            tags.setdefault(row['recipe_id'], set()).add(row['tag_id'])
            if row['kind'] == 'recipe':
                formats.setdefault(row['recipe_id'], row['tag_id'])

    rules, exclusions, prices = [], [], {}
    if sids:
        rules = [dict(r) for r in con.execute(
            f'SELECT * FROM scenario_rules WHERE scenario_id IN ({_marks(sids)})'
            ' ORDER BY COALESCE(sortOrder, id), id;', sids)]
        exclusions = [dict(r) for r in con.execute(
            f'SELECT scenario_id, rule_id, tag_id FROM scenario_exclusions WHERE scenario_id IN ({_marks(sids)});',
            sids)]
        for row in con.execute(
                f'SELECT scenario_id, recipe_id, menu_price FROM scenario_prices WHERE scenario_id IN ({_marks(sids)});',
                sids):
            prices[(row['scenario_id'], row['recipe_id'])] = row['menu_price']

    ing_ids = sorted({i for r in rules for i in (r['from_ingredient'], r['to_ingredient']) if i is not None})
    costs, usage = {}, {}
    if ing_ids:
        for row in con.execute(f'SELECT Id, Cost FROM Ingredients WHERE Id IN ({_marks(ing_ids)});', ing_ids):
            costs[row['Id']] = float(row['Cost'] or 0)
        from_ids = sorted({r['from_ingredient'] for r in rules if r['from_ingredient'] is not None})
        if from_ids and rids:
            for row in con.execute(
                    'SELECT recipe_id, ingredient_id, SUM(Quantity) AS q FROM recipe_ingredients_expanded'
                    f' WHERE ingredient_id IN ({_marks(from_ids)}) AND recipe_id IN ({_marks(rids)})'
                    ' GROUP BY recipe_id, ingredient_id;', from_ids + rids):
                usage[(row['recipe_id'], row['ingredient_id'])] = float(row['q'] or 0)

    return {'scenarios': scenarios, 'recipes': recipes, 'tags': tags, 'formats': formats,
            'rules': rules, 'exclusions': exclusions, 'prices': prices,
            'costs': costs, 'usage': usage}


def _target(rule):
    if rule['action'] in ('substitute', 'remove'):
        return ('line', rule['from_ingredient'])
    if rule['action'] == 'add':
        return ('add', rule['to_ingredient'])
    return ('price',)


def _pct(cost, price):
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    return cost / price * 100 if price > 0 else None


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compute(data):
    '''The matrix from loaded data (see _load); pure, for testing.'''
    rule_tags, scenario_tags = {}, {}
    for ex in data['exclusions']:
        if ex['rule_id'] is None:
            scenario_tags.setdefault(ex['scenario_id'], set()).add(ex['tag_id'])
        else:
            rule_tags.setdefault(ex['rule_id'], set()).add(ex['tag_id'])
    by_scenario = {}
    for rule in data['rules']:
        if rule['action'] in ACTIONS:
            by_scenario.setdefault(rule['scenario_id'], []).append(rule)
    costs, usage = data['costs'], data['usage']

    out = []
    for r in data['recipes']:
        rid, fmt = r['id'], data['formats'].get(r['id'])
        tags = data['tags'].get(rid, set())
        output = _num(r['output']) or 0
        base_price = _num(r['price'])
        entry = {'id': rid, 'name': r['name'], 'format_id': fmt, 'tags': sorted(tags),
                 'base': {'cost': r['cost'], 'price': base_price, 'pct': _pct(r['cost'], base_price)},
                 'cells': {}}
        for s in data['scenarios']:
            sid = s['id']
            if tags & scenario_tags.get(sid, set()):
                entry['cells'][sid] = {'cost': None, 'price': None, 'pct': None,
                                       'excluded': True, 'applied': []}
                continue
            chosen = {}
            for rule in by_scenario.get(sid, ()):
                scope = rule['format_tag_id']
                if scope is not None and scope != fmt:
                    continue
                if tags & rule_tags.get(rule['id'], set()):
                    continue
                key = _target(rule)
                have = chosen.get(key)
                if have is None or (have['format_tag_id'] is None and scope is not None):
                    chosen[key] = rule
            cost, adjust, applied = r['cost'], 0.0, []
            for rule in sorted(chosen.values(), key=lambda x: (x['sortOrder'] is None, x['sortOrder'], x['id'])):
                action, delta = rule['action'], 0.0
                if action == 'price_adjust':
                    adjust += _num(rule['amount']) or 0
                    applied.append({'rule_id': rule['id'], 'action': action, 'delta': _num(rule['amount']) or 0})
                    continue
                if not output:
                    continue
                parts = []      # [(ingredient id, signed $ per unit)]: what moved the cost
                if action == 'add':
                    qty = _num(rule['quantity'])
                    delta = costs.get(rule['to_ingredient'], 0) * (1 if qty is None else qty) / output
                    parts = [(rule['to_ingredient'], delta)]
                else:
                    used = usage.get((rid, rule['from_ingredient']))
                    if not used:
                        continue
                    old = costs.get(rule['from_ingredient'], 0) * used
                    if action == 'remove':
                        delta = -old / output
                        parts = [(rule['from_ingredient'], delta)]
                    else:
                        ratio = _num(rule['quantity'])
                        new = costs.get(rule['to_ingredient'], 0) * used * (1 if ratio is None else ratio)
                        delta = (new - old) / output
                        parts = [(rule['from_ingredient'], -old / output), (rule['to_ingredient'], new / output)]
                cost += delta
                applied.append({'rule_id': rule['id'], 'action': action, 'delta': delta, 'parts': parts})
            override = data['prices'].get((sid, rid))
            if override is not None:
                price = _num(override)
            elif base_price is not None:
                price = base_price + adjust
            else:
                price = None
            entry['cells'][sid] = {'cost': cost, 'price': price, 'pct': _pct(cost, price),
                                   'excluded': False, 'applied': applied}
        out.append(entry)
    return {'scenarios': [{'id': s['id'], 'name': s['name']} for s in data['scenarios']], 'recipes': out}


def ingredient_changes(cell):
    '''[(ingredient id, signed $ per unit)] behind a cell's cost change,
    one line per ingredient, largest first; price rules aren't cost.'''
    total = {}
    for a in cell.get('applied') or ():
        for ing, amount in a.get('parts') or ():
            total[ing] = total.get(ing, 0.0) + amount
    return sorted(((i, v) for i, v in total.items() if abs(v) >= 0.005), key=lambda kv: -abs(kv[1]))


def _money(value, signed=False):
    if signed:
        return f'{"+" if value >= 0 else "−"}${abs(value):,.2f}'
    return f'${value:,.2f}'


def describe_rule(rule, ingredient_names, tag_names=None):
    """A rule in words: "Swap Salad Bowl 32oz → Airport Salad Bowl ·
    except Kids". `rule` may carry except_tags (from get_scenarios)."""
    name = ingredient_names.get
    action, q = rule['action'], rule.get('quantity')
    if action == 'substitute':
        text = f'Swap {name(rule["from_ingredient"], "?")} → {name(rule["to_ingredient"], "?")}'
        if q is not None and q != 1:
            text += f' × {q:g}'
    elif action == 'add':
        text = f'Add {name(rule["to_ingredient"], "?")} × {1 if q is None else q:g}'
    elif action == 'remove':
        text = f'Remove {name(rule["from_ingredient"], "?")}'
    else:
        text = f'Menu price {_money(rule.get("amount") or 0, signed=True)}'
    if rule.get('except_tags'):
        tags = tag_names or {}
        text += ' · except ' + ', '.join(tags.get(t, '?') for t in rule['except_tags'])
    return text


CSV_HEADER = ('Recipe', 'Template', 'Scenario', 'Cost', 'Menu price', 'Food cost %',
              'Cost change', 'Food cost change (pts)', 'Left out')


def csv_rows(result, format_names=None):
    """The matrix flattened: a header, then one row per recipe for the
    baseline and each scenario."""
    names = format_names or {}

    def num(v, places=2):
        return '' if v is None else round(v, places)

    rows = [list(CSV_HEADER)]
    for r in result['recipes']:
        base, fmt = r['base'], names.get(r['format_id'], '')
        rows.append([r['name'], fmt, 'Baseline', num(base['cost']), num(base['price']), num(base['pct'], 1),
                     '', '', ''])
        for s in result['scenarios']:
            c = r['cells'][s['id']]
            if c['excluded']:
                rows.append([r['name'], fmt, s['name'], '', '', '', '', '', 'Yes'])
                continue
            dpct = None if c['pct'] is None or base['pct'] is None else c['pct'] - base['pct']
            rows.append([r['name'], fmt, s['name'], num(c['cost']), num(c['price']), num(c['pct'], 1),
                         num(c['cost'] - base['cost']), num(dpct, 1), ''])
    return rows


def averages(result, recipe_ids=None):
    """Average food cost % for the baseline and each scenario over the
    priced recipes shown: {'base': pct, scenario_id: pct} (None if no
    recipe has a price)."""
    keep = None if recipe_ids is None else set(recipe_ids)
    rows = [r for r in result['recipes'] if keep is None or r['id'] in keep]

    def avg(values):
        values = [v for v in values if v is not None]
        return sum(values) / len(values) if values else None

    out = {'base': avg(r['base']['pct'] for r in rows)}
    for s in result['scenarios']:
        out[s['id']] = avg(r['cells'][s['id']]['pct'] for r in rows if not r['cells'][s['id']]['excluded'])
    return out


def _names_using(sql, params, path=None):
    con = _connect(path)
    try:
        return [r[0] for r in con.execute(sql, params)]
    finally:
        con.close()


def ingredient_uses(ingredient_id, path=None):
    '''Names of the scenarios with a rule that uses this ingredient.'''
    return _names_using(
        'SELECT name FROM scenarios WHERE id IN (SELECT scenario_id FROM scenario_rules'
        ' WHERE from_ingredient = ? OR to_ingredient = ?) ORDER BY COALESCE(sortOrder, id), id;',
        (ingredient_id, ingredient_id), path)


def tag_uses(tag_id, path=None):
    '''Names of the scenarios with a rule for this format or that leave
    out recipes with this tag.'''
    return _names_using(
        'SELECT name FROM scenarios WHERE id IN (SELECT scenario_id FROM scenario_rules WHERE format_tag_id = ?'
        ' UNION SELECT scenario_id FROM scenario_exclusions WHERE tag_id = ?)'
        ' ORDER BY COALESCE(sortOrder, id), id;', (tag_id, tag_id), path)


def names_text(names, limit=3):
    '''"SeaTac", "SeaTac and Take-out", "A, B, C and 2 more".'''
    names = list(names)
    if len(names) <= limit:
        return ' and '.join(filter(None, [', '.join(names[:-1]), names[-1] if names else '']))
    return f'{", ".join(names[:limit])} and {len(names) - limit} more'


# --- editing (scenario tables only) --------------------------------------

def _write(fn, path=None):
    con = _connect(path)
    try:
        result = fn(con)
        con.commit()
        return result
    finally:
        con.close()


def get_scenarios(path=None):
    '''[{id, name, rules, exclusions, prices}] in order. rules carry their
    own `except_tags`; exclusions are the scenario-level tag ids; prices
    is {recipe_id: menu_price}.'''
    con = _connect(path)
    try:
        out = []
        for s in con.execute('SELECT id, name FROM scenarios ORDER BY COALESCE(sortOrder, id), id;'):
            sid = s['id']
            ex = con.execute('SELECT rule_id, tag_id FROM scenario_exclusions WHERE scenario_id = ? ORDER BY id;',
                             (sid,)).fetchall()
            rules = [dict(r, except_tags=[e['tag_id'] for e in ex if e['rule_id'] == r['id']])
                     for r in con.execute('SELECT * FROM scenario_rules WHERE scenario_id = ?'
                                          ' ORDER BY COALESCE(sortOrder, id), id;', (sid,))]
            prices = {r['recipe_id']: r['menu_price'] for r in con.execute(
                'SELECT recipe_id, menu_price FROM scenario_prices WHERE scenario_id = ?;', (sid,))}
            out.append({'id': sid, 'name': s['name'], 'rules': rules,
                        'exclusions': [e['tag_id'] for e in ex if e['rule_id'] is None], 'prices': prices})
        return out
    finally:
        con.close()


def create_scenario(name, path=None):
    def go(con):
        order = con.execute('SELECT COALESCE(MAX(sortOrder), 0) + 1 FROM scenarios;').fetchone()[0]
        return con.execute('INSERT INTO scenarios (name, sortOrder) VALUES (?, ?);', (name, order)).lastrowid
    return _write(go, path)


def rename_scenario(scenario_id, name, path=None):
    _write(lambda con: con.execute('UPDATE scenarios SET name = ? WHERE id = ?;', (name, scenario_id)), path)


def delete_scenario(scenario_id, path=None):
    '''Its rules, exclusions and prices go with it (triggers).'''
    _write(lambda con: con.execute('DELETE FROM scenarios WHERE id = ?;', (scenario_id,)), path)


def reorder_scenarios(ids, path=None):
    def go(con):
        for order, sid in enumerate(ids, start=1):
            con.execute('UPDATE scenarios SET sortOrder = ? WHERE id = ?;', (order, sid))
    _write(go, path)


def duplicate_scenario(scenario_id, name, path=None):
    snap = snapshot(scenario_id, path)
    new_id = create_scenario(name, path)
    restore(new_id, snap, path)
    return new_id


def _check_rule(action, from_ingredient, to_ingredient):
    if action not in ACTIONS:
        raise ValueError(f'Unknown scenario action: {action!r}')
    if action in ('substitute', 'remove') and from_ingredient is None:
        raise ValueError(f'{action} needs an ingredient to replace')
    if action in ('substitute', 'add') and to_ingredient is None:
        raise ValueError(f'{action} needs an ingredient to use')


def add_rule(scenario_id, action, format_tag_id=None, from_ingredient=None, to_ingredient=None,
             quantity=None, amount=None, except_tags=(), path=None):
    _check_rule(action, from_ingredient, to_ingredient)

    def go(con):
        order = con.execute('SELECT COALESCE(MAX(sortOrder), 0) + 1 FROM scenario_rules WHERE scenario_id = ?;',
                            (scenario_id,)).fetchone()[0]
        rule_id = con.execute(
            'INSERT INTO scenario_rules (scenario_id, format_tag_id, action, from_ingredient, to_ingredient,'
            ' quantity, amount, sortOrder) VALUES (?, ?, ?, ?, ?, ?, ?, ?);',
            (scenario_id, format_tag_id, action, from_ingredient, to_ingredient, quantity, amount, order)).lastrowid
        _set_exclusions(con, scenario_id, rule_id, except_tags)
        return rule_id
    return _write(go, path)


_RULE_FIELDS = ('format_tag_id', 'action', 'from_ingredient', 'to_ingredient', 'quantity', 'amount')


def update_rule(rule_id, path=None, **fields):
    '''Patch any of format_tag_id / action / from_ingredient /
    to_ingredient / quantity / amount.'''
    bad = set(fields) - set(_RULE_FIELDS)
    if bad:
        raise ValueError(f'Unknown rule fields: {sorted(bad)}')

    def go(con):
        row = dict(con.execute('SELECT * FROM scenario_rules WHERE id = ?;', (rule_id,)).fetchone())
        row.update(fields)
        _check_rule(row['action'], row['from_ingredient'], row['to_ingredient'])
        con.execute(f'UPDATE scenario_rules SET {", ".join(f"{k} = ?" for k in _RULE_FIELDS)} WHERE id = ?;',
                    [row[k] for k in _RULE_FIELDS] + [rule_id])
    _write(go, path)


def delete_rule(rule_id, path=None):
    _write(lambda con: con.execute('DELETE FROM scenario_rules WHERE id = ?;', (rule_id,)), path)


def reorder_rules(ids, path=None):
    def go(con):
        for order, rid in enumerate(ids, start=1):
            con.execute('UPDATE scenario_rules SET sortOrder = ? WHERE id = ?;', (order, rid))
    _write(go, path)


def _set_exclusions(con, scenario_id, rule_id, tag_ids):
    if rule_id is None:
        con.execute('DELETE FROM scenario_exclusions WHERE scenario_id = ? AND rule_id IS NULL;', (scenario_id,))
    else:
        con.execute('DELETE FROM scenario_exclusions WHERE rule_id = ?;', (rule_id,))
    for tag_id in dict.fromkeys(tag_ids):
        con.execute('INSERT INTO scenario_exclusions (scenario_id, rule_id, tag_id) VALUES (?, ?, ?);',
                    (scenario_id, rule_id, tag_id))


def set_rule_exclusions(rule_id, tag_ids, path=None):
    def go(con):
        sid = con.execute('SELECT scenario_id FROM scenario_rules WHERE id = ?;', (rule_id,)).fetchone()[0]
        _set_exclusions(con, sid, rule_id, tag_ids)
    _write(go, path)


def set_scenario_exclusions(scenario_id, tag_ids, path=None):
    _write(lambda con: _set_exclusions(con, scenario_id, None, tag_ids), path)


def set_price(scenario_id, recipe_id, menu_price, path=None):
    '''The recipe's menu price in the scenario; None goes back to the
    baseline (plus any price_adjust).'''
    def go(con):
        if menu_price is None:
            con.execute('DELETE FROM scenario_prices WHERE scenario_id = ? AND recipe_id = ?;',
                        (scenario_id, recipe_id))
        else:
            con.execute('INSERT OR REPLACE INTO scenario_prices (scenario_id, recipe_id, menu_price)'
                        ' VALUES (?, ?, ?);', (scenario_id, recipe_id, menu_price))
    _write(go, path)


_TABLES = (('scenarios', 'id'), ('scenario_rules', 'id'), ('scenario_exclusions', 'id'),
           ('scenario_prices', 'rowid'))


def snapshot_all(path=None):
    '''Every scenario, row for row with ids, for page-level undo.'''
    con = _connect(path)
    try:
        return {t: [dict(r) for r in con.execute(f'SELECT * FROM {t} ORDER BY {order};')]
                for t, order in _TABLES}
    finally:
        con.close()


def restore_all(snap, path=None):
    '''Put every scenario back to `snap`, ids and all. Rows pointing at an
    ingredient, tag or recipe deleted since are left out.'''
    def go(con):
        live = {
            'ing': {r[0] for r in con.execute('SELECT Id FROM Ingredients;')},
            'tag': {r[0] for r in con.execute('SELECT id FROM tags;')},
            'rec': {r[0] for r in con.execute('SELECT Id FROM Recipes;')},
        }

        def ok(table, row):
            if table == 'scenario_rules':
                return (all(row[k] is None or row[k] in live['ing'] for k in ('from_ingredient', 'to_ingredient'))
                        and (row['format_tag_id'] is None or row['format_tag_id'] in live['tag']))
            if table == 'scenario_exclusions':
                return row['tag_id'] in live['tag']
            if table == 'scenario_prices':
                return row['recipe_id'] in live['rec']
            return True

        for table, _order in reversed(_TABLES):
            con.execute(f'DELETE FROM {table};')
        rule_ids = set()
        for table, _order in _TABLES:
            for row in snap.get(table, ()):
                if not ok(table, row):
                    continue
                if table == 'scenario_exclusions' and row['rule_id'] is not None and row['rule_id'] not in rule_ids:
                    continue
                cols = list(row)
                con.execute(f'INSERT INTO {table} ({", ".join(cols)}) VALUES ({_marks(cols)});',
                            [row[c] for c in cols])
                if table == 'scenario_rules':
                    rule_ids.add(row['id'])
    _write(go, path)


def snapshot(scenario_id, path=None):
    '''Everything inside a scenario (not its name), for undo.'''
    con = _connect(path)
    try:
        return {
            'rules': [dict(r) for r in con.execute(
                'SELECT * FROM scenario_rules WHERE scenario_id = ? ORDER BY id;', (scenario_id,))],
            'exclusions': [dict(r) for r in con.execute(
                'SELECT rule_id, tag_id FROM scenario_exclusions WHERE scenario_id = ? ORDER BY id;',
                (scenario_id,))],
            'prices': [dict(r) for r in con.execute(
                'SELECT recipe_id, menu_price FROM scenario_prices WHERE scenario_id = ?;', (scenario_id,))],
        }
    finally:
        con.close()


def restore(scenario_id, snap, path=None):
    '''Put a scenario's contents back to `snap`. Rule ids come back as
    they were when restoring into the same scenario.'''
    def go(con):
        con.execute('DELETE FROM scenario_rules WHERE scenario_id = ?;', (scenario_id,))
        con.execute('DELETE FROM scenario_exclusions WHERE scenario_id = ?;', (scenario_id,))
        con.execute('DELETE FROM scenario_prices WHERE scenario_id = ?;', (scenario_id,))
        same = all(r['scenario_id'] == scenario_id for r in snap['rules'])
        ids = {}
        for r in snap['rules']:
            cols = ['scenario_id', *_RULE_FIELDS, 'sortOrder'] + (['id'] if same else [])
            vals = [scenario_id] + [r[k] for k in _RULE_FIELDS] + [r['sortOrder']] + ([r['id']] if same else [])
            ids[r['id']] = con.execute(f'INSERT INTO scenario_rules ({", ".join(cols)}) VALUES ({_marks(vals)});',
                                       vals).lastrowid
        for e in snap['exclusions']:
            rule = ids.get(e['rule_id']) if e['rule_id'] is not None else None
            if e['rule_id'] is not None and rule is None:
                continue
            con.execute('INSERT INTO scenario_exclusions (scenario_id, rule_id, tag_id) VALUES (?, ?, ?);',
                        (scenario_id, rule, e['tag_id']))
        for p in snap['prices']:
            con.execute('INSERT INTO scenario_prices (scenario_id, recipe_id, menu_price) VALUES (?, ?, ?);',
                        (scenario_id, p['recipe_id'], p['menu_price']))
    _write(go, path)
