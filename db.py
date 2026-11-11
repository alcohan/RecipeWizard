import config
import json
import sqlite3
from re import sub

from utilities import portions

def make_dict(cursor):
    '''
    Return the results from query on cursor as a list of dictionaries, with keys as the column names
    '''
    columns = [description[0] for description in cursor.description]
    records = cursor.fetchall()
    results = []
    for record in records:
        result_dict = dict(zip(columns,record))
        results.append(result_dict)
    return results

# Run a query with optional parameters
def query(sql, params=(), one=False, rawdata=False):
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()
    cursor.execute(sql, params)
    # If we have rows to parse, then make them into a dict
    if rawdata:
        data = cursor.fetchall()
    else:
        if cursor.description:
            data = make_dict(cursor) 
        else:
            data = []
    results = {'data': data, 'rowcount': cursor.rowcount, 'lastrowid': cursor.lastrowid}
    connection.commit()
    connection.close()
    return (data[0] if data else None) if one else results

def query_from_file(file, params=(), one=False,rawdata=False,filter=""):
    # with open(config.resource_path(file), 'r') as f:
    #     sql = f.read()
    sql = config.get_resource(file)
    return query(sql.format(filter=filter), params, one=one, rawdata=rawdata)


def get_ingredients(id=0):
    '''
    Returns details of ingredient with id passed, if no parameter is provided returns all ingredients in a list.
    TagName / TagColor columns expose the single ingredient-kind tag (or NULL).
    '''
    base_sql = '''
        SELECT i.*
            , (SELECT t.name FROM tags t
                JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
                WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagName
            , (SELECT t.color FROM tags t
                JOIN ingredient_tags_mapping itm ON itm.tag_id=t.id
                WHERE itm.ingredient_id=i.Id AND t.kind='ingredient' LIMIT 1) AS TagColor
        FROM Ingredients i
    '''
    if id:
        return query(base_sql + ' WHERE i.Id=?', (id,), one=True)
    return query(base_sql + ' ORDER BY i.Name COLLATE NOCASE ASC')['data']

def get_ingredient_library(change_days=90):
    '''Everything the Ingredients place shows, one row per ingredient,
    in a single query (no per-row lookups):

      category (TagId / TagName / TagColor / TagSort), latest price
      (unit price, case price, units per case, supplier, date),
      PrevPrice / PrevDate (the price before the latest one, for
      "+8.2% since Sep 1"), BasePrice (the price in effect
      `change_days` ago — or the oldest within the window — for the
      table's 90-day change), UsedIn (recipes using it directly),
      ScenarioUses (scenarios with a rule that uses it),
      Allergens (comma-joined, canonical order) and PriceCount.

    Ordered by category order, then name.'''
    sql = f'''
        WITH ranked AS (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.ingredient_id
                ORDER BY p.effective_date DESC, p.id DESC) AS rn
            FROM ingredient_prices p
            WHERE p.effective_date <= date('now')
        ),
        cat AS (
            SELECT itm.ingredient_id, t.id AS tag_id, t.name, t.color,
                   COALESCE(t.sortOrder, 999) AS sort
            FROM ingredient_tags_mapping itm
            JOIN tags t ON t.id = itm.tag_id AND t.kind = 'ingredient'
        )
        SELECT i.*
            , c.tag_id AS TagId, c.name AS TagName, c.color AS TagColor
            , COALESCE(c.sort, 1000) AS TagSort
            , cur.unit_price AS PriceUnit, cur.case_price AS CasePrice
            , cur.units_per_case AS UnitsPerCase, cur.effective_date AS PriceDate
            , cur.supplier_id AS SupplierId, s.name AS SupplierName
            , prev.unit_price AS PrevPrice, prev.effective_date AS PrevDate
            , COALESCE(
                (SELECT r.unit_price FROM ranked r WHERE r.ingredient_id = i.Id
                   AND r.effective_date <= date('now', '-{int(change_days)} day')
                 ORDER BY r.rn LIMIT 1),
                (SELECT r.unit_price FROM ranked r WHERE r.ingredient_id = i.Id
                 ORDER BY r.rn DESC LIMIT 1)) AS BasePrice
            , (SELECT COUNT(*) FROM ingredient_prices p WHERE p.ingredient_id = i.Id) AS PriceCount
            , (SELECT COUNT(DISTINCT cn.ParentRecipe) FROM Connections cn
               WHERE cn.ChildIngredient = i.Id) AS UsedIn
            , (SELECT COUNT(DISTINCT sr.scenario_id) FROM scenario_rules sr
               WHERE sr.to_ingredient = i.Id OR sr.from_ingredient = i.Id) AS ScenarioUses
            , (SELECT group_concat(name, ', ') FROM (
                 SELECT a.name FROM ingredient_allergens ia
                 JOIN allergens a ON a.id = ia.allergen_id
                 WHERE ia.ingredient_id = i.Id AND ia.facility = 0 ORDER BY a.sortOrder, a.id)) AS Allergens
            , (SELECT group_concat(name, ', ') FROM (
                 SELECT a.name FROM ingredient_allergens ia
                 JOIN allergens a ON a.id = ia.allergen_id
                 WHERE ia.ingredient_id = i.Id AND ia.facility = 1 ORDER BY a.sortOrder, a.id))
                AS FacilityAllergens
        FROM Ingredients i
        LEFT JOIN cat c ON c.ingredient_id = i.Id
        LEFT JOIN ranked cur ON cur.ingredient_id = i.Id AND cur.rn = 1
        LEFT JOIN ranked prev ON prev.ingredient_id = i.Id AND prev.rn = 2
        LEFT JOIN suppliers s ON s.id = cur.supplier_id
        GROUP BY i.Id
        ORDER BY TagSort, i.Name COLLATE NOCASE
    '''
    return query(sql)['data']


def get_ingredient_usage(ingredient_id):
    '''Recipes using this ingredient directly, with the quantity each
    uses and that line's current cost — for the inspector's "impact of
    the increase" list and the edit dialog's Used in list. Archived
    recipes come last, with Status 'archived'.'''
    sql = '''
        SELECT r.Id, r.Name, r.status AS Status, c.Quantity, i.Unit,
               i.Cost * c.Quantity AS LineCost
        FROM Connections c
        JOIN Recipes r ON r.Id = c.ParentRecipe
        JOIN Ingredients i ON i.Id = c.ChildIngredient
        WHERE c.ChildIngredient = ?
        ORDER BY r.status = 'archived', r.Name COLLATE NOCASE
    '''
    return query(sql, (ingredient_id,))['data']


def set_ingredient_status(ingredient_id, status):
    '''Archive ('archived') or restore ('active') an ingredient. Recipes
    using it keep it.'''
    assert status in ('active', 'archived'), status
    query('UPDATE Ingredients SET status = ? WHERE Id = ?;', (status, ingredient_id))


def get_ingredient_prices(ingredient_id):
    '''Full price history, newest first, with supplier names.'''
    sql = '''
        SELECT p.id, p.effective_date, p.case_price, p.units_per_case, p.unit_price,
               p.supplier_id, s.name AS supplier, p.notes
        FROM ingredient_prices p
        LEFT JOIN suppliers s ON s.id = p.supplier_id
        WHERE p.ingredient_id = ?
        ORDER BY p.effective_date DESC, p.id DESC
    '''
    return query(sql, (ingredient_id,))['data']


def set_ingredient_statement(ingredient_id, text):
    '''The ingredients list from the package label ('' clears it).'''
    query('UPDATE Ingredients SET statement = ? WHERE Id = ?;', ((text or '').strip() or None, ingredient_id))


def set_ingredient_allergens(ingredient_id, allergen_ids, facility_ids=()):
    '''Replace the ingredient's allergens: `allergen_ids` it contains,
    `facility_ids` only made in a facility that also handles them.'''
    facility = set(facility_ids) - set(allergen_ids)
    query('DELETE FROM ingredient_allergens WHERE ingredient_id=?', (ingredient_id,))
    for aid in allergen_ids:
        query('INSERT INTO ingredient_allergens (ingredient_id, allergen_id, facility) VALUES (?, ?, 0)',
              (ingredient_id, aid))
    for aid in sorted(facility):
        query('INSERT INTO ingredient_allergens (ingredient_id, allergen_id, facility) VALUES (?, ?, 1)',
              (ingredient_id, aid))


def update_ingredient(id, values):
    '''
    Updates ingredient Id with new values
    '''
    params = (
        values['Name'],
        values['Unit'],
        values['Portion'],
        values['Weight'],
        sub(r'[^\d.]', '', values['Cost']),
        values['Calories'],
        values['TTLFatGrams'],
        values['SatFatGrams'],
        values['CholesterolMilligrams'],
        values['SodiumMilligrams'],
        values['CarbGrams'],
        values['FiberGrams'],
        values['SugarGrams'],
        values['ProteinGrams'],
        values.get('ImageFilename') or None,
    )
    result = query_from_file('sql\\update_ingredient_info.sql',params,filter = f'WHERE Id={id}')
    # A new unit changes how portion rules size it.
    apply_portion_rules_for_ingredient(id)
    return result

def create_ingredient( values):
    '''
    Updates ingredient Id with new values
    '''
    params = (
        values['Name'],
        values['Unit'],
        values['Portion'],
        values['Weight'],
        sub(r'[^\d.]', '', values['Cost']),
        values['Calories'],
        values['TTLFatGrams'],
        values['SatFatGrams'],
        values['CholesterolMilligrams'],
        values['SodiumMilligrams'],
        values['CarbGrams'],
        values['FiberGrams'],
        values['SugarGrams'],
        values['ProteinGrams'],
        values.get('ImageFilename') or None,
    )
    result = query_from_file('sql\\create_ingredient.sql',params)
    from utilities.portions import portioned_by_weight
    set_ingredient_basis(result['lastrowid'],
                         values.get('basis') or ('g' if portioned_by_weight(values['Unit'], values['Weight']) else 'each'))
    return result['lastrowid']


def set_ingredient_basis(ingredient_id, basis):
    '''"g" (portioned by weight: nutrition and prices kept per gram) or
    "each". Per-portion values stay as they are.'''
    query('UPDATE Ingredients SET basis = ? WHERE Id = ?;', (basis, ingredient_id))


def rescale_portion(ingredient_id, weight):
    '''The portion itself changed to `weight` grams. Nutrition, every
    price in the history and vendor items bought by the each scale with
    it, from their per-gram values, so recipes and Cost over time read as
    if the portion had always been this size. A typo fix is a plain save
    instead, which keeps the per-portion numbers. Returns False (and
    changes nothing) for an ingredient that isn't portioned by weight.'''
    from setup import NUTRITION
    weight = float(weight)
    con = _connect()
    try:
        row = con.execute(f"SELECT basis, {', '.join(c + '_g' for c in NUTRITION)}"
                          ' FROM Ingredients WHERE Id = ?;', (ingredient_id,)).fetchone()
        if row is None or row[0] != 'g' or weight <= 0:
            return False
        per_gram = row[1:]
        prices = con.execute('SELECT id, grams_per_case FROM ingredient_prices'
                             ' WHERE ingredient_id = ? AND grams_per_case IS NOT NULL;',
                             (ingredient_id,)).fetchall()
        each = con.execute('SELECT id, grams_per_each FROM vendor_items'
                           ' WHERE ingredient_id = ? AND grams_per_each IS NOT NULL;',
                           (ingredient_id,)).fetchall()
        sets = ', '.join(f'{c} = ?' for c in NUTRITION)
        con.execute(f'UPDATE Ingredients SET Weight = ?, {sets} WHERE Id = ?;',
                    (weight, *[None if g is None else g * weight for g in per_gram], ingredient_id))
        # The triggers just re-derived grams from the old per-portion
        # counts; put the grams back and derive the counts from them.
        for price_id, grams in prices:
            con.execute('UPDATE ingredient_prices SET units_per_case = ?, grams_per_case = ? WHERE id = ?;',
                        (grams / weight, grams, price_id))
        for item_id, grams in each:
            con.execute('UPDATE vendor_items SET portions_per_each = ? WHERE id = ?;', (grams / weight, item_id))
        con.execute('''UPDATE Ingredients SET Cost = COALESCE((
            SELECT unit_price FROM ingredient_prices
            WHERE ingredient_id = ? AND effective_date <= date('now')
            ORDER BY effective_date DESC, id DESC LIMIT 1), Cost) WHERE Id = ?;''', (ingredient_id, ingredient_id))
        con.commit()
    finally:
        con.close()
    return True


def scale_portion(ingredient_id, ratio):
    '''The portion is now `ratio` times its size (.5 ea -> 1 ea is 2).
    By weight, that's rescale_portion at the scaled weight. Per each,
    nutrition, weight and every price in the history scale directly, as
    do vendor items: a case yields 1/ratio as many portions.'''
    from setup import NUTRITION
    ratio = float(ratio)
    row = query('SELECT basis, Weight FROM Ingredients WHERE Id = ?;', (ingredient_id,), one=True)
    if row is None or ratio <= 0:
        return False
    try:
        weight = float(row['Weight'] or 0)
    except (TypeError, ValueError):
        weight = 0.0
    if row['basis'] == 'g' and weight > 0:
        return rescale_portion(ingredient_id, weight * ratio)
    con = _connect()
    try:
        sets = ', '.join(f"{c} = NULLIF({c}, '') * :r" for c in NUTRITION)
        con.execute(f'UPDATE Ingredients SET {sets} WHERE Id = :id;', {'r': ratio, 'id': ingredient_id})
        if weight > 0:
            con.execute('UPDATE Ingredients SET Weight = ? WHERE Id = ?;', (weight * ratio, ingredient_id))
        con.execute('UPDATE ingredient_prices SET units_per_case = units_per_case / ? WHERE ingredient_id = ?;',
                    (ratio, ingredient_id))
        con.execute("UPDATE vendor_items SET portions_per_each = portions_per_each / ?"
                    " WHERE ingredient_id = ? AND portions_per_each IS NOT NULL;", (ratio, ingredient_id))
        con.execute('''UPDATE Ingredients SET Cost = COALESCE((
            SELECT unit_price FROM ingredient_prices
            WHERE ingredient_id = ? AND effective_date <= date('now')
            ORDER BY effective_date DESC, id DESC LIMIT 1), Cost) WHERE Id = ?;''', (ingredient_id, ingredient_id))
        con.commit()
    finally:
        con.close()
    return True


def ingredient_price_latest(id):
    return query('''SELECT * FROM ingredient_prices WHERE ingredient_id=? AND effective_date<=Date('now') ORDER BY effective_date DESC, id DESC;''', (id,), one=True)

def ingredient_price_new(id, values):
    '''
    Add a new row to the ingredient_prices table
    '''
    # One price per ingredient per day: a second entry on the same date
    # replaces the first. (The date used to be interpolated unquoted, so
    # SQLite read 2026-10-14 as subtraction and never matched.)
    query('DELETE FROM ingredient_prices WHERE ingredient_id=? AND effective_date=?',
          (id, values[-2]))
    return query('INSERT INTO ingredient_prices (ingredient_id, supplier_id, case_price,'
                 ' units_per_case, effective_date, notes) VALUES (?,?,?,?,?,?)',
                 (id, *values))

def get_suppliers(id=0):
    '''
    Get all suppliers, or a single supplier when id is supplied.
    '''
    if id:
        return query('SELECT * FROM suppliers WHERE id=?;', (id,), one=True)
    return query('SELECT * FROM suppliers ORDER BY name COLLATE NOCASE ASC;')['data']

def create_supplier(values):
    '''
    Create a new supplier row. Returns the new id.
    '''
    params = (values['name'], values['address'], values['city'], values['state'], values['zip'])
    result = query('INSERT INTO suppliers (name, address, city, state, zip) VALUES (?, ?, ?, ?, ?);', params)
    return result['lastrowid']

def update_supplier(id, values):
    '''
    Update an existing supplier.
    '''
    params = (values['name'], values['address'], values['city'], values['state'], values['zip'], id)
    return query('UPDATE suppliers SET name=?, address=?, city=?, state=?, zip=? WHERE id=?;', params)

def delete_supplier(id):
    '''
    Delete a supplier. Raises Exception if any ingredient_prices rows reference it.
    '''
    number_of_references = query('SELECT COUNT(*) AS Count FROM ingredient_prices WHERE supplier_id=?;', (id,), one=True)['Count']
    if number_of_references == 0:
        return query('DELETE FROM suppliers WHERE id=?;', (id,))
    used_on = query('''
        SELECT DISTINCT i.Name FROM ingredient_prices ip
        JOIN Ingredients i ON ip.ingredient_id = i.Id
        WHERE ip.supplier_id = ?
        ORDER BY i.Name COLLATE NOCASE ASC;
    ''', (id,))['data']
    readable = ', '.join(row['Name'] for row in used_on)
    raise Exception(f'Unable to delete. Supplier referenced by {number_of_references} price record(s) on: {readable}')
def delete_ingredient(id):
    '''
    Delete the ingredient Id
    Raises Exception if the ingredient is included in any recipes
    '''
    number_of_references = query(f'SELECT COUNT(*) AS Count FROM Connections WHERE ChildIngredient={id};', one=True)['Count']

    from utilities import scenarios
    in_scenarios = scenarios.ingredient_uses(id) if number_of_references == 0 else []
    if in_scenarios:
        raise Exception(f'Unable to delete. Ingredient used in the {scenarios.names_text(in_scenarios)}'
                        f' scenario{"s" if len(in_scenarios) != 1 else ""}.')
    if number_of_references==0:
        sql = f'''DELETE FROM Ingredients WHERE Id={id}'''
        return query(sql)
    else:
        used_in = f'''
            SELECT Id, Name FROM
            Connections c JOIN Recipes r
            ON c.ParentRecipe = r.Id 
            WHERE C.ChildIngredient = {id} 
        '''
        # We still need to pass this
        recipelist = query(used_in)['data']
        readable = ', '.join(i['Name'] for i in recipelist)
        raise Exception(f'Unable to delete. Ingredient used in {number_of_references} recipe(s). {readable}')
    
def delete_recipe(id):
    '''
    Delete the Recipe Id
    Raises Exception if the recipe is included as an ingredient in any others
    '''
    number_of_references = query(f'SELECT COUNT(*) AS Count FROM Connections WHERE ChildRecipe={id};', one=True)['Count']

    if number_of_references==0:
        return query(f'DELETE FROM Recipes WHERE Id={id}')
    else:
        used_in = f'''
            SELECT Id, Name FROM
            Connections c JOIN Recipes r
            ON c.ParentRecipe = r.Id 
            WHERE C.ChildRecipe = {id} 
        '''
        # We still need to pass this
        recipelist = query(used_in)['data']
        readable = ', '.join(i['Name'] for i in recipelist)
        raise Exception(f'Unable to delete. Recipe used in {number_of_references} other recipe(s). {readable}')


def get_recipe_category_details():
    '''Flat per-(recipe, ingredient) rows for the analytics spreadsheet.

    One row per ingredient appearance inside a recipe, with the
    ingredient's category and per-serving cost + nutrition values
    already scaled by quantity and recipe yield. Sub-recipes flatten
    to their leaf ingredients via recipe_ingredients_expanded.

    Caller pivots this in Python: group by (recipe_id, category) for
    the spreadsheet cells, and keep the per-ingredient rows around for
    tooltip detail.'''
    return query_from_file('sql\\get_recipe_category_details.sql')['data']


STALE_PRICE_DAYS = 90

# An ingredient is "in use" when an active recipe lists it (archived
# recipes aren't on the menu). Its category says what it needs; an
# ingredient with no category needs both.
_IN_USE = """EXISTS (SELECT 1 FROM Connections c JOIN Recipes r ON r.Id = c.ParentRecipe
                     WHERE c.ChildIngredient = i.Id AND COALESCE(r.status, 'active') != 'archived')"""
# A scenario that swaps it in or adds it prices it too.
_IN_USE_PRICED = f"""({_IN_USE} OR EXISTS (SELECT 1 FROM scenario_rules sr WHERE sr.to_ingredient = i.Id))"""
_CATEGORY = """(SELECT t.{col} FROM ingredient_tags_mapping m JOIN tags t ON t.id = m.tag_id
                WHERE m.ingredient_id = i.Id AND t.kind = 'ingredient' LIMIT 1)"""


def library_health(stale_days=STALE_PRICE_DAYS):
    '''What Library health shows, for ingredients used in active recipes:

      - nutrition: no calories, in a category that needs nutrition, and
        not confirmed as really 0. [{Id, Name, Category}]
      - confirmed: confirmed as 0 calories. [{Id, Name, Category}]
      - prices: no price, or the latest price (or "Still right" check)
        older than `stale_days`, in a category that needs a price.
        Oldest first. [{Id, Name, Category, last_price, checked,
        supplier, unit_price, Unit}]
      - duplicates: names two or more ingredients share (archiving
        one of them settles it). [name]

    `issues` is what the Configure badge counts: each nutrition gap and
    duplicate, and stale prices once.'''
    category = _CATEGORY.format(col='name')
    no_calories = '(i.Calories IS NULL OR i.Calories = 0)'
    nutrition = query(f'''
        SELECT i.Id, i.Name, {category} AS Category, COALESCE(i.nutrition_confirmed, 0) AS confirmed
        FROM Ingredients i
        WHERE {no_calories} AND {_IN_USE} AND COALESCE({_CATEGORY.format(col='needs_nutrition')}, 1) = 1
        ORDER BY i.Name COLLATE NOCASE;''')['data']
    prices = query(f'''
        SELECT * FROM (
            SELECT i.Id, i.Name, i.Unit, {category} AS Category, i.price_checked AS checked,
                   p.effective_date AS last_price, p.unit_price, s.name AS supplier
            FROM Ingredients i
            LEFT JOIN ingredient_prices p ON p.id = (
                SELECT p2.id FROM ingredient_prices p2 WHERE p2.ingredient_id = i.Id
                ORDER BY p2.effective_date DESC, p2.id DESC LIMIT 1)
            LEFT JOIN suppliers s ON s.id = p.supplier_id
            WHERE {_IN_USE_PRICED} AND COALESCE({_CATEGORY.format(col='needs_price')}, 1) = 1)
        WHERE MAX(COALESCE(last_price, ''), COALESCE(checked, '')) < date('now', ?)
        ORDER BY MAX(COALESCE(last_price, ''), COALESCE(checked, '')), Name COLLATE NOCASE;''',
        (f'-{int(stale_days)} day',))['data']
    dup_rows = query(
        'SELECT lower(Name) AS k, COUNT(*) AS n, MIN(Name) AS Name'
        " FROM Ingredients WHERE COALESCE(status, 'active') <> 'archived'"
        ' GROUP BY lower(Name) HAVING n > 1'
        ' ORDER BY k')['data']
    report = {
        'nutrition': [r for r in nutrition if not r['confirmed']],
        'confirmed': [r for r in nutrition if r['confirmed']],
        'prices': prices,
        'duplicates': [r['Name'] for r in dup_rows],
        'stale_days': stale_days,
    }
    report['issues'] = len(report['nutrition']) + len(report['duplicates']) + (1 if prices else 0)
    return report


def set_nutrition_confirmed(ingredient_id, confirmed=True):
    '''Library health's "0 is right": the ingredient really has no
    calories, so stop flagging it.'''
    query('UPDATE Ingredients SET nutrition_confirmed = ? WHERE Id = ?;', (1 if confirmed else 0, ingredient_id))


def mark_price_checked(ingredient_id):
    '''Library health's "Still right": the current price was checked
    today. Adds no price entry, so cost history is unchanged.'''
    query("UPDATE Ingredients SET price_checked = date('now') WHERE Id = ?;", (ingredient_id,))


def get_recently_edited(limit=6):
    '''Return the most-recently-touched ingredients and recipes, mixed
    together and sorted by updated_at DESC. Each row is a dict with
    keys: kind ('ingredient'|'recipe'), id, name, updated_at.

    The home tab's "Recently edited" strip consumes this. Mixing the
    two kinds means a single sorted strip reflects whatever the user
    most recently worked on, regardless of type.'''
    rows = query('''
        SELECT 'recipe' AS kind, Id AS id, Name AS name, updated_at
        FROM Recipes
        WHERE updated_at IS NOT NULL
        UNION ALL
        SELECT 'ingredient' AS kind, Id AS id, Name AS name, updated_at
        FROM Ingredients
        WHERE updated_at IS NOT NULL
        ORDER BY updated_at DESC
        LIMIT ?;
    ''', (limit,))['data']
    return rows


# Get summmary data for recipes. If no Id is passed, we get all records
def recipe_info(id=0):
    if id:
        result = query_from_file('sql\\get_recipe_info.sql',one=True, filter=f'WHERE r.Id = {id}')
        # Format the currency
        result['Cost'] = "$ {:.2f}".format(result['Cost'])
        return result
    else:
        result = query_from_file('sql\\get_recipe_info.sql')['data']
        for row in result:
            row['Cost'] = "$ {:0.2f}".format(row['Cost'])
        return result

# Fetch all components on one recipe
def recipe_components(id: int):
    result = query_from_file('sql\\get_recipe_components.sql', (id,))['data']

    # Format the data
    for row in result:
        # Preserve the raw float — inline editing in the recipe dialog needs
        # the precise value for the undo stack, otherwise round-tripping
        # rounds anything past 2 decimals.
        row['QuantityRaw'] = row['Quantity']
        # Strip trailing zeroes from quantity
        row['Quantity'] = "{:.2f}".format(row['Quantity']).rstrip('0').rstrip('.')
        # Preserve raw cost before formatting so category-group subtotals
        # don't have to parse a formatted string back into a float.
        row['CostRaw'] = row['Cost'] or 0.0
        row['Cost'] = "$ {:.2f}".format(row['Cost'])
    _annotate_portions(result)
    return(result)


def _annotate_portions(rows):
    '''Add row['Portion'] — how portion rules size the row, for the
    recipe editor — or None where no rule applies:
      {'state': 'base' | 'fixed' | 'hand', 'pct': share of its base (base),
       'siblings': rows following the same base, 'sizable': unit is a volume,
       'rule': the rule in words}'''
    shares = {}
    for row in rows:
        if row.get('RuleMode') == 'base' and row.get('PortionShare') is not None \
                and row.get('FromTemplateTagId') is None:
            shares.setdefault(row['RuleCategoryId'], []).append(row['PortionShare'])
    for row in rows:
        row['Portion'] = None
        if row['Type'] != 'ingredient' or not row.get('RuleMode') or row.get('FromTemplateTagId') is not None:
            continue
        unit = portions.parse_unit(row.get('Unit'))
        info = {
            'sizable': unit is not None and unit.is_volume,
            'rule': portions.describe_rule(row.get('TagName') or 'category', row['RuleMode'],
                                           row['RuleAmount'], row['RuleMeasure']),
            'mode': row['RuleMode'],
            'pct': None,
            'siblings': 0,
        }
        share = row.get('PortionShare')
        if share is None:
            info['state'] = 'hand'
        elif row['RuleMode'] == 'fixed':
            info['state'] = 'fixed'
        else:
            group = shares.get(row['RuleCategoryId'], [])
            info['state'] = 'base'
            info['siblings'] = len(group)
            info['pct'] = share / sum(group) if sum(group) else None
        row['Portion'] = info

def update_recipe_info(id: int, name: str, unit: str, outputqty: float, menu_price=None):
    '''menu_price is None when the recipe isn't on the menu / price unknown;
    stored as NULL so food-cost % logic skips cleanly.'''
    return query_from_file(
        'sql\\update_recipe_info.sql', (name, unit, outputqty, menu_price, id),
    )


def update_recipe_cost_snapshot(recipe_id):
    '''Stamp the "last cost the user saw" onto the recipe. Reads the
    recipe's current live cost from RecipeTotalValues (which already
    aggregates through sub-recipes) and stores it along with a now
    timestamp. The editor calls this when the user closes the dialog,
    so the "prices changed since you last looked" badge disappears
    only when the user has actually seen the new numbers.'''
    return query(
        'UPDATE Recipes SET'
        '  cost_snapshot = (SELECT Cost FROM RecipeTotalValues WHERE Id = ?),'
        '  cost_snapshot_at = datetime(\'now\')'
        ' WHERE Id = ?',
        (recipe_id, recipe_id),
    )

def create_recipe(name: str, unit: str, outputqty: float):
    result = query_from_file('sql\\create_recipe.sql', (name, unit, outputqty))
    return result['lastrowid']
    
def create_recipe_with(name, unit, outputqty, menu_price=None, format_tag_id=None, copy_from=None):
    '''The New recipe dialog: create a recipe with a format (its
    template's items and portion rules applied) and, optionally, the
    components of another recipe. Copying goes through the same format
    switch the editor uses, so the source's template items are swapped
    for the new format's and its portions follow the new format's rules.
    Recipe tags aren't copied. Returns the new id.'''
    new_id = create_recipe(name, unit, outputqty)
    if menu_price is not None:
        query('UPDATE Recipes SET menu_price = ? WHERE Id = ?;', (menu_price, new_id))
    old_tag_id = None
    if copy_from:
        query('''
            INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity,
                                     SortOrder, from_template_tag_id, portion_share)
            SELECT ?, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id, portion_share
            FROM Connections WHERE ParentRecipe = ?;''', (new_id, copy_from))
        query('INSERT INTO recipe_print_cards (recipe_id, kind, child_id, shown)'
              ' SELECT ?, kind, child_id, shown FROM recipe_print_cards WHERE recipe_id = ?;', (new_id, copy_from))
        old_tag_id = (get_recipe_tag(copy_from) or {}).get('id')
    if old_tag_id or format_tag_id:
        transition_recipe_format(new_id, old_tag_id, format_tag_id)
    set_recipe_tag(new_id, format_tag_id)
    return new_id


def get_eligible_ingredients(id: int):
    return query_from_file('sql\\get_eligible_ingredients.sql',(id,), rawdata=True)['data']


# Interact with Recipe Ingredients
def add_recipe_ingredient(parent: int, mode: str, child: int, qty: float, sort_order: int = None):
    '''Insert a Connections row. If sort_order is None, the new row is
    appended (MAX(SortOrder) + 1 for the parent recipe). Pass an explicit
    sort_order when undoing a remove, so the row lands back in its
    original position.

    An ingredient in a category the recipe's format has a portion rule
    for follows that rule (an equal share of a base), so `qty` is only
    a starting value there; the rules then size it and its neighbours.'''
    if mode == 'ingredient':
        recipe, ingredient = None, child
    elif mode == 'recipe':
        recipe, ingredient = child, None
    else:
        raise ValueError(f"Invalid mode: {mode}")
    con = _connect()
    try:
        cur = con.cursor()
        if sort_order is None:
            cur.execute('SELECT COALESCE(MAX(SortOrder), 0) + 1 FROM Connections WHERE ParentRecipe = ?;',
                        (parent,))
            sort_order = cur.fetchone()[0] or 1
        share = _default_share(cur, parent, ingredient) if ingredient is not None else None
        cur.execute('INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity,'
                    ' SortOrder, portion_share) VALUES (?, ?, ?, ?, ?, ?);',
                    (parent, recipe, ingredient, qty, sort_order, share))
        result = {'data': [], 'rowcount': cur.rowcount, 'lastrowid': cur.lastrowid}
        _apply_rules(cur, parent)
        con.commit()
        return result
    finally:
        con.close()


def reorder_recipe_components(parent: int, ordered_specs):
    '''Rewrite SortOrder for `parent`'s components in the order given.
    `ordered_specs` is a list of (mode, child_id) tuples; the first gets
    SortOrder=1, the next gets 2, etc. Unlisted rows are left alone (their
    old SortOrder values may now be out of range, but ORDER BY still
    produces a consistent result).'''
    for i, (mode, child_id) in enumerate(ordered_specs, start=1):
        if mode == 'ingredient':
            query(
                'UPDATE Connections SET SortOrder = ? WHERE ParentRecipe = ? AND ChildIngredient = ?;',
                (i, parent, child_id),
            )
        elif mode == 'recipe':
            query(
                'UPDATE Connections SET SortOrder = ? WHERE ParentRecipe = ? AND ChildRecipe = ?;',
                (i, parent, child_id),
            )

def _child_column(mode):
    if mode == 'ingredient':
        return 'ChildIngredient'
    if mode == 'recipe':
        return 'ChildRecipe'
    raise ValueError(f"Invalid mode: {mode}")


def update_recipe_ingredient(parent: int, mode: str, child: int, qty: float):
    '''Set a row's quantity by hand. Typing a quantity pins it: a row
    following a fixed rule stops following it; for a base category the
    whole category is pinned at its current quantities, so the typed
    amount sticks and its neighbours don't move.'''
    column = _child_column(mode)
    con = _connect()
    try:
        cur = con.cursor()
        if mode == 'ingredient':
            category = _ingredient_category(cur, child)
            rule = _format_rules(cur, _recipe_format_id(cur, parent)).get(category)
            if rule is not None and rule.mode == 'base':
                cur.execute('''UPDATE Connections SET portion_share = NULL
                               WHERE ParentRecipe = ? AND portion_share IS NOT NULL
                                 AND ChildIngredient IN (
                                   SELECT itm.ingredient_id FROM ingredient_tags_mapping itm
                                   WHERE itm.tag_id = ?);''', (parent, category))
        cur.execute(f'UPDATE Connections SET Quantity = ?, portion_share = NULL'
                    f' WHERE ParentRecipe = ? AND {column} = ?;', (qty, parent, child))
        result = {'data': [], 'rowcount': cur.rowcount, 'lastrowid': cur.lastrowid}
        con.commit()
        return result
    finally:
        con.close()


def delete_recipe_ingredient(parent: int, mode: str, child: int):
    '''Remove a row; a base category it was in is re-split among the
    rows left.'''
    column = _child_column(mode)
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute(f'DELETE FROM Connections WHERE ParentRecipe = ? AND {column} = ?;', (parent, child))
        result = {'data': [], 'rowcount': cur.rowcount, 'lastrowid': cur.lastrowid}
        _apply_rules(cur, parent)
        con.commit()
        return result
    finally:
        con.close()

def set_recipe_tag(recipe_id, tag_id):
    '''Replace this recipe's format tag with `tag_id`, or clear it if
    `tag_id` is falsy. Enforces "one format tag per recipe" in code, since
    SQLite can't easily express the partial-unique constraint.

    Note: this only flips the mapping row — it does NOT apply or unapply
    the template's items or portion rules. Use transition_recipe_format() for
    the full apply-or-switch flow.'''
    query(
        'DELETE FROM recipe_tags_mapping WHERE recipe_id=? '
        "AND tag_id IN (SELECT id FROM tags WHERE kind='recipe');",
        (recipe_id,),
    )
    if tag_id:
        query(
            'INSERT INTO recipe_tags_mapping (recipe_id, tag_id) VALUES (?, ?);',
            (recipe_id, tag_id),
        )


# ---------------------------------------------------------------------------
# Template (recipe-format tag) CRUD + apply/unapply
# ---------------------------------------------------------------------------

def get_tag_components(tag_id):
    '''Rows describing the items this template auto-adds. Joined to the
    canonical name / unit / unit cost so the template editor + summary
    can render and total each row without follow-up queries.'''
    sql = '''
        SELECT tc.id, tc.tag_id, tc.child_recipe, tc.child_ingredient, tc.quantity
            , COALESCE(r.Name, i.Name) AS Name
            , COALESCE(r.Unit, i.Unit) AS Unit
            , CASE WHEN tc.child_recipe IS NOT NULL THEN 'recipe' ELSE 'ingredient' END AS Type
            , COALESCE(rwn.Cost, i.Cost, 0) AS UnitCost
        FROM tag_components tc
        LEFT JOIN Recipes r ON r.Id = tc.child_recipe
        LEFT JOIN Ingredients i ON i.Id = tc.child_ingredient
        LEFT JOIN RecipesWithNutrition rwn ON rwn.Id = tc.child_recipe
        WHERE tc.tag_id = ?
        ORDER BY Name COLLATE NOCASE ASC;
    '''
    return query(sql, (tag_id,))['data']


def add_tag_component(tag_id, mode, child_id, quantity=1.0):
    '''Add an item to a template. `mode` must be 'ingredient' — sub-recipes
    are intentionally rejected here, because a recipe tagged with this
    template would gain itself as a Connections row during reconcile and
    the recursive CTE in RecipesWithNutrition hangs forever on the cycle.
    The schema still accepts `child_recipe` (legacy / forward-compat), but
    the code never inserts one.'''
    if mode == 'ingredient':
        recipe, ingredient = None, child_id
    elif mode == 'recipe':
        raise ValueError(
            'Templates cannot contain sub-recipes — adding one risks a '
            'cycle when the template is applied. Add ingredients only.'
        )
    else:
        raise ValueError(f'Invalid mode: {mode}')
    return query(
        'INSERT INTO tag_components (tag_id, child_recipe, child_ingredient, quantity) VALUES (?, ?, ?, ?);',
        (tag_id, recipe, ingredient, quantity),
    )['lastrowid']


def delete_tag_component(tag_component_id):
    return query('DELETE FROM tag_components WHERE id=?;', (tag_component_id,))


def update_tag_component_quantity(tag_component_id, quantity):
    return query('UPDATE tag_components SET quantity=? WHERE id=?;', (quantity, tag_component_id))


def get_category_portion_formats(category_tag_id):
    '''Names of the formats with a portion rule for this ingredient
    category (utilities/portions.py), in format order.'''
    if not category_tag_id:
        return []
    rows = query(
        '''SELECT t.name FROM tag_portion_rules pr
           JOIN tags t ON t.id = pr.tag_id
           WHERE pr.category_tag_id = ?
           ORDER BY COALESCE(t.sortOrder, 999), t.id;''',
        (category_tag_id,),
    )['data']
    return [r['name'] for r in rows]


def _recipe_has_component(recipe_id, mode, child_id):
    '''True if the recipe already has a connection for this ingredient/recipe.'''
    if mode == 'ingredient':
        row = query(
            'SELECT 1 FROM Connections WHERE ParentRecipe=? AND ChildIngredient=? LIMIT 1;',
            (recipe_id, child_id), one=True,
        )
    else:
        row = query(
            'SELECT 1 FROM Connections WHERE ParentRecipe=? AND ChildRecipe=? LIMIT 1;',
            (recipe_id, child_id), one=True,
        )
    return row is not None


# ---------------------------------------------------------------------------
# Portion rules engine (utilities/portions.py has the math)
# ---------------------------------------------------------------------------

def _connect():
    return sqlite3.connect(config.DATABASE)


def _format_rules(cur, tag_id):
    '''{category_tag_id: portions.Rule} for one format.'''
    if not tag_id:
        return {}
    cur.execute('SELECT category_tag_id, mode, amount, measure FROM tag_portion_rules WHERE tag_id = ?;',
                (tag_id,))
    return {cat: portions.Rule(mode, amount, measure) for cat, mode, amount, measure in cur.fetchall()}


def _recipe_format_id(cur, recipe_id):
    cur.execute('''SELECT rtm.tag_id FROM recipe_tags_mapping rtm
                   JOIN tags t ON t.id = rtm.tag_id AND t.kind = 'recipe'
                   WHERE rtm.recipe_id = ? LIMIT 1;''', (recipe_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _ingredient_category(cur, ingredient_id):
    cur.execute('''SELECT itm.tag_id FROM ingredient_tags_mapping itm
                   JOIN tags t ON t.id = itm.tag_id AND t.kind = 'ingredient'
                   WHERE itm.ingredient_id = ? LIMIT 1;''', (ingredient_id,))
    row = cur.fetchone()
    return row[0] if row else None


def _ingredient_rows(cur, recipe_id):
    '''The recipe's ingredient rows with what the rules need: rowid,
    ingredient, qty, share, unit, category, template.'''
    cur.execute('''
        SELECT c.rowid, c.ChildIngredient, c.Quantity, c.portion_share, i.Unit,
               (SELECT itm.tag_id FROM ingredient_tags_mapping itm
                  JOIN tags t ON t.id = itm.tag_id AND t.kind = 'ingredient'
                 WHERE itm.ingredient_id = c.ChildIngredient LIMIT 1) AS category,
               c.from_template_tag_id
        FROM Connections c JOIN Ingredients i ON i.Id = c.ChildIngredient
        WHERE c.ParentRecipe = ?;''', (recipe_id,))
    keys = ('rowid', 'ingredient', 'qty', 'share', 'unit', 'category', 'template')
    return [dict(zip(keys, r)) for r in cur.fetchall()]


def _apply_rules(cur, recipe_id):
    '''Derive Quantity for every row that follows its format's rule.
    Writes only rows whose quantity actually changes. Returns how many.'''
    rules = _format_rules(cur, _recipe_format_id(cur, recipe_id))
    if not rules:
        return 0
    by_category = {}
    for r in _ingredient_rows(cur, recipe_id):
        if r['share'] is not None and r['category'] in rules:
            by_category.setdefault(r['category'], []).append(r)
    changed = 0
    for category, rows in by_category.items():
        derived = portions.rule_quantities(rules[category], [(r['rowid'], r['unit'], r['share']) for r in rows])
        for r in rows:
            qty = derived.get(r['rowid'])
            if qty is None or (r['qty'] is not None and abs(r['qty'] - qty) < 1e-9):
                continue
            cur.execute('UPDATE Connections SET Quantity = ? WHERE rowid = ?;', (qty, r['rowid']))
            changed += 1
    return changed


def _follow_rules(cur, recipe_id):
    '''Make every hand-added row in a category the recipe's format has a
    rule for follow that rule, keeping the category's current split as
    the shares. Template items stay as the template says.'''
    rules = _format_rules(cur, _recipe_format_id(cur, recipe_id))
    by_category = {}
    for r in _ingredient_rows(cur, recipe_id):
        if r['category'] in rules and r['template'] is None:
            by_category.setdefault(r['category'], []).append(r)
    for category, rows in by_category.items():
        if rules[category].mode == 'fixed':
            shares = {r['rowid']: 1.0 for r in rows
                      if (portions.parse_unit(r['unit']) or portions.ParsedUnit(0, '', None)).is_volume}
        else:
            shares = portions.shares_from_quantities([(r['rowid'], r['unit'], r['qty']) for r in rows])
        for r in rows:
            if r['rowid'] in shares:
                cur.execute('UPDATE Connections SET portion_share = ? WHERE rowid = ?;',
                            (round(shares[r['rowid']], 6), r['rowid']))


def _default_share(cur, recipe_id, ingredient_id):
    '''The share a newly added ingredient starts with: None (pinned) if
    its category has no rule in the recipe's format or its unit isn't a
    volume; otherwise an equal part — the average of the shares already
    in that category, or 1.'''
    rules = _format_rules(cur, _recipe_format_id(cur, recipe_id))
    category = _ingredient_category(cur, ingredient_id)
    if category not in rules:
        return None
    cur.execute('SELECT Unit FROM Ingredients WHERE Id = ?;', (ingredient_id,))
    row = cur.fetchone()
    unit = portions.parse_unit(row[0] if row else None)
    if unit is None or not unit.is_volume:
        return None
    if rules[category].mode == 'fixed':
        return 1.0
    shares = [r['share'] for r in _ingredient_rows(cur, recipe_id)
              if r['category'] == category and r['share'] is not None]
    return sum(shares) / len(shares) if shares else 1.0


def _rule_for_row(cur, recipe_id, ingredient_id):
    '''(category_tag_id, Rule or None) for one ingredient in a recipe.'''
    category = _ingredient_category(cur, ingredient_id)
    return category, _format_rules(cur, _recipe_format_id(cur, recipe_id)).get(category)


def _hand_added_rows(cur, recipe_id, category):
    return [r for r in _ingredient_rows(cur, recipe_id)
            if r['category'] == category and r['template'] is None]


def _run(fn):
    con = _connect()
    try:
        result = fn(con.cursor())
        con.commit()
        return result
    finally:
        con.close()


def pin_portion(recipe_id, ingredient_id):
    '''Size a row by hand at its current quantity. In a base category the
    whole category is pinned, so nothing in it moves any more.'''
    def run(cur):
        category, rule = _rule_for_row(cur, recipe_id, ingredient_id)
        if rule is not None and rule.mode == 'base':
            for r in _hand_added_rows(cur, recipe_id, category):
                cur.execute('UPDATE Connections SET portion_share = NULL WHERE rowid = ?;', (r['rowid'],))
        cur.execute('UPDATE Connections SET portion_share = NULL WHERE ParentRecipe = ? AND ChildIngredient = ?;',
                    (recipe_id, ingredient_id))
    _run(run)


def follow_portion(recipe_id, ingredient_id):
    '''Let a row follow its format's rule again. In a base category every
    hand-added row of the category follows, keeping the current split.
    Returns False when there's no rule or the unit can't be sized.'''
    def run(cur):
        category, rule = _rule_for_row(cur, recipe_id, ingredient_id)
        if rule is None:
            return False
        rows = _hand_added_rows(cur, recipe_id, category)
        if rule.mode == 'base':
            shares = portions.shares_from_quantities([(r['rowid'], r['unit'], r['qty']) for r in rows])
        else:
            shares = {r['rowid']: 1.0 for r in rows if r['ingredient'] == ingredient_id
                      and (portions.parse_unit(r['unit']) or portions.ParsedUnit(0, '', None)).is_volume}
        if not any(r['ingredient'] == ingredient_id and r['rowid'] in shares for r in rows):
            return False
        for r in rows:
            if r['rowid'] in shares:
                cur.execute('UPDATE Connections SET portion_share = ? WHERE rowid = ?;',
                            (round(shares[r['rowid']], 6), r['rowid']))
        _apply_rules(cur, recipe_id)
        return True
    return _run(run)


def _base_split(cur, recipe_id, ingredient_id, qty):
    '''Work out set_base_quantity: (rule, target row, other rows, volume
    wanted) or raise ValueError saying why the quantity can't be a share.'''
    category, rule = _rule_for_row(cur, recipe_id, ingredient_id)
    if rule is None or rule.mode != 'base':
        raise ValueError('This ingredient doesn’t follow a shared base.')
    rows = []
    for r in _ingredient_rows(cur, recipe_id):
        unit = portions.parse_unit(r['unit'])
        if r['category'] == category and r['share'] is not None and unit is not None and unit.is_volume:
            rows.append((r, unit.floz))
    target = next(((r, u) for r, u in rows if r['ingredient'] == ingredient_id), None)
    if target is None:
        raise ValueError('This ingredient doesn’t follow a shared base.')
    want = float(qty) * target[1]
    if not 0 < want < rule.floz - 1e-9:
        raise ValueError(f'That’s the whole base or more ({portions.format_amount(rule.amount, rule.measure)}).')
    others = [(r, u) for r, u in rows if r is not target[0]]
    if not others:
        raise ValueError('It’s the only ingredient in the base, so it takes all of it.')
    return rule, target, others, want


def base_quantity_problem(recipe_id, ingredient_id, qty):
    '''Why set_base_quantity would refuse this quantity, or None.'''
    try:
        _run(lambda cur: _base_split(cur, recipe_id, ingredient_id, qty))
    except ValueError as exc:
        return str(exc)
    return None


def set_base_quantity(recipe_id, ingredient_id, qty):
    '''Type a quantity on a row that follows a base rule: it becomes that
    row's share of the base, and the category's other rows share what's
    left in their current proportions, so the base total holds. Raises
    ValueError when the amount isn't less than the whole base (check
    first with base_quantity_problem).'''
    def run(cur):
        rule, target, others, want = _base_split(cur, recipe_id, ingredient_id, qty)
        total = rule.floz
        other_sum = sum(r['share'] for r, _u in others) or len(others)
        cur.execute('UPDATE Connections SET portion_share = ? WHERE rowid = ?;',
                    (round(want / total, 6), target[0]['rowid']))
        for r, _u in others:
            part = (r['share'] or 1.0) / other_sum if other_sum else 1.0 / len(others)
            cur.execute('UPDATE Connections SET portion_share = ? WHERE rowid = ?;',
                        (round(part * (total - want) / total, 6), r['rowid']))
        _apply_rules(cur, recipe_id)
    _run(run)


def portion_review():
    '''Hand-sized rows a format's rule could size, for the "Check recipes
    against portion rules" review. One group per (recipe, ruled category)
    with at least one pinned, hand-added, volume-unit row:

      {recipe_id, recipe, status, format, category_id, category, mode,
       rule (in words), rows: [{ingredient_id, name, unit, current,
       standard}], cost_change, at_standard}

    `standard` is what following the rule would give (a base keeps its
    current split). Rows whose unit isn't a volume are listed per group
    under `unsizable` instead. Ordered by format, then recipe.'''
    ingredients = {r['Id']: r for r in query('SELECT Id, Name, Unit, Cost FROM Ingredients;')['data']}
    recipes = query('''
        SELECT r.Id, r.Name, r.status, t.id AS tag_id, t.name AS format
        FROM Recipes r
        JOIN recipe_tags_mapping rtm ON rtm.recipe_id = r.Id
        JOIN tags t ON t.id = rtm.tag_id AND t.kind = 'recipe'
        WHERE EXISTS (SELECT 1 FROM tag_portion_rules pr WHERE pr.tag_id = t.id)
        ORDER BY COALESCE(t.sortOrder, 999), t.id, r.Name COLLATE NOCASE;''')['data']
    categories = {t['id']: t['name'] for t in get_tags(kind='ingredient')}
    groups = []

    def run(cur):
        for recipe in recipes:
            rules = _format_rules(cur, recipe['tag_id'])
            by_category = {}
            for r in _ingredient_rows(cur, recipe['Id']):
                if r['category'] in rules and r['template'] is None:
                    by_category.setdefault(r['category'], []).append(r)
            for category, rows in by_category.items():
                rule = rules[category]
                sizable = [r for r in rows
                           if (portions.parse_unit(r['unit']) or portions.ParsedUnit(0, '', None)).is_volume]
                unsizable = [r for r in rows if r not in sizable]
                pinned = [r for r in sizable if r['share'] is None]
                if not pinned and not unsizable:
                    continue
                if rule.mode == 'base':
                    shares = portions.shares_from_quantities([(r['rowid'], r['unit'], r['qty']) for r in sizable])
                    standard = portions.rule_quantities(
                        rule, [(r['rowid'], r['unit'], shares.get(r['rowid'])) for r in sizable])
                    listed = sizable if pinned else []
                else:
                    standard = portions.rule_quantities(rule, [(r['rowid'], r['unit'], 1.0) for r in pinned])
                    listed = pinned
                out_rows, change = [], 0.0
                for r in listed:
                    ing = ingredients.get(r['ingredient'], {})
                    std = standard.get(r['rowid'])
                    change += (std - (r['qty'] or 0)) * float(ing.get('Cost') or 0)
                    out_rows.append({'ingredient_id': r['ingredient'], 'name': ing.get('Name'), 'unit': r['unit'],
                                     'current': r['qty'], 'standard': std, 'following': r['share'] is not None})
                groups.append({
                    'recipe_id': recipe['Id'], 'recipe': recipe['Name'], 'status': recipe['status'],
                    'format': recipe['format'], 'category_id': category,
                    'category': categories.get(category, ''), 'mode': rule.mode,
                    'rule': portions.describe_rule(categories.get(category, 'category'), rule.mode,
                                                   rule.amount, rule.measure),
                    'rows': out_rows, 'cost_change': change,
                    'at_standard': bool(out_rows) and all(portions.matches(x['current'], x['standard'])
                                                          for x in out_rows),
                    'unsizable': [{'ingredient_id': r['ingredient'],
                                   'name': ingredients.get(r['ingredient'], {}).get('Name'), 'unit': r['unit']}
                                  for r in unsizable],
                })
    _run(run)
    return groups


def follow_portion_groups(groups):
    '''Bring review groups onto their rules (see portion_review). Returns
    {recipe_id: snapshot before} so the caller can undo.'''
    before = {}
    for g in groups:
        if not g['rows']:
            continue
        before.setdefault(g['recipe_id'], snapshot_recipe_connections(g['recipe_id']))
        if g['mode'] == 'base':
            follow_portion(g['recipe_id'], g['rows'][0]['ingredient_id'])
        else:
            for row in g['rows']:
                follow_portion(g['recipe_id'], row['ingredient_id'])
    return before


def split_base_evenly(recipe_id, ingredient_id):
    '''Give every row following this ingredient's base an equal share.'''
    def run(cur):
        category, rule = _rule_for_row(cur, recipe_id, ingredient_id)
        if rule is None or rule.mode != 'base':
            return
        for r in _ingredient_rows(cur, recipe_id):
            if r['category'] == category and r['share'] is not None:
                cur.execute('UPDATE Connections SET portion_share = 1.0 WHERE rowid = ?;', (r['rowid'],))
        _apply_rules(cur, recipe_id)
    _run(run)


def apply_portion_rules(recipe_id):
    '''Bring one recipe's rule-following quantities up to date. Safe to
    call any time: the result depends only on rules, shares and units.'''
    con = _connect()
    try:
        changed = _apply_rules(con.cursor(), recipe_id)
        con.commit()
        return changed
    finally:
        con.close()


def apply_portion_rules_for_ingredient(ingredient_id):
    '''Re-derive every recipe that uses this ingredient — after its unit
    or category changes.'''
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute('SELECT DISTINCT ParentRecipe FROM Connections WHERE ChildIngredient = ?;',
                    (ingredient_id,))
        for (recipe_id,) in cur.fetchall():
            _apply_rules(cur, recipe_id)
        con.commit()
    finally:
        con.close()


def get_portion_rules(tag_id):
    '''A format's portion rules, joined to the category name/color.'''
    return query('''
        SELECT pr.id, pr.category_tag_id, ct.name AS category_name, ct.color AS category_color,
               pr.mode, pr.amount, pr.measure
        FROM tag_portion_rules pr JOIN tags ct ON ct.id = pr.category_tag_id
        WHERE pr.tag_id = ?
        ORDER BY COALESCE(ct.sortOrder, 999), ct.id;''', (tag_id,))['data']


def set_portion_rule(tag_id, category_tag_id, mode, amount, measure):
    '''Add or replace a format's rule for one category. Doesn't touch any
    recipe; follow with apply_template_to_recipes(tag_id).'''
    if mode not in portions.MODES:
        raise ValueError(f'Invalid portion rule mode: {mode}')
    if portions.to_floz(amount, measure) is None or float(amount) <= 0:
        raise ValueError(f'Invalid portion rule amount: {amount} {measure}')
    query('''INSERT INTO tag_portion_rules (tag_id, category_tag_id, mode, amount, measure)
             VALUES (?, ?, ?, ?, ?)
             ON CONFLICT (tag_id, category_tag_id)
             DO UPDATE SET mode = excluded.mode, amount = excluded.amount, measure = excluded.measure;''',
          (tag_id, category_tag_id, mode, float(amount), measure))


def delete_portion_rule(tag_id, category_tag_id):
    query('DELETE FROM tag_portion_rules WHERE tag_id = ? AND category_tag_id = ?;',
          (tag_id, category_tag_id))


def get_format_recipe_ids(tag_id):
    return [r['recipe_id'] for r in query(
        'SELECT recipe_id FROM recipe_tags_mapping WHERE tag_id = ? ORDER BY recipe_id;', (tag_id,))['data']]


def get_format_costs(tag_id):
    '''{recipe_id: cost} for every recipe in a format.'''
    return {r['Id']: float(r['Cost'] or 0) for r in query(
        '''SELECT rtv.Id, rtv.Cost FROM RecipeTotalValues rtv
           JOIN recipe_tags_mapping rtm ON rtm.recipe_id = rtv.Id
           WHERE rtm.tag_id = ?;''', (tag_id,))['data']}


def count_hand_sized_recipes(tag_id):
    '''How many of a format's recipes have a hand-added, pinned row in a
    category the format has a rule for — rows its rules don't resize.'''
    return query('''
        SELECT COUNT(DISTINCT c.ParentRecipe) AS n
        FROM Connections c
        JOIN recipe_tags_mapping rtm ON rtm.recipe_id = c.ParentRecipe AND rtm.tag_id = ?
        JOIN ingredient_tags_mapping itm ON itm.ingredient_id = c.ChildIngredient
        JOIN tag_portion_rules pr ON pr.tag_id = rtm.tag_id AND pr.category_tag_id = itm.tag_id
        WHERE c.portion_share IS NULL AND c.from_template_tag_id IS NULL;''', (tag_id,), one=True)['n']


def snapshot_template(tag_id):
    '''A format's auto-add items and portion rules, for undoing a template
    edit with restore_template.'''
    return {
        'components': query('SELECT child_recipe, child_ingredient, quantity FROM tag_components'
                            ' WHERE tag_id = ? ORDER BY id;', (tag_id,))['data'],
        'rules': query('SELECT category_tag_id, mode, amount, measure FROM tag_portion_rules'
                       ' WHERE tag_id = ? ORDER BY id;', (tag_id,))['data'],
    }


def restore_template(tag_id, snapshot):
    con = _connect()
    try:
        cur = con.cursor()
        cur.execute('DELETE FROM tag_components WHERE tag_id = ?;', (tag_id,))
        cur.execute('DELETE FROM tag_portion_rules WHERE tag_id = ?;', (tag_id,))
        for c in snapshot['components']:
            cur.execute('INSERT INTO tag_components (tag_id, child_recipe, child_ingredient, quantity)'
                        ' VALUES (?, ?, ?, ?);', (tag_id, c['child_recipe'], c['child_ingredient'], c['quantity']))
        for r in snapshot['rules']:
            cur.execute('INSERT INTO tag_portion_rules (tag_id, category_tag_id, mode, amount, measure)'
                        ' VALUES (?, ?, ?, ?, ?);', (tag_id, r['category_tag_id'], r['mode'], r['amount'],
                                                     r['measure']))
        con.commit()
    finally:
        con.close()


def apply_template_to_recipes(tag_id):
    '''After a template edit: bring every recipe in this format in line
    with its items (added, removed, quantities) and portion rules, in one
    transaction. Returns {recipe_id: snapshot before} for the recipes that
    changed, so the caller can offer to revert them.'''
    recipe_ids = get_format_recipe_ids(tag_id)
    before = {rid: snapshot_recipe_connections(rid) for rid in recipe_ids}
    con = _connect()
    try:
        cur = con.cursor()
        for rid in recipe_ids:
            _reconcile_items(cur, rid, tag_id)
            _apply_rules(cur, rid)
        con.commit()
    finally:
        con.close()
    return {rid: rows for rid, rows in before.items() if snapshot_recipe_connections(rid) != rows}


def _template_items(cur, tag_id):
    '''{ingredient_id: quantity} a template adds (ingredients only — see
    add_tag_component on why sub-recipes are refused).'''
    if not tag_id:
        return {}
    cur.execute('SELECT child_ingredient, quantity FROM tag_components'
                ' WHERE tag_id = ? AND child_ingredient IS NOT NULL;', (tag_id,))
    return {ing: (qty if qty is not None else 1.0) for ing, qty in cur.fetchall()}


def _reconcile_items(cur, recipe_id, tag_id, old_tag_id=None):
    '''Make the recipe's template rows match `tag_id`'s items. Rows from
    this template (or `old_tag_id`, when switching) that it no longer
    lists are deleted. Rows of a listed item — template or hand-added —
    become template rows at the template's quantity. Missing items are
    appended. Other hand-added rows are untouched.'''
    items = _template_items(cur, tag_id)
    attributed = {t for t in (tag_id, old_tag_id) if t}
    cur.execute('SELECT rowid, ChildIngredient, Quantity, from_template_tag_id, portion_share'
                ' FROM Connections WHERE ParentRecipe = ?;', (recipe_id,))
    present = set()
    for rowid, ingredient, qty, template, share in cur.fetchall():
        if ingredient in items:
            present.add(ingredient)
            if (template, qty, share) != (tag_id, items[ingredient], None):
                cur.execute('UPDATE Connections SET from_template_tag_id = ?, Quantity = ?,'
                            ' portion_share = NULL WHERE rowid = ?;', (tag_id, items[ingredient], rowid))
        elif template is not None and template in attributed:
            cur.execute('DELETE FROM Connections WHERE rowid = ?;', (rowid,))
    for ingredient, qty in items.items():
        if ingredient in present:
            continue
        cur.execute('SELECT COALESCE(MAX(SortOrder), 0) + 1 FROM Connections WHERE ParentRecipe = ?;',
                    (recipe_id,))
        cur.execute('INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity,'
                    ' SortOrder, from_template_tag_id) VALUES (?, NULL, ?, ?, ?, ?);',
                    (recipe_id, ingredient, qty, cur.fetchone()[0], tag_id))


def transition_recipe_format(recipe_id, old_tag_id, new_tag_id):
    '''Move the recipe from one format to another (either may be None),
    and set its format mapping:
      1. Swap template items: the old template's that the new one doesn't
         list go, listed ones are at the new template's quantity, missing
         ones are added. Other hand-added rows stay.
      2. Every hand-added row in a category the new format has a rule for
         follows that rule, keeping the category's current split — so a
         salad's 3 cups of greens become a wrap's 1 cup, and romaine moved
         onto a bowl becomes its 0.5 cup topping.
      3. Derive the quantities.
    SetRecipeTagCommand snapshots before/after, so undo never runs this
    in reverse.'''
    con = _connect()
    try:
        cur = con.cursor()
        _reconcile_items(cur, recipe_id, new_tag_id, old_tag_id)
        cur.execute("DELETE FROM recipe_tags_mapping WHERE recipe_id = ?"
                    " AND tag_id IN (SELECT id FROM tags WHERE kind = 'recipe');", (recipe_id,))
        if new_tag_id:
            cur.execute('INSERT INTO recipe_tags_mapping (recipe_id, tag_id) VALUES (?, ?);',
                        (recipe_id, new_tag_id))
        _follow_rules(cur, recipe_id)
        _apply_rules(cur, recipe_id)
        con.commit()
    finally:
        con.close()


def reconcile_recipe_template(recipe_id):
    '''Bring the recipe in line with its current format: template items
    (added, removed, quantities) and rule-following quantities. Run when
    the editor opens, as a safety net — template edits already apply to
    every recipe in the format (apply_template_to_recipes).'''
    con = _connect()
    try:
        cur = con.cursor()
        tag_id = _recipe_format_id(cur, recipe_id)
        if tag_id:
            _reconcile_items(cur, recipe_id, tag_id)
            _apply_rules(cur, recipe_id)
        con.commit()
    finally:
        con.close()


def snapshot_recipe_connections(recipe_id):
    '''Return all Connections rows for one recipe as a list of dicts. The
    SetRecipeTagCommand uses this to capture before/after state so undo
    is a simple table-restore rather than re-running the transition logic
    in reverse.'''
    return query(
        'SELECT ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id, portion_share '
        'FROM Connections WHERE ParentRecipe=? ORDER BY rowid;',
        (recipe_id,),
    )['data']


def restore_recipe_connections(recipe_id, rows):
    '''Replace all Connections rows for one recipe with `rows` (output of
    snapshot_recipe_connections). Used by the undoable format-change
    command.'''
    query('DELETE FROM Connections WHERE ParentRecipe=?;', (recipe_id,))
    for r in rows:
        query(
            'INSERT INTO Connections '
            '(ParentRecipe, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id,'
            ' portion_share) VALUES (?, ?, ?, ?, ?, ?, ?);',
            (recipe_id, r['ChildRecipe'], r['ChildIngredient'], r['Quantity'],
             r['SortOrder'], r['from_template_tag_id'], r.get('portion_share')),
        )


def get_recipe_tag(recipe_id):
    '''The recipe's current format tag (or None). Returned as a dict with
    id/name/color/kind/shape so callers can render the badge or pick a
    silhouette without an extra lookup.'''
    sql = '''
        SELECT t.id, t.name, t.color, t.kind, t.shape
        FROM tags t
        JOIN recipe_tags_mapping rtm ON rtm.tag_id = t.id
        WHERE rtm.recipe_id = ? AND t.kind = 'recipe'
        LIMIT 1;
    '''
    return query(sql, (recipe_id,), one=True)


def get_ingredient_tag(ingredient_id):
    sql = '''
        SELECT t.id, t.name, t.color, t.kind
        FROM tags t
        JOIN ingredient_tags_mapping itm ON itm.tag_id = t.id
        WHERE itm.ingredient_id = ? AND t.kind = 'ingredient'
        LIMIT 1;
    '''
    return query(sql, (ingredient_id,), one=True)


def set_ingredient_tag(ingredient_id, tag_id):
    '''Replace this ingredient's category tag with `tag_id`, or clear it if
    falsy. Single-per-kind enforced in code (see set_recipe_tag).'''
    query(
        'DELETE FROM ingredient_tags_mapping WHERE ingredient_id=? '
        "AND tag_id IN (SELECT id FROM tags WHERE kind='ingredient');",
        (ingredient_id,),
    )
    if tag_id:
        query(
            'INSERT INTO ingredient_tags_mapping (ingredient_id, tag_id) VALUES (?, ?);',
            (ingredient_id, tag_id),
        )
    apply_portion_rules_for_ingredient(ingredient_id)


def get_tags(kind=None):
    '''All tags, optionally filtered to one kind. Returns rows in
    (sortOrder, id) order so the UI is stable.'''
    if kind is None:
        return query(
            'SELECT * FROM tags ORDER BY kind, COALESCE(sortOrder, 999), id;'
        )['data']
    return query(
        'SELECT * FROM tags WHERE kind=? ORDER BY COALESCE(sortOrder, 999), id;',
        (kind,),
    )['data']

def get_ingredient_allergens(ingredient_id):
    '''
    Per-allergen rows for one ingredient: `checked` when the ingredient
    contains it, `facility` when it's only a facility warning.
    '''
    sql = '''
        SELECT a.name, a.id,
            CASE WHEN EXISTS (
                SELECT 1 FROM ingredient_allergens ia
                WHERE ia.allergen_id = a.id AND ia.ingredient_id = ? AND ia.facility = 0
            ) THEN 1 ELSE 0 END AS checked,
            CASE WHEN EXISTS (
                SELECT 1 FROM ingredient_allergens ia
                WHERE ia.allergen_id = a.id AND ia.ingredient_id = ? AND ia.facility = 1
            ) THEN 1 ELSE 0 END AS facility
        FROM allergens a
        ORDER BY a.sortOrder, a.id;
    '''
    return query(sql, (ingredient_id, ingredient_id))['data']

def modify_ingredient_allergen(ingredient_id, allergen_id, state):
    if state:
        sql = 'INSERT INTO ingredient_allergens (ingredient_id, allergen_id) VALUES (?, ?)'
    else:
        sql = 'DELETE FROM ingredient_allergens WHERE ingredient_id=? AND allergen_id=?'
    return query(sql, (ingredient_id, allergen_id))

def get_recipe_allergens(recipe_id):
    '''
    Allergen names present anywhere in this recipe's expanded ingredient tree.
    '''
    rows = query('SELECT DISTINCT name FROM RecipeAllergens WHERE recipe_id=? ORDER BY name;', (recipe_id,))['data']
    return [row['name'] for row in rows]


def get_recipe_facility_allergens(recipe_id):
    '''Allergens the recipe only has facility warnings for (none of its
    ingredients contains them), in canonical order.'''
    rows = query('''SELECT DISTINCT rf.name FROM RecipeFacilityAllergens rf
                    JOIN allergens a ON a.id = rf.allergen_id
                    WHERE rf.recipe_id = ? ORDER BY a.sortOrder, a.id;''', (recipe_id,))['data']
    return [row['name'] for row in rows]


def get_recipe_allergen_sources(recipe_id, facility=False):
    '''[(allergen, [component names])] for the editor's rolled-up
    allergen list: each allergen in the recipe's tree and the direct
    components that bring it in (an ingredient, or a sub-recipe whose
    tree contains it). Canonical allergen order. With `facility`, the
    facility-only warnings instead.'''
    if facility:
        sql = '''
        SELECT a.name AS allergen, COALESCE(r.Name, i.Name) AS source
        FROM Connections c
        LEFT JOIN Ingredients i ON i.Id = c.ChildIngredient
        LEFT JOIN Recipes r ON r.Id = c.ChildRecipe
        JOIN allergens a ON a.id IN (
            SELECT allergen_id FROM ingredient_allergens WHERE ingredient_id = c.ChildIngredient AND facility = 1
            UNION
            SELECT allergen_id FROM RecipeFacilityAllergens WHERE recipe_id = c.ChildRecipe
        )
        WHERE c.ParentRecipe = ?1
          AND a.id IN (SELECT allergen_id FROM RecipeFacilityAllergens WHERE recipe_id = ?1)
        ORDER BY a.sortOrder, a.id, c.SortOrder;
    '''
    else:
        sql = '''
        SELECT a.name AS allergen, COALESCE(r.Name, i.Name) AS source
        FROM Connections c
        LEFT JOIN Ingredients i ON i.Id = c.ChildIngredient
        LEFT JOIN Recipes r ON r.Id = c.ChildRecipe
        JOIN allergens a ON a.id IN (
            SELECT allergen_id FROM ingredient_allergens WHERE ingredient_id = c.ChildIngredient AND facility = 0
            UNION
            SELECT allergen_id FROM RecipeAllergens WHERE recipe_id = c.ChildRecipe
        )
        WHERE c.ParentRecipe = ?
        ORDER BY a.sortOrder, a.id, c.SortOrder;
    '''
    out = {}
    for row in query(sql, (recipe_id,))['data']:
        out.setdefault(row['allergen'], [])
        if row['source'] not in out[row['allergen']]:
            out[row['allergen']].append(row['source'])
    return list(out.items())


def get_parent_recipes(recipe_id):
    '''Recipes that use this one directly as a sub-recipe, with their
    Status ('active' / 'archived'); archived ones last.'''
    sql = '''
        SELECT DISTINCT r.Id, r.Name, r.status AS Status
        FROM Connections c
        JOIN Recipes r ON r.Id = c.ParentRecipe
        WHERE c.ChildRecipe = ?
        ORDER BY r.status = 'archived', r.Name COLLATE NOCASE ASC;
    '''
    return query(sql, (recipe_id,))['data']


def get_component_allergen_maps():
    '''({ingredient_id: {names}}, {recipe_id: {names}}) — what each
    possible component would bring in. Two queries, used by the
    add-component picker to say which allergens an addition is new.'''
    ingredients, recipes = {}, {}
    for r in query('SELECT ia.ingredient_id AS id, a.name FROM ingredient_allergens ia'
                   ' JOIN allergens a ON a.id = ia.allergen_id WHERE ia.facility = 0;')['data']:
        ingredients.setdefault(r['id'], set()).add(r['name'])
    for r in query('SELECT recipe_id AS id, name FROM RecipeAllergens;')['data']:
        recipes.setdefault(r['id'], set()).add(r['name'])
    return ingredients, recipes


def get_all_allergens():
    '''All allergen names in canonical display order (allergens.sortOrder,
    id). Used by the facet pane to render Free-From chips.'''
    rows = query('SELECT name FROM allergens ORDER BY sortOrder, id;')['data']
    return [row['name'] for row in rows]


def get_all_allergen_rows():
    '''[{id, name}] in canonical order.'''
    return query('SELECT id, name FROM allergens ORDER BY sortOrder, id;')['data']


def get_all_recipe_allergens():
    '''{recipe_id: [allergen_names]} for every recipe that has any
    allergen in its tree. Recipes with no allergens are missing from
    the result. One query, O(allergens-across-recipes) rows.'''
    rows = query('SELECT recipe_id, name FROM RecipeAllergens ORDER BY recipe_id, name;')['data']
    out = {}
    for r in rows:
        out.setdefault(r['recipe_id'], []).append(r['name'])
    return out

def get_recipe_library_extras():
    '''{recipe_id: {...}} — what the Library adds to recipe_info, in
    four queries for the whole library (no per-recipe lookups):
    Calories / Protein / Fiber per serving (one unit of yield), Unit and
    OutputQty, UpdatedAt, IsSubRecipe (used inside another recipe),
    Allergens (canonical order), CategoryIds (ingredient categories
    anywhere in the tree) and TagIds (recipe tags).'''
    out = {}
    for r in query('''
        SELECT r.Id, r.OutputQty, r.updated_at AS UpdatedAt,
               n.Calories, n.ProteinGrams, n.FiberGrams, n.CarbGrams, n.SugarGrams,
               n.TTLFatGrams, n.SatFatGrams, n.SodiumMilligrams, n.CholesterolMilligrams,
               EXISTS (SELECT 1 FROM Connections c WHERE c.ChildRecipe = r.Id) AS IsSubRecipe
        FROM Recipes r LEFT JOIN RecipeTotalValues n ON n.Id = r.Id;''')['data']:
        # RecipeTotalValues is already per unit of yield (it divides
        # by OutputQty), so these are per serving as they stand.
        out[r['Id']] = {
            'CaloriesPerServing': r['Calories'] or 0,
            'PerServing': {key: r[col] or 0 for key, col in (
                ('Calories', 'Calories'), ('Protein', 'ProteinGrams'), ('Fiber', 'FiberGrams'),
                ('Carbs', 'CarbGrams'), ('Sugar', 'SugarGrams'), ('Fat', 'TTLFatGrams'),
                ('SatFat', 'SatFatGrams'), ('Sodium', 'SodiumMilligrams'),
                ('Cholesterol', 'CholesterolMilligrams'))},
            'UpdatedAt': r['UpdatedAt'],
            'IsSubRecipe': bool(r['IsSubRecipe']),
            'Allergens': [],
            'FacilityAllergens': [],
            'CategoryIds': set(),
            'TagIds': set(),
        }
    for r in query('''
        SELECT ra.recipe_id AS rid, a.name FROM RecipeAllergens ra
        JOIN allergens a ON a.id = ra.allergen_id
        ORDER BY ra.recipe_id, a.sortOrder, a.id;''')['data']:
        if r['rid'] in out and r['name'] not in out[r['rid']]['Allergens']:
            out[r['rid']]['Allergens'].append(r['name'])
    for r in query('''
        SELECT rf.recipe_id AS rid, a.name FROM RecipeFacilityAllergens rf
        JOIN allergens a ON a.id = rf.allergen_id
        ORDER BY rf.recipe_id, a.sortOrder, a.id;''')['data']:
        if r['rid'] in out and r['name'] not in out[r['rid']]['FacilityAllergens']:
            out[r['rid']]['FacilityAllergens'].append(r['name'])
    for r in query('''
        SELECT DISTINCT e.recipe_id AS rid, itm.tag_id
        FROM recipe_ingredients_expanded e
        JOIN ingredient_tags_mapping itm ON itm.ingredient_id = e.ingredient_id
        JOIN tags t ON t.id = itm.tag_id AND t.kind = 'ingredient';''')['data']:
        if r['rid'] in out:
            out[r['rid']]['CategoryIds'].add(r['tag_id'])
    for r in query('''
        SELECT m.recipe_id AS rid, m.tag_id FROM recipe_tags_mapping m
        JOIN tags t ON t.id = m.tag_id AND t.kind = 'recipe_tag';''')['data']:
        if r['rid'] in out:
            out[r['rid']]['TagIds'].add(r['tag_id'])
    return out


def get_recipe_tags(recipe_id):
    '''Ids of the recipe tags (kind 'recipe_tag') on this recipe.'''
    rows = query('''
        SELECT m.tag_id FROM recipe_tags_mapping m
        JOIN tags t ON t.id = m.tag_id AND t.kind = 'recipe_tag'
        WHERE m.recipe_id = ?;''', (recipe_id,))['data']
    return {r['tag_id'] for r in rows}


def set_recipe_tags(recipe_id, tag_ids):
    '''Replace this recipe's recipe tags (not its format) with tag_ids.'''
    query('''DELETE FROM recipe_tags_mapping WHERE recipe_id = ?
             AND tag_id IN (SELECT id FROM tags WHERE kind = 'recipe_tag');''', (recipe_id,))
    for tag_id in tag_ids:
        query('INSERT INTO recipe_tags_mapping (recipe_id, tag_id) VALUES (?, ?);', (recipe_id, tag_id))


def set_recipe_status(recipe_id, status):
    '''Archive ('archived') or restore ('active') a recipe.'''
    assert status in ('active', 'archived'), status
    query('UPDATE Recipes SET status = ? WHERE Id = ?;', (status, recipe_id))


def get_diets():
    '''Diet rules in order: [{id, key, name, excluded: [allergen
    names], allergen_ids, nutrient, op, amount, strict}]. A strict diet
    also rules out facility allergens.'''
    rows = query('SELECT id, key, name, nutrient, op, amount, strict FROM diets ORDER BY sortOrder, id;')['data']
    for r in rows:
        r['strict'] = bool(r['strict'])
    links = query('SELECT da.diet_id, a.id, a.name FROM diet_allergens da'
                  ' JOIN allergens a ON a.id = da.allergen_id ORDER BY a.sortOrder, a.id;')['data']
    for r in rows:
        mine = [l for l in links if l['diet_id'] == r['id']]
        r['excluded'] = [l['name'] for l in mine]
        r['allergen_ids'] = [l['id'] for l in mine]
    return rows


def create_diet(name):
    nxt = query('SELECT COALESCE(MAX(sortOrder), 0) + 1 AS n FROM diets;', one=True)['n']
    new_id = query("INSERT INTO diets (key, name, op, sortOrder) VALUES ('', ?, 'min', ?);",
                   (name, nxt))['lastrowid']
    query('UPDATE diets SET key = ? WHERE id = ?;', (f'diet_{new_id}', new_id))
    return new_id


def update_diet(diet_id, name=None, nutrient=..., op=None, amount=..., strict=None):
    '''Patch a diet. nutrient / amount accept None to clear (... = unchanged).'''
    if strict is not None:
        query('UPDATE diets SET strict = ? WHERE id = ?;', (1 if strict else 0, diet_id))
    if name is not None:
        query('UPDATE diets SET name = ? WHERE id = ?;', (name, diet_id))
    if nutrient is not ...:
        query('UPDATE diets SET nutrient = ? WHERE id = ?;', (nutrient, diet_id))
    if op is not None:
        query('UPDATE diets SET op = ? WHERE id = ?;', (op, diet_id))
    if amount is not ...:
        query('UPDATE diets SET amount = ? WHERE id = ?;', (amount, diet_id))


def set_diet_allergens(diet_id, allergen_ids):
    query('DELETE FROM diet_allergens WHERE diet_id = ?;', (diet_id,))
    for a in allergen_ids:
        query('INSERT INTO diet_allergens (diet_id, allergen_id) VALUES (?, ?);', (diet_id, a))


def delete_diet(diet_id):
    query('DELETE FROM diet_allergens WHERE diet_id = ?;', (diet_id,))
    query('DELETE FROM diets WHERE id = ?;', (diet_id,))


def reorder_diets(ids):
    for order, diet_id in enumerate(ids, start=1):
        query('UPDATE diets SET sortOrder = ? WHERE id = ?;', (order, diet_id))


def get_allergen_usage():
    '''Allergens in order with how many ingredients and recipes have
    each: [{id, name, Ingredients, Recipes}].'''
    return query('''
        SELECT a.id, a.name,
               (SELECT COUNT(*) FROM ingredient_allergens ia WHERE ia.allergen_id = a.id AND ia.facility = 0)
                   AS Ingredients,
               (SELECT COUNT(*) FROM ingredient_allergens ia WHERE ia.allergen_id = a.id AND ia.facility = 1)
                   AS Facility,
               (SELECT COUNT(DISTINCT recipe_id) FROM RecipeAllergens ra WHERE ra.allergen_id = a.id) AS Recipes
        FROM allergens a ORDER BY a.sortOrder, a.id;''')['data']


def create_allergen(name):
    nxt = query('SELECT COALESCE(MAX(sortOrder), 0) + 1 AS n FROM allergens;', one=True)['n']
    return query('INSERT INTO allergens (name, sortOrder) VALUES (?, ?);', (name, nxt))['lastrowid']


def rename_allergen(allergen_id, name):
    query('UPDATE allergens SET name = ? WHERE id = ?;', (name, allergen_id))


def delete_allergen(allergen_id):
    '''Also clears it from ingredients and diet rules.'''
    query('DELETE FROM ingredient_allergens WHERE allergen_id = ?;', (allergen_id,))
    query('DELETE FROM diet_allergens WHERE allergen_id = ?;', (allergen_id,))
    query('DELETE FROM allergens WHERE id = ?;', (allergen_id,))


def reorder_allergens(ids):
    for order, allergen_id in enumerate(ids, start=1):
        query('UPDATE allergens SET sortOrder = ? WHERE id = ?;', (order, allergen_id))


def get_saved_views():
    '''[{id, name, state}] in their order; state is a dict.'''
    rows = query('SELECT id, name, state FROM saved_views ORDER BY sortOrder, id;')['data']
    for r in rows:
        r['state'] = json.loads(r['state'])
    return rows


def create_saved_view(name, state):
    nxt = query('SELECT COALESCE(MAX(sortOrder), 0) + 1 AS n FROM saved_views;', one=True)['n']
    return query('INSERT INTO saved_views (name, state, sortOrder) VALUES (?, ?, ?);',
                 (name, json.dumps(state), nxt))['lastrowid']


def update_saved_view(view_id, name=None, state=None):
    if name is not None:
        query('UPDATE saved_views SET name = ? WHERE id = ?;', (name, view_id))
    if state is not None:
        query('UPDATE saved_views SET state = ? WHERE id = ?;', (json.dumps(state), view_id))


def delete_saved_view(view_id):
    query('DELETE FROM saved_views WHERE id = ?;', (view_id,))


def get_saved_comparisons():
    '''[{id, name, recipe_ids, settings}] in their order; recipe_ids is a
    list and settings a dict.'''
    rows = query('SELECT id, name, recipe_ids, settings FROM saved_comparisons'
                 ' ORDER BY sortOrder, id;')['data']
    for r in rows:
        r['recipe_ids'] = json.loads(r['recipe_ids'])
        r['settings'] = json.loads(r['settings'])
    return rows


def create_saved_comparison(name, recipe_ids, settings):
    nxt = query('SELECT COALESCE(MAX(sortOrder), 0) + 1 AS n FROM saved_comparisons;', one=True)['n']
    return query('INSERT INTO saved_comparisons (name, recipe_ids, settings, sortOrder) VALUES (?, ?, ?, ?);',
                 (name, json.dumps(list(recipe_ids)), json.dumps(settings), nxt))['lastrowid']


def update_saved_comparison(comparison_id, name=None, recipe_ids=None, settings=None):
    if name is not None:
        query('UPDATE saved_comparisons SET name = ? WHERE id = ?;', (name, comparison_id))
    if recipe_ids is not None:
        query('UPDATE saved_comparisons SET recipe_ids = ? WHERE id = ?;',
              (json.dumps(list(recipe_ids)), comparison_id))
    if settings is not None:
        query('UPDATE saved_comparisons SET settings = ? WHERE id = ?;', (json.dumps(settings), comparison_id))


def delete_saved_comparison(comparison_id):
    query('DELETE FROM saved_comparisons WHERE id = ?;', (comparison_id,))


def duplicate_recipe(recipe_id):
    '''Copy a recipe — its yield, menu price, components (in order,
    keeping template provenance), tags and print settings — as
    "<name> (copy)". The copy starts active, even from an archived
    recipe. Returns the new id.'''
    connection = sqlite3.connect(config.DATABASE)
    try:
        cur = connection.cursor()
        cur.execute('''
            INSERT INTO Recipes (Name, Unit, OutputQty, menu_price, ImageFilename, print_title, updated_at)
            SELECT Name || ' (copy)', Unit, OutputQty, menu_price, ImageFilename, print_title, datetime('now')
            FROM Recipes WHERE Id = ?;''', (recipe_id,))
        new_id = cur.lastrowid
        cur.execute('''
            INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity,
                                     SortOrder, from_template_tag_id, portion_share)
            SELECT ?, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id, portion_share
            FROM Connections WHERE ParentRecipe = ?;''', (new_id, recipe_id))
        cur.execute('''
            INSERT INTO recipe_tags_mapping (tag_id, recipe_id)
            SELECT tag_id, ? FROM recipe_tags_mapping WHERE recipe_id = ?;''', (new_id, recipe_id))
        cur.execute('INSERT INTO recipe_print_cards (recipe_id, kind, child_id, shown)'
                    ' SELECT ?, kind, child_id, shown FROM recipe_print_cards WHERE recipe_id = ?;',
                    (new_id, recipe_id))
        connection.commit()
        return new_id
    finally:
        connection.close()


def update_tag(tag_id, name=None, color=None, shape=None, needs_nutrition=None, needs_price=None):
    '''Patch a tag's name, color, and/or shape (any combination). Kind is
    intentionally NOT editable — moving a tag between kinds would orphan
    all its existing mappings.'''
    fields, params = [], []
    if name is not None:
        fields.append('name=?')
        params.append(name)
    if color is not None:
        fields.append('color=?')
        params.append(color)
    if shape is not None:
        fields.append('shape=?')
        params.append(shape)
    for col, value in (('needs_nutrition', needs_nutrition), ('needs_price', needs_price)):
        if value is not None:
            fields.append(f'{col}=?')
            params.append(1 if value else 0)
    if not fields:
        return None
    params.append(tag_id)
    return query(f"UPDATE tags SET {', '.join(fields)} WHERE id=?;", tuple(params))


def create_tag(name, kind='ingredient', color='#64748b', shape='none'):
    return query(
        'INSERT INTO tags (name, kind, color, shape) VALUES (?, ?, ?, ?);',
        (name, kind, color, shape),
    )['lastrowid']


def delete_tag(tag_id):
    # Drop both directions of mapping to keep the tables consistent. Either
    # mapping might be empty for a tag — that's fine, DELETE is a no-op.
    query('DELETE FROM recipe_tags_mapping WHERE tag_id=?;', (tag_id,))
    query('DELETE FROM ingredient_tags_mapping WHERE tag_id=?;', (tag_id,))
    return query('DELETE FROM tags WHERE id=?;', (tag_id,))['rowcount']

def get_tag_usage(kind):
    '''Tags of one kind in order, each with how many ingredients (for
    categories) or recipes (for recipe tags and formats) carry it.'''
    table, col = (('ingredient_tags_mapping', 'ingredient_id') if kind == 'ingredient'
                  else ('recipe_tags_mapping', 'recipe_id'))
    return query(f'''
        SELECT t.*, (SELECT COUNT(DISTINCT m.{col}) FROM {table} m WHERE m.tag_id = t.id) AS used
        FROM tags t WHERE t.kind = ? ORDER BY COALESCE(t.sortOrder, 999), t.id;''', (kind,))['data']


def reorder_tags(ids):
    '''Set sortOrder to the position in `ids` (one kind's tags, in order).'''
    con = sqlite3.connect(config.DATABASE)
    try:
        con.executemany('UPDATE tags SET sortOrder = ? WHERE id = ?;', [(i + 1, tid) for i, tid in enumerate(ids)])
        con.commit()
    finally:
        con.close()


def get_supplier_overview():
    '''Every supplier with what the library knows about it:
    {..supplier columns, prices (entries), last_price (date),
     current: [{Id, Name, Unit, unit_price, effective_date}] ingredients
     whose current price is from it, aliases: [names in purchase files],
     vendor_items (count)}.'''
    import json
    from utilities import purchase_import as pi
    suppliers = query('SELECT * FROM suppliers ORDER BY name COLLATE NOCASE;')['data']
    counts = {r['supplier_id']: r for r in query('''
        SELECT supplier_id, COUNT(*) AS n, MAX(effective_date) AS last
        FROM ingredient_prices WHERE supplier_id IS NOT NULL GROUP BY supplier_id;''')['data']}
    current = query('''
        SELECT i.Id, i.Name, i.Unit, p.unit_price, p.effective_date, p.supplier_id
        FROM Ingredients i JOIN (
            SELECT ingredient_id, supplier_id, unit_price, effective_date,
                   ROW_NUMBER() OVER (PARTITION BY ingredient_id ORDER BY effective_date DESC, id DESC) AS rn
            FROM ingredient_prices WHERE effective_date <= date('now')
        ) p ON p.ingredient_id = i.Id AND p.rn = 1
        WHERE p.supplier_id IS NOT NULL
        ORDER BY i.Name COLLATE NOCASE;''')['data']
    aliases = {}
    for f in query('SELECT settings FROM import_formats;')['data']:
        try:
            aliases.update(json.loads(f['settings'] or '{}').get('vendor_suppliers') or {})
        except (TypeError, ValueError):
            pass
    plain = [{'id': s['id'], 'name': s['name'] or ''} for s in suppliers]
    vendor_counts = {}
    for v in query('SELECT vendor_name, COUNT(*) AS n FROM vendor_items GROUP BY vendor_name;')['data']:
        sid = pi.match_supplier(v['vendor_name'] or '', plain, aliases)
        if sid is not None:
            vendor_counts[sid] = vendor_counts.get(sid, 0) + v['n']
            if v['vendor_name'] and v['vendor_name'] not in aliases:
                aliases[v['vendor_name']] = sid
    out = []
    for s in suppliers:
        c = counts.get(s['id']) or {}
        out.append(dict(s, prices=c.get('n', 0), last_price=c.get('last'),
                        current=[r for r in current if r['supplier_id'] == s['id']],
                        aliases=sorted((n for n, sid in aliases.items()
                                        if sid == s['id'] and n.casefold() != (s['name'] or '').casefold()),
                                       key=str.casefold),
                        vendor_items=vendor_counts.get(s['id'], 0)))
    return out


def recipe_cost_history_inputs(recipe_id):
    '''What utilities.cost_history needs for one recipe: its ingredients
    with quantity per serving (sub-recipes expanded) and current cost,
    every price entry those ingredients have, and the menu price.'''
    recipe = query('SELECT Id, Name, Unit, OutputQty, menu_price AS MenuPrice FROM Recipes WHERE Id = ?;',
                   (recipe_id,), one=True)
    if not recipe:
        return None
    components = query('''
        SELECT i.Id AS ingredient_id, i.Name AS name, i.Unit AS unit, i.Cost AS cost,
               SUM(rx.Quantity) / r.OutputQty AS qty,
               (SELECT t.color FROM ingredient_tags_mapping m JOIN tags t ON t.id = m.tag_id
                WHERE m.ingredient_id = i.Id AND t.kind = 'ingredient'
                ORDER BY t.sortOrder LIMIT 1) AS color
        FROM recipe_ingredients_expanded rx
        JOIN Ingredients i ON i.Id = rx.ingredient_id
        JOIN Recipes r ON r.Id = rx.recipe_id
        WHERE rx.recipe_id = ?
        GROUP BY i.Id
        ORDER BY i.Name COLLATE NOCASE;
    ''', (recipe_id,))['data']
    prices = query('''
        SELECT p.id, p.ingredient_id, p.effective_date, p.unit_price, p.import_batch_id
        FROM ingredient_prices p
        WHERE p.ingredient_id IN (SELECT ingredient_id FROM recipe_ingredients_expanded WHERE recipe_id = ?)
          AND p.unit_price IS NOT NULL;
    ''', (recipe_id,))['data']
    return {'recipe': recipe, 'components': components, 'prices': prices}

def set_ingredient_image(ingredient_id, filename):
    '''Set or clear an ingredient's ImageFilename. Pass None/empty to clear.'''
    return query('UPDATE Ingredients SET ImageFilename=? WHERE Id=?', (filename or None, ingredient_id))

def get_recipe_image(recipe_id):
    '''A recipe's photo filename (in config.RECIPE_IMAGES_PATH), or ''.'''
    rows = query('SELECT ImageFilename FROM Recipes WHERE Id = ?;', (recipe_id,))['data']
    return (rows[0]['ImageFilename'] or '') if rows else ''

def set_recipe_image(recipe_id, filename):
    '''Set or clear a recipe's photo. Pass None/empty to clear.'''
    return query('UPDATE Recipes SET ImageFilename=? WHERE Id=?', (filename or None, recipe_id))

def get_recipes_using_ingredient(ingredient_id):
    '''Recipes that directly include this ingredient as a component.
    Matches the same "in use" check that blocks ingredient deletion —
    doesn't expand sub-recipes.'''
    sql = '''
        SELECT DISTINCT r.Id, r.Name
        FROM Connections c
        JOIN Recipes r ON c.ParentRecipe = r.Id
        WHERE c.ChildIngredient = ?
        ORDER BY r.Name COLLATE NOCASE ASC;
    '''
    return query(sql, (ingredient_id,))['data']


def get_recipe_wedge_components(recipe_id):
    '''
    Direct components of a recipe for wedge rendering: name, type, and (for
    ingredients) the assigned image filename.

    Packaging-tagged ingredients are skipped (visually meaningless — they'd
    just take up wedge sectors without an image), but template-added rows
    of non-packaging ingredients still appear so e.g. a wrap shell auto-
    added by the Wrap template shows up in the wedge alongside its greens.
    '''
    sql = '''
        SELECT
            COALESCE(r.Name, i.Name) AS Name,
            CASE WHEN c.ChildRecipe IS NOT NULL THEN 'recipe' ELSE 'ingredient' END AS Type,
            i.ImageFilename AS ImageFilename
        FROM Connections c
        LEFT JOIN Recipes r ON r.Id = c.ChildRecipe
        LEFT JOIN Ingredients i ON i.Id = c.ChildIngredient
        WHERE c.ParentRecipe = ?
          AND NOT EXISTS (
            SELECT 1 FROM ingredient_tags_mapping itm
            JOIN tags t ON t.id = itm.tag_id
            WHERE itm.ingredient_id = c.ChildIngredient
              AND t.kind = 'ingredient' AND t.name = 'Packaging'
          );
    '''
    return query(sql, (recipe_id,))['data']

# --- portion tools (Configure › Portion tools) ----------------------------

def get_portion_tools():
    '''[{id, name, family, size_floz, color, pattern, used}] in sort
    order; `used` counts ingredients whose Portion text names the tool.'''
    return query('''
        SELECT t.id, t.name, t.family, t.size_floz, t.color, t.pattern,
               (SELECT COUNT(*) FROM Ingredients i
                 WHERE lower(trim(i.Portion)) = lower(t.name)) AS used
        FROM portion_tools t
        ORDER BY COALESCE(t.sortOrder, t.id), t.id;''')['data']


def portion_tool_objects():
    '''The tools as utilities.recipe_print.Tool values.'''
    from utilities.recipe_print import Tool
    return [Tool(r['id'], r['name'], r['family'] or '', r['size_floz'], r['color'], r['pattern'] or 'solid')
            for r in get_portion_tools()]


def create_portion_tool(name, family='', size_floz=None, color=None, pattern='solid'):
    top = query('SELECT COALESCE(MAX(sortOrder), 0) AS m FROM portion_tools;', one=True)
    return query('INSERT INTO portion_tools (name, family, size_floz, color, pattern, sortOrder)'
                 ' VALUES (?, ?, ?, ?, ?, ?);',
                 (' '.join(name.split()), family or '', size_floz, color, pattern or 'solid',
                  (top or {}).get('m', 0) + 1))['lastrowid']


def update_portion_tool(tool_id, **fields):
    '''Change any of name, family, size_floz, color, pattern. A rename
    carries the ingredients that name the tool along with it.'''
    allowed = ('name', 'family', 'size_floz', 'color', 'pattern')
    changes = {k: v for k, v in fields.items() if k in allowed}
    if not changes:
        return
    con = _connect()
    try:
        cur = con.cursor()
        if 'name' in changes:
            changes['name'] = ' '.join(str(changes['name']).split())
            cur.execute('SELECT name FROM portion_tools WHERE id = ?;', (tool_id,))
            old = cur.fetchone()
            if old and old[0] != changes['name']:
                cur.execute('UPDATE Ingredients SET Portion = ? WHERE lower(trim(Portion)) = lower(?);',
                            (changes['name'], old[0]))
        sets = ', '.join(f'{k} = ?' for k in changes)
        cur.execute(f'UPDATE portion_tools SET {sets} WHERE id = ?;', (*changes.values(), tool_id))
        con.commit()
    finally:
        con.close()


def delete_portion_tool(tool_id):
    '''Ingredients keep their Portion text; it just links to nothing.'''
    query('DELETE FROM portion_tools WHERE id = ?;', (tool_id,))


def reorder_portion_tools(ids):
    con = _connect()
    try:
        con.executemany('UPDATE portion_tools SET sortOrder = ? WHERE id = ?;',
                        [(i, tool_id) for i, tool_id in enumerate(ids, start=1)])
        con.commit()
    finally:
        con.close()


def get_portion_text_review():
    '''Portion text that needs a look, grouped by (text, unit):
    [{portion, unit, count, names, tool, problem, suggestion}]. `tool`
    is the linked tool's name (None if unlinked), `problem` why a linked
    sized tool doesn't fit the unit, `suggestion` a tool to link
    unlinked text to. Linked text that fits isn't listed.'''
    from utilities import recipe_print
    tools = portion_tool_objects()
    rows = query('''
        SELECT MIN(trim(Portion)) AS portion, COALESCE(Unit, '') AS unit, COUNT(*) AS count,
               group_concat(Name, ', ') AS names
        FROM Ingredients
        WHERE Portion IS NOT NULL AND trim(Portion) <> ''
        GROUP BY lower(trim(Portion)), COALESCE(Unit, '')
        ORDER BY lower(trim(Portion)), COALESCE(Unit, '');''')['data']
    out = []
    for r in rows:
        tool = recipe_print.find_tool(r['portion'], tools)
        if tool is not None:
            problem = recipe_print.size_problem(r['unit'], tool)
            if problem:
                out.append(dict(r, tool=tool.name, problem=problem, suggestion=None))
            continue
        suggestion = recipe_print.suggest_tool(r['portion'], r['unit'], tools)
        out.append(dict(r, tool=None, problem=None, suggestion=suggestion.name if suggestion else None))
    return out


def link_portion_text(portion_text, unit, tool_name):
    '''Point every ingredient with this Portion text and unit at a tool:
    its Portion text becomes the tool's name. Returns rows changed.'''
    return query('''UPDATE Ingredients SET Portion = ?
                    WHERE lower(trim(Portion)) = lower(trim(?)) AND COALESCE(Unit, '') = ?;''',
                 (tool_name, portion_text, unit or ''))['rowcount']


# --- printable recipe page -------------------------------------------------

_PRINT_NUTRIENTS = ('Calories', 'TTLFatGrams', 'SatFatGrams', 'CholesterolMilligrams', 'SodiumMilligrams',
                    'CarbGrams', 'FiberGrams', 'SugarGrams', 'ProteinGrams')


def recipe_print_data(recipe_id):
    '''Everything a printed recipe page shows, and no cost:
    {id, name, unit, output_qty, weight, nutrition (per serving),
     format: {name, color, shape} | None, tags: [{name, color}],
     diets: [names it fits], allergens, facility (facility-only warnings),
     free_of: [names, neither contained nor a facility warning], wedge: [components],
     rows: [{name, type, amount, tool: ToolUse | None, allergens, facility, from_template, statement}],
     nutrition_title: the main panel's subtitle or None,
     cards: [{key, name, serving, weight, nutrition} for each component
             with a panel of its own (utilities.recipe_print)],
     card_options: [{key, name, shown, default}] for the Print view,
     tools_used: [Tool]}. Rows are in the user's order; packaging is
    left out except a wrap's tortilla (utilities.recipe_print.prints_row).
    A card key is (kind, child id).'''
    from utilities import recipe_print
    info = query('SELECT * FROM RecipesWithNutrition WHERE Id = ?;', (recipe_id,), one=True)
    if info is None:
        return None
    fmt = get_recipe_tag(recipe_id)
    tags = query('''
        SELECT t.name, t.color FROM recipe_tags_mapping m
        JOIN tags t ON t.id = m.tag_id AND t.kind = 'recipe_tag'
        WHERE m.recipe_id = ? ORDER BY COALESCE(t.sortOrder, t.id);''', (recipe_id,))['data']
    order = get_all_allergens()
    present = set(get_recipe_allergens(recipe_id))
    facility = set(get_recipe_facility_allergens(recipe_id))
    components = query('''
        SELECT COALESCE(r.Name, i.Name) AS Name
             , CASE WHEN c.ChildRecipe IS NOT NULL THEN 'recipe' ELSE 'ingredient' END AS Type
             , c.Quantity
             , COALESCE(c.ChildIngredient, c.ChildRecipe) AS ChildId
             , COALESCE(i.Unit, r.Unit) AS Unit
             , i.Portion AS Portion
             , i.Calories AS UnitCalories
             , i.statement AS Statement
             , COALESCE(i.Weight, rn.Weight) AS UnitWeight
             , COALESCE(i.Calories, rn.Calories) AS Calories
             , COALESCE(i.TTLFatGrams, rn.TTLFatGrams) AS TTLFatGrams
             , COALESCE(i.SatFatGrams, rn.SatFatGrams) AS SatFatGrams
             , COALESCE(i.CholesterolMilligrams, rn.CholesterolMilligrams) AS CholesterolMilligrams
             , COALESCE(i.SodiumMilligrams, rn.SodiumMilligrams) AS SodiumMilligrams
             , COALESCE(i.CarbGrams, rn.CarbGrams) AS CarbGrams
             , COALESCE(i.FiberGrams, rn.FiberGrams) AS FiberGrams
             , COALESCE(i.SugarGrams, rn.SugarGrams) AS SugarGrams
             , COALESCE(i.ProteinGrams, rn.ProteinGrams) AS ProteinGrams
             , c.from_template_tag_id AS FromTemplateTagId
             , (SELECT t.name FROM tags t JOIN ingredient_tags_mapping itm ON itm.tag_id = t.id
                 WHERE itm.ingredient_id = i.Id AND t.kind = 'ingredient' LIMIT 1) AS TagName
             , CASE WHEN c.ChildRecipe IS NOT NULL THEN
                 (SELECT group_concat(name, ', ') FROM
                   (SELECT DISTINCT a.name FROM RecipeAllergens ra JOIN allergens a ON a.id = ra.allergen_id
                     WHERE ra.recipe_id = c.ChildRecipe ORDER BY a.sortOrder, a.id))
               ELSE
                 (SELECT group_concat(name, ', ') FROM
                   (SELECT a.name FROM ingredient_allergens ia JOIN allergens a ON a.id = ia.allergen_id
                     WHERE ia.ingredient_id = c.ChildIngredient AND ia.facility = 0 ORDER BY a.sortOrder, a.id))
               END AS Allergens
             , CASE WHEN c.ChildRecipe IS NOT NULL THEN
                 (SELECT group_concat(name, ', ') FROM
                   (SELECT DISTINCT a.name FROM RecipeFacilityAllergens rf JOIN allergens a ON a.id = rf.allergen_id
                     WHERE rf.recipe_id = c.ChildRecipe ORDER BY a.sortOrder, a.id))
               ELSE
                 (SELECT group_concat(name, ', ') FROM
                   (SELECT a.name FROM ingredient_allergens ia JOIN allergens a ON a.id = ia.allergen_id
                     WHERE ia.ingredient_id = c.ChildIngredient AND ia.facility = 1 ORDER BY a.sortOrder, a.id))
               END AS FacilityAllergens
        FROM Connections c
        LEFT JOIN Recipes r ON r.Id = c.ChildRecipe
        LEFT JOIN RecipesWithNutrition rn ON rn.Id = c.ChildRecipe
        LEFT JOIN Ingredients i ON i.Id = c.ChildIngredient
        WHERE c.ParentRecipe = ?
        ORDER BY c.SortOrder, c.rowid;''', (recipe_id,))['data']
    settings = recipe_print_settings(recipe_id)
    tools = portion_tool_objects()
    tool_order = {t.id: n for n, t in enumerate(tools)}
    fmt_name = fmt['name'] if fmt else None
    rows, used, cards, card_options = [], {}, [], []
    for c in components:
        if not recipe_print.prints_row(c, fmt_name):
            continue
        key = (c['Type'], c['ChildId'])
        if key not in {o['key'] for o in card_options}:
            default = recipe_print.card_by_default(c)
            shown = settings['cards'].get(key, default)
            label = dict(recipe_print.card_label(c['Name'], c['Unit'], c['UnitWeight'],
                                                 {k: c.get(k) for k in _PRINT_NUTRIENTS}), key=key)
            card_options.append({'key': key, 'name': c['Name'], 'serving': label['serving'],
                                 'shown': shown, 'default': default})
            if shown:
                cards.append(label)
        amt = recipe_print.amount(c['Quantity'], c['Unit'])
        use = (recipe_print.resolve_tool(c['Quantity'], c['Unit'], c['Portion'], tools)
               if c['Type'] == 'ingredient' else None)
        if use and use.tool and use.tool.sized:
            used[use.tool.id] = use.tool
        rows.append({
            'name': c['Name'], 'type': c['Type'], 'amount': amt.text, 'tool': use,
            'allergens': c['Allergens'] or '', 'from_template': c['FromTemplateTagId'] is not None,
            'statement': (c['Statement'] or '').strip(),
            'facility': c['FacilityAllergens'] or '',
        })
    from utilities import diets
    n = {k: info.get(k) or 0 for k in _PRINT_NUTRIENTS}   # already per unit of yield
    per_serving = {'Calories': n['Calories'], 'Protein': n['ProteinGrams'], 'Fiber': n['FiberGrams'],
                   'Carbs': n['CarbGrams'], 'Sugar': n['SugarGrams'], 'Fat': n['TTLFatGrams'],
                   'SatFat': n['SatFatGrams'], 'Sodium': n['SodiumMilligrams'],
                   'Cholesterol': n['CholesterolMilligrams']}
    rules = get_diets()
    fit = set(diets.diets_for(present, per_serving, rules, facility))
    return {
        'id': recipe_id,
        'name': info['Name'],
        'unit': info['Unit'] or '',
        'output_qty': info['OutputQty'],
        'weight': info.get('Weight') or 0,
        'nutrition': n,
        'format': {'name': fmt['name'], 'color': fmt['color'], 'shape': fmt['shape']} if fmt else None,
        'tags': tags,
        'diets': [r['name'] for r in rules if r['key'] in fit],
        'allergens': [a for a in order if a in present],
        'facility': [a for a in order if a in facility],
        # The cautious reading: a facility warning isn't "free of".
        'free_of': [a for a in order if a not in present and a not in facility],
        'wedge': get_recipe_wedge_components(recipe_id),
        'photo': get_recipe_image(recipe_id),
        'nutrition_title': recipe_print.nutrition_title(info['Name'], bool(cards), settings['title']),
        'title_override': settings['title'],
        'cards': cards,
        'card_options': card_options,
        'rows': rows,
        'tools_used': sorted(used.values(), key=lambda t: tool_order.get(t.id, 0)),
    }


def recipe_print_settings(recipe_id):
    '''{title: the main panel title override or None,
     cards: {(kind, child id): shown}} for the components the recipe
    has said something about.'''
    row = query('SELECT print_title FROM Recipes WHERE Id = ?;', (recipe_id,), one=True)
    cards = query('SELECT kind, child_id, shown FROM recipe_print_cards WHERE recipe_id = ?;',
                  (recipe_id,))['data']
    return {'title': (row or {}).get('print_title') or None,
            'cards': {(c['kind'], c['child_id']): bool(c['shown']) for c in cards}}


def set_recipe_print_title(recipe_id, title):
    '''None or blank: back to the automatic title.'''
    query('UPDATE Recipes SET print_title = ? WHERE Id = ?;', ((title or '').strip() or None, recipe_id))


def set_recipe_print_card(recipe_id, key, shown):
    '''Whether component `key` (kind, child id) gets its own panel;
    None goes back to the default.'''
    kind, child_id = key
    if shown is None:
        query('DELETE FROM recipe_print_cards WHERE recipe_id = ? AND kind = ? AND child_id = ?;',
              (recipe_id, kind, child_id))
    else:
        query('INSERT OR REPLACE INTO recipe_print_cards (recipe_id, kind, child_id, shown)'
              ' VALUES (?, ?, ?, ?);', (recipe_id, kind, child_id, 1 if shown else 0))


# --- print branding (Configure › Print & branding) -------------------------

def get_print_branding():
    '''{key: value} for the branding text settings (accent, header,
    footer); missing keys mean the defaults. The logo is a file, see
    gui.services.print_branding.'''
    rows = query("SELECT key, value FROM print_branding WHERE key <> 'logo';")['data']
    return {r['key']: r['value'] for r in rows}


def set_print_branding(key, value):
    query('INSERT INTO print_branding (key, value) VALUES (?, ?)'
          ' ON CONFLICT(key) DO UPDATE SET value = excluded.value;', (key, value))


def take_legacy_print_logo():
    '''A logo an earlier build stored in the library, as (bytes, ext),
    removed from the library; None if there isn't one.'''
    row = query("SELECT value, data FROM print_branding WHERE key = 'logo';", one=True)
    query("DELETE FROM print_branding WHERE key = 'logo';")
    return (bytes(row['data']), row['value'] or '') if row and row['data'] else None
