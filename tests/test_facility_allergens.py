import db
from utilities import diets


def _allergen(lib, name):
    rows = lib.sql('SELECT id FROM allergens WHERE name = ?;', (name,))[0]
    if rows:
        return rows[0][0]
    return lib.sql('INSERT INTO allergens (name, sortOrder) VALUES (?, (SELECT COUNT(*) FROM allergens));',
                   (name,))[1]


def _gluten_free_excludes_gluten(lib):
    gf = next(d for d in db.get_diets() if d['key'] == 'gluten_free')
    db.set_diet_allergens(gf['id'], [_allergen(lib, 'Gluten')])


def _recipe_with(lib, *ingredients):
    rid = lib.recipe('Test bowl')
    for order, ing in enumerate(ingredients, start=1):
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity, SortOrder) VALUES (?, ?, 1, ?);',
                (rid, ing, order))
    return rid


def test_diets_strict_by_default_and_fits():
    gf = {'key': 'gluten_free', 'name': 'Gluten-free', 'excluded': ['Gluten'], 'strict': True}
    assert diets.fits(gf, [], {}, facility=[]) is True
    assert diets.fits(gf, [], {}, facility=['Gluten']) is False          # strict counts facility
    assert diets.fits(dict(gf, strict=False), [], {}, facility=['Gluten']) is True
    assert diets.fits(dict(gf, strict=False), ['Gluten'], {}) is False   # contains always counts
    assert diets.excluded_by([], [gf], facility=['Gluten']) == ['Gluten-free']
    assert 'including facility warnings' in diets.describe(gf)


def test_seeded_diets_start_strict(lib):
    assert db.get_diets() and all(d['strict'] for d in db.get_diets())


def test_facility_allergens_roll_up_separately(lib):
    spices = lib.ingredient('BK Spices', '1 tsp')
    wrap = lib.ingredient('Tortilla', '1 ea')
    gluten, nuts, soy = (_allergen(lib, n) for n in ('Gluten', 'Tree Nuts', 'Soy'))
    db.set_ingredient_allergens(spices, [], facility_ids=[gluten, nuts])
    db.set_ingredient_allergens(wrap, [gluten, soy])
    rows = {r['name']: r for r in db.get_ingredient_allergens(spices)}
    assert rows['Gluten']['facility'] == 1 and rows['Gluten']['checked'] == 0

    _gluten_free_excludes_gluten(lib)
    rid = _recipe_with(lib, spices, wrap)
    # Gluten is contained by the tortilla, so it isn't a facility-only warning.
    assert sorted(db.get_recipe_allergens(rid)) == ['Gluten', 'Soy']
    assert db.get_recipe_facility_allergens(rid) == ['Tree Nuts']
    extras = db.get_recipe_library_extras()[rid]
    assert extras['FacilityAllergens'] == ['Tree Nuts']

    data = db.recipe_print_data(rid)
    assert data['facility'] == ['Tree Nuts']
    assert 'Tree Nuts' not in data['free_of']           # the cautious reading
    assert 'Gluten-free' not in data['diets']
    by_name = {r['name']: r for r in data['rows']}
    assert by_name['BK Spices']['facility'] == 'Gluten, Tree Nuts'
    assert by_name['BK Spices']['allergens'] == ''

    sources = dict(db.get_recipe_allergen_sources(rid, facility=True))
    assert sources == {'Tree Nuts': ['BK Spices']}


def test_non_strict_diet_ignores_facility(lib):
    spices = lib.ingredient('BK Spices', '1 tsp')
    db.set_ingredient_allergens(spices, [], facility_ids=[_allergen(lib, 'Gluten')])
    _gluten_free_excludes_gluten(lib)
    rid = _recipe_with(lib, spices)
    assert 'Gluten-free' not in db.recipe_print_data(rid)['diets']
    gf = next(d for d in db.get_diets() if d['key'] == 'gluten_free')
    db.update_diet(gf['id'], strict=False)
    assert 'Gluten-free' in db.recipe_print_data(rid)['diets']


def test_backup_merge_keeps_facility_flag(lib, tmp_path):
    from utilities import backup
    import sqlite3
    spices = lib.ingredient('BK Spices', '1 tsp')
    db.set_ingredient_allergens(spices, [], facility_ids=[_allergen(lib, 'Sesame')])
    path = str(tmp_path / 'b.rwbackup')
    backup.create_backup(path, db_path=lib.path, images_dir=str(tmp_path))
    lib.sql('DELETE FROM ingredient_allergens;')
    lib.sql('DELETE FROM Ingredients;')
    backup.restore_merge(path, db_path=lib.path, images_dir=str(tmp_path),
                         branding_dir=str(tmp_path / 'brand'), safety=False)
    con = sqlite3.connect(lib.path)
    assert con.execute('SELECT facility FROM ingredient_allergens').fetchall() == [(1,)]
    con.close()
