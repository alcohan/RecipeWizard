'''The portion rules engine in db.py, against the default rules:
Salad greens base 3 cup, grains fixed 3 f.oz; Bowl grains base 8 f.oz,
greens fixed 0.5 cup; Wrap greens base 1 cup, grains base 4 f.oz.'''
import pytest

import db
import setup


@pytest.fixture
def pantry(lib):
    return {
        'romaine': lib.ingredient('Romaine', '3 cups', 'Greens'),
        'kale': lib.ingredient('Kale', '3 cups', 'Greens'),
        'arugula': lib.ingredient('Arugula', '3 cups', 'Greens'),
        'rice': lib.ingredient('Rice', '8 f.oz', 'Grains'),
        'tortilla': lib.ingredient('Tortilla', '1 ea', 'Packaging'),
        'bowl': lib.ingredient('Bowl', '1 ea', 'Packaging'),
        'feta': lib.ingredient('Feta', '1 f.oz', 'Cheese'),
    }


def test_default_rules_are_seeded(lib):
    rules = {(r['category_name'], r['mode'], r['amount'], r['measure'])
             for r in db.get_portion_rules(lib.tag('Bowl', 'recipe'))}
    assert rules == {('Grains', 'base', 8.0, 'f.oz'), ('Greens', 'fixed', 0.5, 'cup')}


def test_adding_greens_to_a_salad_splits_the_base(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    assert lib.qty(salad) == {'Romaine': 1.0}
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    assert lib.qty(salad) == {'Romaine': 0.5, 'Kale': 0.5}
    db.add_recipe_ingredient(salad, 'ingredient', pantry['arugula'], 1)
    assert lib.qty(salad) == pytest.approx({'Romaine': 0.3333, 'Kale': 0.3333, 'Arugula': 0.3333}, abs=1e-4)


def test_removing_a_green_resplits(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    db.delete_recipe_ingredient(salad, 'ingredient', pantry['kale'])
    assert lib.qty(salad) == {'Romaine': 1.0}


def test_rice_on_a_salad_is_a_fixed_topping(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['rice'], 1)
    assert lib.qty(salad) == {'Rice': 0.375}


def test_unruled_categories_keep_the_typed_quantity(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['feta'], 2)
    assert lib.rows(salad)['Feta'] == (2, None, None)


def test_switching_salad_to_wrap_and_bowl(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    for name in ('romaine', 'kale', 'rice', 'feta'):
        db.add_recipe_ingredient(salad, 'ingredient', pantry[name], 2 if name == 'feta' else 1)
    salad_tag, wrap_tag, bowl_tag = (lib.tag(n, 'recipe') for n in ('Salad', 'Wrap', 'Bowl'))

    db.transition_recipe_format(salad, salad_tag, wrap_tag)
    # 1 cup of greens split evenly; rice becomes the 4 f.oz grains base.
    assert lib.qty(salad) == pytest.approx({'Romaine': 1 / 6, 'Kale': 1 / 6, 'Rice': 0.5, 'Feta': 2}, abs=1e-4)

    db.transition_recipe_format(salad, wrap_tag, bowl_tag)
    # Greens are a 0.5 cup topping each; rice is the 8 f.oz base.
    assert lib.qty(salad) == pytest.approx({'Romaine': 1 / 6, 'Kale': 1 / 6, 'Rice': 1.0, 'Feta': 2}, abs=1e-4)

    db.transition_recipe_format(salad, bowl_tag, salad_tag)
    assert lib.qty(salad) == pytest.approx({'Romaine': 0.5, 'Kale': 0.5, 'Rice': 0.375, 'Feta': 2}, abs=1e-4)


def test_a_wrap_with_only_greens_stays_at_one_cup(lib, pantry):
    wrap = lib.recipe('Wrap', 'Wrap')
    db.add_recipe_ingredient(wrap, 'ingredient', pantry['romaine'], 1)
    assert lib.qty(wrap) == {'Romaine': pytest.approx(1 / 3, abs=1e-4)}


def test_switching_keeps_an_uneven_split(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    db.update_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 0.6)   # pins both greens
    db.update_recipe_ingredient(salad, 'ingredient', pantry['kale'], 0.3)
    db.transition_recipe_format(salad, lib.tag('Salad', 'recipe'), lib.tag('Wrap', 'recipe'))
    assert lib.qty(salad) == pytest.approx({'Romaine': 2 / 9, 'Kale': 1 / 9}, abs=1e-4)


def test_typing_a_quantity_pins_the_base_without_moving_neighbours(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    db.update_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 0.7)
    rows = lib.rows(salad)
    assert rows['Romaine'][:2] == (0.7, None)
    assert rows['Kale'][:2] == (0.5, None)
    db.apply_portion_rules(salad)
    assert lib.qty(salad) == {'Romaine': 0.7, 'Kale': 0.5}


def test_template_items_swap_and_follow_template_edits(lib, pantry):
    wrap_tag, bowl_tag = lib.tag('Wrap', 'recipe'), lib.tag('Bowl', 'recipe')
    db.add_tag_component(wrap_tag, 'ingredient', pantry['tortilla'], 1)
    bowl_item = db.add_tag_component(bowl_tag, 'ingredient', pantry['bowl'], 1)
    r = lib.recipe('R', None)
    db.transition_recipe_format(r, None, wrap_tag)
    assert set(lib.rows(r)) == {'Tortilla'}
    db.transition_recipe_format(r, wrap_tag, bowl_tag)
    assert set(lib.rows(r)) == {'Bowl'}

    db.update_tag_component_quantity(bowl_item, 2)
    changed = db.apply_template_to_recipes(bowl_tag)
    assert list(changed) == [r]
    assert lib.qty(r) == {'Bowl': 2}
    db.delete_tag_component(bowl_item)
    db.apply_template_to_recipes(bowl_tag)
    assert lib.rows(r) == {}


def test_rule_edits_reach_every_recipe_in_the_format(lib, pantry):
    salad_tag, greens = lib.tag('Salad', 'recipe'), lib.tag('Greens', 'ingredient')
    salads = [lib.recipe(f'S{i}', 'Salad') for i in range(3)]
    for s in salads:
        db.add_recipe_ingredient(s, 'ingredient', pantry['romaine'], 1)
    db.set_portion_rule(salad_tag, greens, 'base', 2, 'cup')
    assert set(db.apply_template_to_recipes(salad_tag)) == set(salads)
    assert all(lib.qty(s) == {'Romaine': pytest.approx(2 / 3, abs=1e-4)} for s in salads)
    assert db.apply_template_to_recipes(salad_tag) == {}   # nothing left to change


def test_changing_an_ingredients_unit_rederives(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    lib.sql("UPDATE Ingredients SET Unit = '1 cup' WHERE Id = ?;", (pantry['romaine'],))
    db.apply_portion_rules_for_ingredient(pantry['romaine'])
    assert lib.qty(salad) == {'Romaine': 3.0}


def test_recategorizing_an_ingredient_rederives(lib, pantry):
    bowl = lib.recipe('Bowl', 'Bowl')
    farro = lib.ingredient('Farro', '3 f.oz', 'Toppings')
    db.add_recipe_ingredient(bowl, 'ingredient', farro, 1)
    db.add_recipe_ingredient(bowl, 'ingredient', pantry['rice'], 1)
    assert lib.qty(bowl) == {'Farro': 1, 'Rice': 1.0}
    db.set_ingredient_tag(farro, lib.tag('Grains', 'ingredient'))   # pinned rows stay pinned
    assert lib.qty(bowl) == {'Farro': 1, 'Rice': 1.0}


def test_snapshots_restore_shares(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    before = db.snapshot_recipe_connections(salad)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    db.restore_recipe_connections(salad, before)
    assert lib.rows(salad)['Romaine'][:2] == (1.0, 1.0)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    assert lib.qty(salad) == {'Romaine': 0.5, 'Kale': 0.5}


def test_adoption_only_takes_rows_already_at_the_standard(lib, pantry):
    on_std, off_std = lib.recipe('On', 'Salad'), lib.recipe('Off', 'Wrap')
    for rid, ing, qty in ((on_std, 'romaine', 0.5), (on_std, 'kale', 0.5), (off_std, 'spinach', 0.15)):
        ing_id = pantry.get(ing) or lib.ingredient('Spinach', '3 cups', 'Greens')
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, ?);',
                (rid, ing_id, qty))
    con = __import__('sqlite3').connect(lib.path)
    try:
        assert setup.adopt_matching_portions(con.cursor()) == 2
        con.commit()
    finally:
        con.close()
    assert lib.rows(on_std)['Romaine'][1] == pytest.approx(0.5)
    assert lib.rows(off_std)['Spinach'] == (0.15, None, None)
    assert lib.qty(on_std) == {'Romaine': 0.5, 'Kale': 0.5}


def test_template_undo_restores_rules_items_and_recipes(lib, pantry):
    wrap_tag, greens = lib.tag('Wrap', 'recipe'), lib.tag('Greens', 'ingredient')
    db.add_tag_component(wrap_tag, 'ingredient', pantry['tortilla'], 1)
    wrap = lib.recipe('W', 'Wrap')
    db.apply_template_to_recipes(wrap_tag)
    db.add_recipe_ingredient(wrap, 'ingredient', pantry['romaine'], 1)
    template = db.snapshot_template(wrap_tag)
    db.set_portion_rule(wrap_tag, greens, 'base', 2, 'cup')
    db.delete_tag_component(db.get_tag_components(wrap_tag)[0]['id'])
    changed = db.apply_template_to_recipes(wrap_tag)
    assert lib.qty(wrap) == {'Romaine': pytest.approx(2 / 3, abs=1e-4)}
    db.restore_template(wrap_tag, template)
    for rid, rows in changed.items():
        db.restore_recipe_connections(rid, rows)
    assert db.snapshot_template(wrap_tag) == template
    assert lib.qty(wrap) == {'Romaine': pytest.approx(1 / 3, abs=1e-4), 'Tortilla': 1}


def test_hand_sized_recipes_are_counted(lib, pantry):
    wrap_tag = lib.tag('Wrap', 'recipe')
    pinned, ruled = lib.recipe('P', 'Wrap'), lib.recipe('R', 'Wrap')
    db.add_recipe_ingredient(ruled, 'ingredient', pantry['romaine'], 1)
    db.add_recipe_ingredient(pinned, 'ingredient', pantry['romaine'], 1)
    db.update_recipe_ingredient(pinned, 'ingredient', pantry['romaine'], 0.15)
    db.add_recipe_ingredient(pinned, 'ingredient', pantry['feta'], 1)   # no rule: not counted
    assert db.count_hand_sized_recipes(wrap_tag) == 1


def _salad_with_two_greens(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['kale'], 1)
    return salad


def test_typing_a_quantity_on_a_shared_base_resplits_it(lib, pantry):
    salad = _salad_with_two_greens(lib, pantry)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['arugula'], 1)
    db.set_base_quantity(salad, pantry['romaine'], 0.5)            # 1.5 of the 3 cups
    assert lib.qty(salad) == pytest.approx({'Romaine': 0.5, 'Kale': 0.25, 'Arugula': 0.25}, abs=1e-4)
    assert all(share is not None for _q, share, _t in lib.rows(salad).values())


def test_a_base_share_must_leave_room_for_the_others(lib, pantry):
    salad = _salad_with_two_greens(lib, pantry)
    assert db.base_quantity_problem(salad, pantry['romaine'], 1.0)
    assert db.base_quantity_problem(salad, pantry['romaine'], 0.8) is None
    alone = lib.recipe('Alone', 'Salad')
    db.add_recipe_ingredient(alone, 'ingredient', pantry['romaine'], 1)
    assert 'only ingredient' in db.base_quantity_problem(alone, pantry['romaine'], 0.5)


def test_pin_and_follow(lib, pantry):
    salad = _salad_with_two_greens(lib, pantry)
    db.set_base_quantity(salad, pantry['romaine'], 0.75)
    db.pin_portion(salad, pantry['kale'])                          # pins the whole base
    assert {n: s for n, (_q, s, _t) in lib.rows(salad).items()} == {'Romaine': None, 'Kale': None}
    lib.sql('UPDATE Connections SET Quantity = 0.1 WHERE ChildIngredient = ?;', (pantry['kale'],))
    assert db.follow_portion(salad, pantry['kale'])                # back on the rule, keeping 0.75 : 0.1
    assert lib.qty(salad) == pytest.approx({'Romaine': 0.75 / 0.85, 'Kale': 0.1 / 0.85}, abs=1e-4)
    db.split_base_evenly(salad, pantry['romaine'])
    assert lib.qty(salad) == {'Romaine': 0.5, 'Kale': 0.5}


def test_follow_refuses_what_a_rule_cant_size(lib, pantry):
    salad = lib.recipe('Salad', 'Salad')
    db.add_recipe_ingredient(salad, 'ingredient', pantry['feta'], 1)    # no rule for Cheese
    assert db.follow_portion(salad, pantry['feta']) is False
    cup = lib.ingredient('Croutons each', '1 ea', 'Greens')
    db.add_recipe_ingredient(salad, 'ingredient', cup, 1)
    assert db.follow_portion(salad, cup) is False


def test_components_query_describes_portions(lib, pantry):
    salad = _salad_with_two_greens(lib, pantry)
    db.add_recipe_ingredient(salad, 'ingredient', pantry['feta'], 1)
    rows = {r['Name']: r['Portion'] for r in db.recipe_components(salad)}
    assert rows['Feta'] is None
    assert rows['Romaine']['state'] == 'base' and rows['Romaine']['siblings'] == 2
    assert rows['Romaine']['pct'] == pytest.approx(0.5)
    db.pin_portion(salad, pantry['romaine'])
    assert db.recipe_components(salad)[0]['Portion']['state'] == 'hand'


def _pinned(lib, recipe_id, ingredient_id, qty):
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, ?);',
            (recipe_id, ingredient_id, qty))


def test_review_lists_hand_sized_rows_with_their_standard(lib, pantry):
    wrap, bowl, salad = lib.recipe('W', 'Wrap'), lib.recipe('B', 'Bowl'), lib.recipe('S', 'Salad')
    _pinned(lib, wrap, pantry['romaine'], 0.15)
    _pinned(lib, bowl, pantry['kale'], 0.15)
    _pinned(lib, bowl, pantry['feta'], 1)                      # no rule: not reviewed
    db.add_recipe_ingredient(salad, 'ingredient', pantry['romaine'], 1)   # follows already
    groups = {g['recipe']: g for g in db.portion_review()}
    assert set(groups) == {'W', 'B'}
    assert [(r['name'], r['standard']) for r in groups['W']['rows']] == [('Romaine', pytest.approx(1 / 3))]
    assert groups['B']['mode'] == 'fixed' and groups['B']['rows'][0]['standard'] == pytest.approx(1 / 6)
    assert groups['W']['cost_change'] == pytest.approx(1 / 3 - 0.15)   # Cost 1.0 per unit


def test_review_apply_and_undo(lib, pantry):
    wrap = lib.recipe('W', 'Wrap')
    _pinned(lib, wrap, pantry['romaine'], 0.1)
    _pinned(lib, wrap, pantry['kale'], 0.2)
    before = db.follow_portion_groups(db.portion_review())
    assert lib.qty(wrap) == pytest.approx({'Romaine': 1 / 9, 'Kale': 2 / 9}, abs=1e-4)
    assert db.portion_review() == []
    for rid, rows in before.items():
        db.restore_recipe_connections(rid, rows)
    assert lib.qty(wrap) == {'Romaine': 0.1, 'Kale': 0.2}


def test_review_flags_units_a_rule_cant_size(lib, pantry):
    wrap = lib.recipe('W', 'Wrap')
    leaf = lib.ingredient('Leaf', '1 ea', 'Greens')
    _pinned(lib, wrap, leaf, 1)
    (group,) = db.portion_review()
    assert group['rows'] == [] and [u['name'] for u in group['unsizable']] == ['Leaf']
