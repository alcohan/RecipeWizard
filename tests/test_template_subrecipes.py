'''Sub-recipes as Format (template) items: a packaging kit added to every
recipe of a format, never one that would put a recipe inside itself,
and still seen through by Scenarios.'''
import pytest

import db
import setup
from utilities import scenarios as sc


def _connect(lib, parent, *, ingredient=None, recipe=None, qty=1.0):
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, ChildRecipe, Quantity) VALUES (?, ?, ?, ?);',
            (parent, ingredient, recipe, qty))


@pytest.fixture
def kit(lib):
    '''A "Salad items" kit (bowl, fork, napkin) and two salads.'''
    m = {
        'lettuce': lib.ingredient('Lettuce', '1 cup', cost=1.00),
        'bowl': lib.ingredient('Salad Bowl 32oz', '1 ea', 'Packaging', cost=0.30),
        'grn_bowl': lib.ingredient('GRN Salad Bowl', '1 ea', 'Packaging', cost=0.50),
        'fork': lib.ingredient('Fork', '1 ea', 'Packaging', cost=0.05),
        'napkin': lib.ingredient('Napkin', '1 ea', 'Packaging', cost=0.01),
        'Salad': lib.tag('Salad', 'recipe'),
    }
    m['kit'] = lib.recipe('Salad items')
    for ing in ('bowl', 'fork', 'napkin'):
        _connect(lib, m['kit'], ingredient=m[ing])
    m['cobb'] = lib.recipe('Cobb', 'Salad')
    m['caesar'] = lib.recipe('Caesar', 'Salad')
    for r in ('cobb', 'caesar'):
        _connect(lib, m[r], ingredient=m['lettuce'], qty=2)
        lib.sql('UPDATE Recipes SET menu_price = 10 WHERE Id = ?;', (m[r],))
    return m


def _rows(lib, recipe_id):
    return lib.sql('SELECT ChildIngredient, ChildRecipe, Quantity, from_template_tag_id FROM Connections'
                   ' WHERE ParentRecipe = ?;', (recipe_id,))[0]


def _cost(recipe_id):
    return db.query('SELECT Cost FROM RecipeTotalValues WHERE Id = ?;', (recipe_id,), one=True)['Cost']


def test_kit_is_added_to_every_recipe_of_the_format(lib, kit):
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    db.apply_template_to_recipes(kit['Salad'])
    for r in ('cobb', 'caesar'):
        assert (None, kit['kit'], 1.0, kit['Salad']) in _rows(lib, kit[r])
        assert _cost(kit[r]) == pytest.approx(2.00 + 0.30 + 0.05 + 0.01)
    # A new salad gets it too, and leaving the format takes it away.
    tart = lib.recipe('Tart Salad')
    db.transition_recipe_format(tart, None, kit['Salad'])
    assert (None, kit['kit'], 1.0, kit['Salad']) in _rows(lib, tart)
    db.transition_recipe_format(tart, kit['Salad'], None)
    assert _rows(lib, tart) == []


def test_template_quantity_change_applies(lib, kit):
    comp = db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    db.apply_template_to_recipes(kit['Salad'])
    db.update_tag_component_quantity(comp, 2)
    db.apply_template_to_recipes(kit['Salad'])
    assert (None, kit['kit'], 2.0, kit['Salad']) in _rows(lib, kit['cobb'])


def test_looping_sub_recipes_are_refused(lib, kit):
    # The format's own recipes, and anything containing one.
    platter = lib.recipe('Salad platter')
    _connect(lib, platter, recipe=kit['cobb'])
    blocked = db.template_blocked_recipes(kit['Salad'])
    assert {kit['cobb'], kit['caesar'], platter} <= blocked and kit['kit'] not in blocked
    for rid in (kit['cobb'], platter):
        with pytest.raises(ValueError):
            db.add_tag_component(kit['Salad'], 'recipe', rid)


def test_a_recipe_never_gets_itself(lib, kit):
    '''The kit moving into the format it belongs to (or a recipe inside
    the kit doing so) skips the item instead of looping.'''
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    db.apply_template_to_recipes(kit['Salad'])
    db.transition_recipe_format(kit['kit'], None, kit['Salad'])
    assert all(r[1] != kit['kit'] for r in _rows(lib, kit['kit']))
    assert _cost(kit['kit']) == pytest.approx(0.36)          # the views still finish


def test_scenario_swaps_the_bowl_inside_the_kit(lib, kit):
    '''SeaTac swaps the salad bowl for the GRN bowl even when the bowl
    comes from the template's kit, at the kit's yield.'''
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    db.apply_template_to_recipes(kit['Salad'])
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', kit['Salad'], kit['bowl'], kit['grn_bowl'])
    result = sc.matrix()
    for r in result['recipes']:
        if r['id'] in (kit['cobb'], kit['caesar']):
            assert r['cells'][sid]['cost'] == pytest.approx(r['base']['cost'] + 0.20)
    # A kit that makes 2 sets: each salad uses half a bowl.
    lib.sql('UPDATE Recipes SET OutputQty = 2 WHERE Id = ?;', (kit['kit'],))
    cobb = next(r for r in sc.matrix()['recipes'] if r['id'] == kit['cobb'])
    assert cobb['cells'][sid]['cost'] == pytest.approx(cobb['base']['cost'] + 0.10)


def test_packaging_kit_is_hidden_from_the_components_grid(lib, kit):
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    db.apply_template_to_recipes(kit['Salad'])
    names = [r['Name'] for r in db.recipe_components(kit['cobb'])]
    assert 'Salad items' not in names and 'Lettuce' in names
    # A kit with food in it stays listed.
    _connect(lib, kit['kit'], ingredient=kit['lettuce'])
    assert 'Salad items' in [r['Name'] for r in db.recipe_components(kit['cobb'])]


def test_kit_in_a_format_cannot_be_deleted(lib, kit):
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    with pytest.raises(Exception, match='Salad format'):
        db.delete_recipe(kit['kit'])


def test_migration_keeps_good_kits_and_drops_looping_ones(lib, kit):
    lib.sql('INSERT INTO tag_components (tag_id, child_recipe, quantity) VALUES (?, ?, 1);', (kit['Salad'], kit['kit']))
    lib.sql('INSERT INTO tag_components (tag_id, child_recipe, quantity) VALUES (?, ?, 1);', (kit['Salad'], kit['cobb']))
    lib.sql('INSERT INTO tag_components (tag_id, child_recipe, quantity) VALUES (?, ?, 1);', (kit['Salad'], 9999))
    setup.migrateDB(lib.path)
    left = [r[0] for r in lib.sql('SELECT child_recipe FROM tag_components WHERE child_recipe IS NOT NULL;')[0]]
    assert left == [kit['kit']]


def test_scenario_editor_suggests_the_kits_ingredients(lib, kit):
    db.add_tag_component(kit['Salad'], 'recipe', kit['kit'], 1)
    assert set(db.recipe_leaf_ingredient_ids(kit['kit'])) == {kit['bowl'], kit['fork'], kit['napkin']}


def test_blank_nutrition_saves_as_null_and_old_blanks_are_cleaned(lib):
    ing = lib.ingredient('Napkin', '')
    lib.sql("UPDATE Ingredients SET Calories = '', SodiumMilligrams = '' WHERE Id = ?;", (ing,))
    setup.migrateDB(lib.path)
    assert lib.sql('SELECT typeof(Calories), typeof(SodiumMilligrams) FROM Ingredients WHERE Id = ?;',
                   (ing,))[0][0] == ('null', 'null')
    values = {k: '' for k in ('Calories', 'TTLFatGrams', 'SatFatGrams', 'CholesterolMilligrams',
                              'SodiumMilligrams', 'CarbGrams', 'FiberGrams', 'SugarGrams', 'ProteinGrams')}
    values.update(Name='Napkin', Unit='', Portion='', Weight=5, Cost='0.01', Calories='12')
    db.update_ingredient(ing, values)
    assert lib.sql('SELECT typeof(Calories), Calories, typeof(ProteinGrams) FROM Ingredients WHERE Id = ?;',
                   (ing,))[0][0] == ('integer', 12, 'null')


def test_picker_reads_odd_numbers():
    from gui.dialogs.recipe_component_add import _number
    assert _number('') is None and _number(None) is None and _number('3.5') == 3.5
