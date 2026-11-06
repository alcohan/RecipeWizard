import db


def _use(lib, *ingredient_ids, archived=False):
    rid = lib.recipe('Bowl ' + '-'.join(map(str, ingredient_ids)))
    for iid in ingredient_ids:
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (rid, iid))
    if archived:
        lib.sql("UPDATE Recipes SET status = 'archived' WHERE Id = ?;", (rid,))
    return rid


def _price(lib, iid, day):
    lib.sql('INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)'
            ' VALUES (?, 10, 10, ?);', (iid, day))


def _names(rows):
    return sorted(r['Name'] for r in rows)


def test_packaging_needs_no_nutrition(lib):
    box = lib.ingredient('Box', 'ea', 'Packaging')
    pepper = lib.ingredient('Pepper', 'g', 'Finish')
    _use(lib, box, pepper)
    assert _names(db.library_health()['nutrition']) == ['Pepper']


def test_only_active_recipes_count(lib):
    used = lib.ingredient('Kale', 'g', 'Greens')
    lib.ingredient('Unused', 'g', 'Greens')
    old = lib.ingredient('Old', 'g', 'Greens')
    _use(lib, used)
    _use(lib, old, archived=True)
    r = db.library_health()
    assert _names(r['nutrition']) == ['Kale']
    assert _names(r['prices']) == ['Kale']


def test_zero_is_right(lib):
    pepper = lib.ingredient('Pepper', 'g', 'Finish')
    _use(lib, pepper)
    db.set_nutrition_confirmed(pepper)
    r = db.library_health()
    assert r['nutrition'] == [] and _names(r['confirmed']) == ['Pepper']
    db.set_nutrition_confirmed(pepper, False)
    assert _names(db.library_health()['nutrition']) == ['Pepper']


def test_stale_prices_flag_once_oldest_first(lib):
    a = lib.ingredient('Apple', 'ea', 'Toppings')
    b = lib.ingredient('Beet', 'ea', 'Toppings')
    c = lib.ingredient('Corn', 'ea', 'Toppings')
    lib.sql('UPDATE Ingredients SET Calories = 10;')
    _use(lib, a, b, c)
    _price(lib, a, '2025-01-01')
    _price(lib, b, '2024-01-01')
    lib.sql("INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)"
            " VALUES (?, 10, 10, date('now'));", (c,))
    r = db.library_health()
    assert [p['Name'] for p in r['prices']] == ['Beet', 'Apple']
    assert r['issues'] == 1


def test_still_right_clears_without_a_price(lib):
    a = lib.ingredient('Apple', 'ea', 'Toppings')
    _use(lib, a)
    _price(lib, a, '2025-01-01')
    db.mark_price_checked(a)
    assert db.library_health()['prices'] == []
    assert lib.sql('SELECT COUNT(*) FROM ingredient_prices;')[0][0][0] == 1


def test_category_can_skip_price(lib):
    box = lib.ingredient('Box', 'ea', 'Packaging')
    _use(lib, box)
    assert _names(db.library_health()['prices']) == ['Box']
    db.update_tag(lib.tag('Packaging', 'ingredient'), needs_price=False)
    assert db.library_health()['prices'] == []
