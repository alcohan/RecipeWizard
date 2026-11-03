import config
import json
import sqlite3
from re import sub

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
            , (SELECT group_concat(name, ', ') FROM (
                 SELECT a.name FROM ingredient_allergens ia
                 JOIN allergens a ON a.id = ia.allergen_id
                 WHERE ia.ingredient_id = i.Id ORDER BY a.sortOrder, a.id)) AS Allergens
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


def set_ingredient_allergens(ingredient_id, allergen_ids):
    '''Replace the ingredient's allergen set.'''
    query('DELETE FROM ingredient_allergens WHERE ingredient_id=?', (ingredient_id,))
    for aid in allergen_ids:
        query('INSERT INTO ingredient_allergens (ingredient_id, allergen_id) VALUES (?, ?)',
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
    return result['lastrowid']

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


def library_health_report(stale_days=90):
    '''Collect the data-quality signals Library Health surfaces.

    Each check returns a (count, sample_names) pair — the sample is at
    most 5 names for the UI to show inline, the full count drives the
    badge. Checks are intentionally conservative:

      - missing_nutrition: Calories IS NULL or 0. Fat/protein etc. are
        allowed to be zero (water has them), but a calorie-less row is
        almost always a stub the user forgot to fill in.
      - stale_prices: ingredients whose latest ingredient_prices row is
        older than `stale_days`, plus ingredients with no prices at all.
      - unused_ingredients: not referenced by any Connections row.
      - duplicate_names: ingredient names colliding case-insensitively.

    All read-only; this is a glance report, not an auto-fixer.'''
    def _rows_with_sample(sql, params=(), limit=5):
        rows = query(sql, params)['data']
        names = [r['Name'] for r in rows[:limit]]
        return len(rows), names

    missing_nutrition = _rows_with_sample(
        'SELECT Name FROM Ingredients'
        ' WHERE (Calories IS NULL OR Calories = 0)'
        ' ORDER BY Name COLLATE NOCASE'
    )

    stale_prices = _rows_with_sample(
        'SELECT i.Name FROM Ingredients i'
        ' WHERE NOT EXISTS ('
        '   SELECT 1 FROM ingredient_prices p'
        '   WHERE p.ingredient_id = i.Id'
        f'     AND p.effective_date >= date(\'now\', \'-{int(stale_days)} day\')'
        ' )'
        ' ORDER BY i.Name COLLATE NOCASE'
    )

    unused_ingredients = _rows_with_sample(
        'SELECT i.Name FROM Ingredients i'
        ' WHERE NOT EXISTS ('
        '   SELECT 1 FROM Connections c WHERE c.ChildIngredient = i.Id'
        ' )'
        ' ORDER BY i.Name COLLATE NOCASE'
    )

    # Duplicate names: group rows that share a case-insensitive name;
    # the "sample" lists each name once.
    dup_rows = query(
        'SELECT lower(Name) AS k, COUNT(*) AS n, MIN(Name) AS Name'
        ' FROM Ingredients GROUP BY lower(Name) HAVING n > 1'
        ' ORDER BY k'
    )['data']
    duplicate_names = (len(dup_rows), [r['Name'] for r in dup_rows[:5]])

    return {
        'missing_nutrition': missing_nutrition,
        'stale_prices': stale_prices,
        'unused_ingredients': unused_ingredients,
        'duplicate_names': duplicate_names,
    }


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
    return(result)

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
    
def get_eligible_ingredients(id: int):
    return query_from_file('sql\\get_eligible_ingredients.sql',(id,), rawdata=True)['data']


# Interact with Recipe Ingredients
def add_recipe_ingredient(parent: int, mode: str, child: int, qty: float, sort_order: int = None):
    '''Insert a Connections row. If sort_order is None, the new row is
    appended (MAX(SortOrder) + 1 for the parent recipe). Pass an explicit
    sort_order when undoing a remove, so the row lands back in its
    original position.'''
    if sort_order is None:
        result = query(
            'SELECT COALESCE(MAX(SortOrder), 0) + 1 AS next FROM Connections WHERE ParentRecipe = ?;',
            (parent,), one=True,
        )
        sort_order = (result or {}).get('next', 1) or 1
    sql = '''
        INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity, SortOrder)
        VALUES (?, ?, ?, ?, ?);
    '''
    if mode == 'ingredient':
        recipe = None
        ingredient = child
    elif mode == 'recipe':
        recipe = child
        ingredient = None
    else:
        raise ValueError(f"Invalid mode: {mode}")
    return query(sql, (parent, recipe, ingredient, qty, sort_order))


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

def update_recipe_ingredient(parent: int, mode: str, child: int, qty: float):
    sql = '''
        UPDATE Connections SET Quantity=?
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
    else:
        raise ValueError(f"Invalid mode: {mode}")
    params = (qty, parent, child)
    return query(sql.format(filter=filter), params)


def delete_recipe_ingredient(parent: int, mode: str, child: int):
    sql = '''
        DELETE FROM Connections
        WHERE ParentRecipe=? {filter};
    '''
    if mode == 'ingredient':
        filter = 'AND ChildIngredient=?'
    elif mode == 'recipe':
        filter = 'AND ChildRecipe=?'
    else:
        raise ValueError(f"Invalid mode: {mode}")

    params = (parent, child)
    return query(sql.format(filter=filter), params)

def set_recipe_tag(recipe_id, tag_id):
    '''Replace this recipe's format tag with `tag_id`, or clear it if
    `tag_id` is falsy. Enforces "one format tag per recipe" in code, since
    SQLite can't easily express the partial-unique constraint.

    Note: this only flips the mapping row — it does NOT apply or unapply
    the template's items/multipliers. Use transition_recipe_format() for
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


def get_tag_category_multipliers(tag_id):
    '''All category-multiplier rows for one template. Each ingredient
    category (kind='ingredient' tag) gets one row at most. Categories
    without an override return multiplier=1.0 here so the editor can list
    every category uniformly.'''
    sql = '''
        SELECT
            ct.id AS category_tag_id,
            ct.name AS category_name,
            ct.color AS category_color,
            COALESCE(tcm.multiplier, 1.0) AS multiplier
        FROM tags ct
        LEFT JOIN tag_category_multipliers tcm
          ON tcm.category_tag_id = ct.id AND tcm.tag_id = ?
        WHERE ct.kind = 'ingredient'
        ORDER BY COALESCE(ct.sortOrder, 999), ct.id;
    '''
    return query(sql, (tag_id,))['data']


def set_tag_category_multiplier(tag_id, category_tag_id, multiplier):
    '''Insert or update the (tag_id, category_tag_id) pair. A multiplier of
    exactly 1.0 deletes the row instead — keeps the table clean of no-ops
    so the apply step doesn't waste work on identity multiplications.'''
    if abs(multiplier - 1.0) < 1e-9:
        query(
            'DELETE FROM tag_category_multipliers WHERE tag_id=? AND category_tag_id=?;',
            (tag_id, category_tag_id),
        )
        return
    # Upsert by hand — SQLite's INSERT ON CONFLICT is fine but the UNIQUE
    # constraint gives us a tidy two-step path that's easy to reason about.
    query(
        'DELETE FROM tag_category_multipliers WHERE tag_id=? AND category_tag_id=?;',
        (tag_id, category_tag_id),
    )
    query(
        'INSERT INTO tag_category_multipliers (tag_id, category_tag_id, multiplier) VALUES (?, ?, ?);',
        (tag_id, category_tag_id, multiplier),
    )


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


def transition_recipe_format(recipe_id, old_tag_id, new_tag_id):
    '''Move the recipe from one format to another:
      1. Reverse the old template's category multipliers
      2. Remove items that came from the old template (and aren't in the new
         template's spec) — items the user manually added are left alone
         because their from_template_tag_id is NULL
      3. Re-attribute items shared between old and new templates so they
         survive a future switch-back
      4. Add new template's items that aren't already present
      5. Apply the new template's category multipliers

    Multipliers scale ALL ingredients of a given category in the recipe
    (whether user- or template-added), which matches the user-facing
    notion that "Wraps get a 0.3 portion of greens" is a property of the
    recipe-as-served, not a property of any particular component.
    '''
    # --- 1. reverse old multipliers ---
    if old_tag_id:
        for m in get_tag_category_multipliers(old_tag_id):
            mult = m['multiplier']
            if abs(mult - 1.0) < 1e-9 or mult == 0:
                continue
            query(
                '''UPDATE Connections SET Quantity = Quantity / ?
                   WHERE ParentRecipe = ?
                     AND ChildIngredient IN (
                         SELECT itm.ingredient_id FROM ingredient_tags_mapping itm
                         WHERE itm.tag_id = ?
                     );''',
                (mult, recipe_id, m['category_tag_id']),
            )

    # --- 2/3. handle old template's items ---
    new_template_keys = set()
    if new_tag_id:
        for c in get_tag_components(new_tag_id):
            key = ('ingredient' if c['child_ingredient'] else 'recipe',
                   c['child_ingredient'] or c['child_recipe'])
            new_template_keys.add(key)

    if old_tag_id:
        old_rows = query(
            'SELECT rowid, ChildRecipe, ChildIngredient FROM Connections '
            'WHERE ParentRecipe=? AND from_template_tag_id=?;',
            (recipe_id, old_tag_id),
        )['data']
        for r in old_rows:
            mode = 'ingredient' if r['ChildIngredient'] else 'recipe'
            child = r['ChildIngredient'] or r['ChildRecipe']
            if (mode, child) in new_template_keys:
                # Carries over — re-attribute so the next switch can still
                # find it. Without this, switching back-and-forth would
                # orphan template items as merely-manual ones.
                query(
                    'UPDATE Connections SET from_template_tag_id=? WHERE rowid=?;',
                    (new_tag_id, r['rowid']),
                )
            else:
                query('DELETE FROM Connections WHERE rowid=?;', (r['rowid'],))

    # --- 4. add new template's items not already present ---
    if new_tag_id:
        for c in get_tag_components(new_tag_id):
            mode = 'ingredient' if c['child_ingredient'] else 'recipe'
            child_id = c['child_ingredient'] or c['child_recipe']
            if _recipe_has_component(recipe_id, mode, child_id):
                continue
            # Append; capture template provenance so it can be removed cleanly
            # if the format changes again. Reuses the standard add path so the
            # SortOrder backfill is consistent with manual adds.
            next_order = query(
                'SELECT COALESCE(MAX(SortOrder), 0) + 1 AS next FROM Connections WHERE ParentRecipe=?;',
                (recipe_id,), one=True,
            )
            sort_order = (next_order or {}).get('next', 1) or 1
            qty = c['quantity'] if c['quantity'] is not None else 1.0
            recipe_child = child_id if mode == 'recipe' else None
            ingredient_child = child_id if mode == 'ingredient' else None
            query(
                'INSERT INTO Connections '
                '(ParentRecipe, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id) '
                'VALUES (?, ?, ?, ?, ?, ?);',
                (recipe_id, recipe_child, ingredient_child, qty, sort_order, new_tag_id),
            )

    # --- 5. apply new multipliers ---
    if new_tag_id:
        for m in get_tag_category_multipliers(new_tag_id):
            mult = m['multiplier']
            if abs(mult - 1.0) < 1e-9:
                continue
            query(
                '''UPDATE Connections SET Quantity = Quantity * ?
                   WHERE ParentRecipe = ?
                     AND ChildIngredient IN (
                         SELECT itm.ingredient_id FROM ingredient_tags_mapping itm
                         WHERE itm.tag_id = ?
                     );''',
                (mult, recipe_id, m['category_tag_id']),
            )


def reconcile_recipe_template(recipe_id):
    '''Bring the recipe's Connections rows back in line with its current
    format template — without re-applying multipliers.

    Three steps:
      1. Backfill `from_template_tag_id` on existing rows whose (mode,
         child) matches a template item but whose provenance is NULL.
         Without this, sample-seeded rows look like manual additions and
         a future format switch can't remove them cleanly.
      2. INSERT any template item the recipe is missing, tagged with the
         current `from_template_tag_id`.
      3. DELETE rows still attributed to the current template that aren't
         in the spec anymore (orphaned by a template edit). Manual rows
         (`from_template_tag_id IS NULL`) are never touched.

    Multipliers are deliberately NOT re-applied — they're not idempotent
    and we can't tell whether existing quantities have already been
    scaled. Quantity adjustments stay an explicit, user-driven operation.
    '''
    tag = get_recipe_tag(recipe_id)
    if not tag:
        return
    tag_id = tag['id']
    # Defensive filter: tag_components rows with a non-NULL child_recipe
    # are legacy data from before recipes-in-templates were disallowed.
    # Reconciling one would re-create the cycle that crashed the app, so
    # they're skipped here. The cleanup pass in setup.migrateDB removes
    # such rows; this guard means a stale DB doesn't crash if migration
    # hasn't run yet.
    template_items = [
        c for c in get_tag_components(tag_id) if c['child_ingredient']
    ]
    template_keys = set()
    for c in template_items:
        template_keys.add(('ingredient', c['child_ingredient']))

    rows = query(
        'SELECT rowid, ChildRecipe, ChildIngredient, from_template_tag_id '
        'FROM Connections WHERE ParentRecipe=?;',
        (recipe_id,),
    )['data']
    existing_keys = set()
    for r in rows:
        mode = 'ingredient' if r['ChildIngredient'] else 'recipe'
        child = r['ChildIngredient'] or r['ChildRecipe']
        existing_keys.add((mode, child))
        if (mode, child) in template_keys and r['from_template_tag_id'] is None:
            query(
                'UPDATE Connections SET from_template_tag_id=? WHERE rowid=?;',
                (tag_id, r['rowid']),
            )
        elif r['from_template_tag_id'] == tag_id and (mode, child) not in template_keys:
            query('DELETE FROM Connections WHERE rowid=?;', (r['rowid'],))

    # Template items are always ingredients (recipes are filtered out above).
    for c in template_items:
        child_id = c['child_ingredient']
        if ('ingredient', child_id) in existing_keys:
            continue
        next_order = query(
            'SELECT COALESCE(MAX(SortOrder), 0) + 1 AS next FROM Connections WHERE ParentRecipe=?;',
            (recipe_id,), one=True,
        )
        sort_order = (next_order or {}).get('next', 1) or 1
        qty = c['quantity'] if c['quantity'] is not None else 1.0
        query(
            'INSERT INTO Connections '
            '(ParentRecipe, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id) '
            'VALUES (?, ?, ?, ?, ?, ?);',
            (recipe_id, None, child_id, qty, sort_order, tag_id),
        )


def snapshot_recipe_connections(recipe_id):
    '''Return all Connections rows for one recipe as a list of dicts. The
    SetRecipeTagCommand uses this to capture before/after state so undo
    is a simple table-restore rather than re-running the transition logic
    in reverse.'''
    return query(
        'SELECT ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id '
        'FROM Connections WHERE ParentRecipe=?;',
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
            '(ParentRecipe, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id) '
            'VALUES (?, ?, ?, ?, ?, ?);',
            (recipe_id, r['ChildRecipe'], r['ChildIngredient'], r['Quantity'],
             r['SortOrder'], r['from_template_tag_id']),
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
    Per-allergen rows for one ingredient, with a `checked` flag indicating
    whether the ingredient-allergen mapping exists.
    '''
    sql = '''
        SELECT a.name, a.id,
            CASE WHEN EXISTS (
                SELECT 1 FROM ingredient_allergens ia
                WHERE ia.allergen_id = a.id
                AND ia.ingredient_id = ?
            ) THEN 1 ELSE 0 END AS checked
        FROM allergens a
        ORDER BY a.sortOrder, a.id;
    '''
    return query(sql, (ingredient_id,))['data']

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


def get_recipe_allergen_sources(recipe_id):
    '''[(allergen, [component names])] for the editor's rolled-up
    allergen list: each allergen in the recipe's tree and the direct
    components that bring it in (an ingredient, or a sub-recipe whose
    tree contains it). Canonical allergen order.'''
    sql = '''
        SELECT a.name AS allergen, COALESCE(r.Name, i.Name) AS source
        FROM Connections c
        LEFT JOIN Ingredients i ON i.Id = c.ChildIngredient
        LEFT JOIN Recipes r ON r.Id = c.ChildRecipe
        JOIN allergens a ON a.id IN (
            SELECT allergen_id FROM ingredient_allergens WHERE ingredient_id = c.ChildIngredient
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
                   ' JOIN allergens a ON a.id = ia.allergen_id;')['data']:
        ingredients.setdefault(r['id'], set()).add(r['name'])
    for r in query('SELECT recipe_id AS id, name FROM RecipeAllergens;')['data']:
        recipes.setdefault(r['id'], set()).add(r['name'])
    return ingredients, recipes


def get_all_allergens():
    '''All allergen names in canonical display order (allergens.sortOrder,
    id). Used by the facet pane to render Free-From chips.'''
    rows = query('SELECT name FROM allergens ORDER BY sortOrder, id;')['data']
    return [row['name'] for row in rows]


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
               n.Calories, n.ProteinGrams, n.FiberGrams,
               EXISTS (SELECT 1 FROM Connections c WHERE c.ChildRecipe = r.Id) AS IsSubRecipe
        FROM Recipes r LEFT JOIN RecipeTotalValues n ON n.Id = r.Id;''')['data']:
        per = float(r['OutputQty'] or 1) or 1.0
        out[r['Id']] = {
            'CaloriesPerServing': (r['Calories'] or 0) / per,
            'PerServing': {'Protein': (r['ProteinGrams'] or 0) / per,
                           'Fiber': (r['FiberGrams'] or 0) / per},
            'UpdatedAt': r['UpdatedAt'],
            'IsSubRecipe': bool(r['IsSubRecipe']),
            'Allergens': [],
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


def duplicate_recipe(recipe_id):
    '''Copy a recipe — its yield, menu price, components (in order,
    keeping template provenance) and tags — as "<name> (copy)". The
    copy starts active, even from an archived recipe. Returns the new
    id.'''
    connection = sqlite3.connect(config.DATABASE)
    try:
        cur = connection.cursor()
        cur.execute('''
            INSERT INTO Recipes (Name, Unit, OutputQty, menu_price, updated_at)
            SELECT Name || ' (copy)', Unit, OutputQty, menu_price, datetime('now')
            FROM Recipes WHERE Id = ?;''', (recipe_id,))
        new_id = cur.lastrowid
        cur.execute('''
            INSERT INTO Connections (ParentRecipe, ChildRecipe, ChildIngredient, Quantity,
                                     SortOrder, from_template_tag_id)
            SELECT ?, ChildRecipe, ChildIngredient, Quantity, SortOrder, from_template_tag_id
            FROM Connections WHERE ParentRecipe = ?;''', (new_id, recipe_id))
        cur.execute('''
            INSERT INTO recipe_tags_mapping (tag_id, recipe_id)
            SELECT tag_id, ? FROM recipe_tags_mapping WHERE recipe_id = ?;''', (new_id, recipe_id))
        connection.commit()
        return new_id
    finally:
        connection.close()


def update_tag(tag_id, name=None, color=None, shape=None):
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

def get_price_history(id):
    '''
    Get price history for an ingredient {id}
    '''
    result = query_from_file('sql\\get_ingredient_price_history.sql', (id,))['data']
    return result

def get_recipe_price_history(id):
    '''
    Get price history for a recipe {id}
    '''
    return query_from_file('sql\\get_recipe_price_history.sql', (id,))['data']

def get_recipe_price_history_details(id, date):
    '''
    Get price by component for a recipe {id} and date {date}
    '''
    return query_from_file('sql\\get_recipe_price_history_details.sql', (id,date))['data']

def get_recipe_price_history_dates(recipe_id):
    '''
    For the given recipe, get the list of ingredients and dates of earliest price history
    '''
    return query_from_file('sql\\get_recipe_price_history_dates.sql', (recipe_id,))['data']

def set_ingredient_image(ingredient_id, filename):
    '''Set or clear an ingredient's ImageFilename. Pass None/empty to clear.'''
    return query('UPDATE Ingredients SET ImageFilename=? WHERE Id=?', (filename or None, ingredient_id))

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