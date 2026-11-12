import db
from utilities import recipe_print as rp
from utilities.recipe_print import Tool

TOOLS = [
    Tool(1, 'Yellow', 'Disher', 1.0),
    Tool(2, 'Red', 'Disher', 2.0),
    Tool(3, 'White', 'Disher', 3.0),
    Tool(4, 'Grey', 'Disher', 4.0),
    Tool(5, 'Red slotted', 'Slotted', 2.0, pattern='striped'),
    Tool(6, 'Blue', 'Ice cream', 2.0),
    Tool(7, 'Tongs'),
]


def text(qty, unit, portion):
    use = rp.resolve_tool(qty, unit, portion, TOOLS)
    return use.text if use else None


def test_fraction_text():
    assert rp.fraction_text(1) == '1'
    assert rp.fraction_text(1.5) == '1½'
    assert rp.fraction_text(1 / 3) == '⅓'
    assert rp.fraction_text(0.999) == '1'
    assert rp.fraction_text(0.3) == '0.3'
    assert rp.fraction_text(2.125) == '2⅛'


def test_amounts():
    assert rp.amount(1 / 3, '3 cups').text == '1 cup'
    assert rp.amount(0.5, '3 cups').text == '1½ cups'
    assert rp.amount(0.5, '8 f.oz').text == '4 fl oz'
    assert rp.amount(2, '1 f.oz').text == '2 fl oz'
    assert rp.amount(1, '1 ea').text == '1 each'
    assert rp.amount(1, '1 w.oz').text == '1 wt oz'
    assert rp.amount(2, 'each').text == '2 each'
    assert rp.amount(1, '1/2 tsp').text == '½ tsp'


def test_scoop_resolution():
    # Half of "8 f.oz / 2 x grey" is one Grey.
    assert text(0.5, '8 f.oz', 'Grey') == '1 Grey'
    # The ingredient's own tool when it's a whole number of them.
    assert text(1, '8 f.oz', 'grey') == '2 × Grey'
    # Half a Red is a Yellow: same family, one scoop.
    assert text(0.5, '2 f.oz', 'Red') == '1 Yellow'
    # 6 fl oz: no single scoop, not whole Greys; fewest of another.
    assert text(1.5, '4 f.oz', 'Grey') == '2 × White'
    # Nothing fits: blank rather than a misleading scoop.
    assert text(0.75, '2 f.oz', 'Red') is None


def test_families_never_cross():
    # Slotted only has a 2 oz: half of one doesn't become a Yellow.
    assert text(0.5, '2 f.oz', 'Red slotted') is None
    assert text(2, '2 f.oz', 'Red slotted') == '2 × Red slotted'
    assert text(1, '2 f.oz', 'Blue') == '1 Blue'
    assert text(0.5, '4 f.oz', 'Blue') == '1 Blue'


def test_unsized_and_plain_text():
    assert text(0.5, '2 f.oz', 'Tongs') == 'Tongs'
    assert text(1, '.5 ea', 'Half') == 'Half'
    assert text(2, '.5 ea', 'Half') is None   # text describes one unit
    assert text(1, '', '') is None


def test_suggest_and_size_problem():
    assert rp.suggest_tool('2 x grey', '8 f.oz', TOOLS).name == 'Grey'
    assert rp.suggest_tool('Blue Scoop', '2 f.oz', TOOLS).name == 'Blue'
    assert rp.suggest_tool('scoop', '8 f.oz', TOOLS) is None
    red = TOOLS[1]
    assert rp.size_problem('3 f.oz', red)
    assert rp.size_problem('2 f.oz', red) is None
    assert rp.size_problem('4 f.oz', red) is None


def test_prints_row():
    napkin = {'TagName': 'Packaging', 'UnitCalories': 0}
    tortilla = {'TagName': 'Packaging', 'UnitCalories': 110}
    greens = {'TagName': 'Greens', 'UnitCalories': 10}
    assert rp.prints_row(greens, 'Salad')
    assert not rp.prints_row(napkin, 'Wrap')
    assert rp.prints_row(tortilla, 'Wrap')
    assert not rp.prints_row(tortilla, 'Salad')


def test_recipe_print_data(lib):
    spinach = lib.ingredient('Spinach', '3 cups', 'Greens')
    quinoa = lib.ingredient('Quinoa', '8 f.oz', 'Grains')
    wrap = lib.ingredient('Tortilla', '1 ea', 'Packaging')
    napkin = lib.ingredient('Napkin', '1 ea', 'Packaging')
    lib.sql("UPDATE Ingredients SET Calories = 110 WHERE Id = ?;", (wrap,))
    lib.sql("UPDATE Ingredients SET Portion = '2 x grey' WHERE Id = ?;", (quinoa,))
    rid = lib.recipe('Test Wrap', 'Wrap')
    wrap_tag = lib.tag('Wrap', 'recipe')
    for order, (ing, qty, tpl) in enumerate([(quinoa, 0.5, None), (spinach, 1 / 3, None),
                                              (wrap, 1, wrap_tag), (napkin, 1, wrap_tag)], start=1):
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity, SortOrder,'
                ' from_template_tag_id) VALUES (?, ?, ?, ?, ?);', (rid, ing, qty, order, tpl))

    # Unlinked "2 x grey" prints nothing; linking it through the review fixes that.
    review = {(r['portion'], r['unit']): r for r in db.get_portion_text_review()}
    assert review[('2 x grey', '8 f.oz')]['suggestion'] == 'Grey'
    assert db.link_portion_text('2 x grey', '8 f.oz', 'Grey') == 1

    data = db.recipe_print_data(rid)
    names = [r['name'] for r in data['rows']]
    assert names == ['Quinoa', 'Spinach', 'Tortilla']          # user order, napkin hidden
    quinoa_row = data['rows'][0]
    assert quinoa_row['amount'] == '4 fl oz'
    assert quinoa_row['tool'].text == '1 Grey'
    assert data['rows'][1]['amount'] == '1 cup'
    assert [t.name for t in data['tools_used']] == ['Grey']
    assert data['format']['name'] == 'Wrap'
    assert data['diets'][:4] == ['Vegan', 'Vegetarian', 'Dairy-free', 'Gluten-free']
    assert 'High protein' not in data['diets']
    assert 'Cost' not in data and 'cost' not in data


def test_rename_tool_carries_ingredients(lib):
    ing = lib.ingredient('Beets', '2 f.oz')
    lib.sql("UPDATE Ingredients SET Portion = 'red' WHERE Id = ?;", (ing,))
    red = next(t for t in db.get_portion_tools() if t['name'] == 'Red')
    assert red['used'] == 1
    db.update_portion_tool(red['id'], name='Red disher')
    assert lib.sql('SELECT Portion FROM Ingredients WHERE Id = ?;', (ing,))[0][0][0] == 'Red disher'


def test_print_branding_text_lives_in_the_library(lib):
    assert db.get_print_branding() == {}
    db.set_print_branding('footer', 'Internal use')
    assert db.get_print_branding() == {'footer': 'Internal use'}


def test_logo_travels_with_photos_only(lib, tmp_path):
    import os
    from utilities import backup
    images, brand = tmp_path / 'images', tmp_path / 'branding'
    images.mkdir()
    brand.mkdir()
    (brand / 'logo.svg').write_bytes(b'<svg/>')

    lean = str(tmp_path / 'lean.rwbackup')
    backup.create_backup(lean, include_images=False, db_path=lib.path,
                         images_dir=str(images), branding_dir=str(brand))
    assert backup.read_backup(lean).logo_name is None

    full = str(tmp_path / 'full.rwbackup')
    backup.create_backup(full, include_images=True, db_path=lib.path,
                         images_dir=str(images), branding_dir=str(brand))
    assert backup.read_backup(full).logo_name == 'logo.svg'

    # Merge: copied when there's no logo here, never over one.
    elsewhere = tmp_path / 'other-branding'
    report = backup.restore_merge(full, db_path=lib.path, images_dir=str(images),
                                  branding_dir=str(elsewhere), safety=False)
    assert report.logo_copied and (elsewhere / 'logo.svg').read_bytes() == b'<svg/>'
    os.remove(elsewhere / 'logo.svg')
    (elsewhere / 'logo.png').write_bytes(b'mine')
    report = backup.restore_merge(full, db_path=lib.path, images_dir=str(images),
                                  branding_dir=str(elsewhere), safety=False)
    assert not report.logo_copied and (elsewhere / 'logo.png').read_bytes() == b'mine'

    # Overwrite: the backup's logo replaces this one.
    backup.restore_overwrite(full, db_path=lib.path, images_dir=str(images),
                             branding_dir=str(elsewhere), safety=False)
    assert sorted(os.listdir(elsewhere)) == ['logo.svg']


def test_library_per_serving_divides_by_yield_once(lib):
    rice = lib.ingredient('Rice', '8 f.oz')
    lib.sql('UPDATE Ingredients SET Calories = 200, ProteinGrams = 4 WHERE Id = ?;', (rice,))
    rid = lib.recipe('Rice batch')
    lib.sql('UPDATE Recipes SET OutputQty = 4 WHERE Id = ?;', (rid,))
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity, SortOrder) VALUES (?, ?, 8, 1);',
            (rid, rice))
    extras = db.get_recipe_library_extras()[rid]
    assert extras['CaloriesPerServing'] == 400          # 8 × 200 kcal over 4 servings
    assert extras['PerServing']['Protein'] == 8
    assert db.recipe_print_data(rid)['nutrition']['Calories'] == 400


def test_card_label():
    label = rp.card_label('Ranch', '2 f.oz', 30, {'Calories': 200, 'SodiumMilligrams': 300})
    assert label['nutrition'] == {'Calories': 100, 'SodiumMilligrams': 150}
    assert (label['weight'], label['serving']) == (15, '1 fl oz (15 g)')
    # Not a volume: per one unit as entered.
    packet = rp.card_label('Avocado', '.5 ea', 61, {'Calories': 117})
    assert (packet['serving'], packet['nutrition']['Calories']) == ('½ each (61 g)', 117)


def test_nutrition_title():
    assert rp.nutrition_title('Cobb', False) is None
    assert rp.nutrition_title('Cobb', True) == 'Cobb (dressed)'
    assert rp.nutrition_title('Cobb', True, '  Cobb with ranch ') == 'Cobb with ranch'
    assert rp.nutrition_title('Cobb', False, 'As served') == 'As served'


def test_dressing_labels_and_statements(lib):
    greens = lib.ingredient('Greens', '3 cups', 'Greens')
    ranch = lib.ingredient('Ranch', '1 f.oz', 'Dressing')
    lib.sql('UPDATE Ingredients SET Calories = 120, Weight = 28 WHERE Id = ?;', (ranch,))
    db.set_ingredient_statement(ranch, '  buttermilk,   oil, salt ')
    rid = lib.recipe('Salad', 'Salad')
    for order, (ing, qty) in enumerate([(greens, 1), (ranch, 2)], start=1):
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity, SortOrder) VALUES (?, ?, ?, ?);',
                (rid, ing, qty, order))
    data = db.recipe_print_data(rid)
    by_name = {r['name']: r for r in data['rows']}
    assert by_name['Ranch']['statement'] == 'buttermilk,   oil, salt'
    assert by_name['Greens']['statement'] == ''
    assert [d['name'] for d in data['cards']] == ['Ranch']
    assert data['cards'][0]['nutrition']['Calories'] == 120
    assert data['nutrition']['Calories'] == 240     # the main panel includes the 2 oz on the recipe
    assert data['nutrition_title'] == 'Salad (dressed)'
    assert [(o['name'], o['shown'], o['default']) for o in data['card_options']] == [
        ('Greens', False, False), ('Ranch', True, True)]


def _salad_with_sides(lib):
    greens = lib.ingredient('Greens', '3 cups', 'Greens')
    ranch = lib.ingredient('Ranch', '1 f.oz', 'Dressing')
    vin = lib.recipe('House vinaigrette')
    oil = lib.ingredient('Oil', '1 f.oz')
    lib.sql('UPDATE Ingredients SET Calories = 240, Weight = 28 WHERE Id = ?;', (oil,))
    lib.sql("UPDATE Recipes SET Unit = '2 f.oz' WHERE Id = ?;", (vin,))
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 2);', (vin, oil))
    rid = lib.recipe('Salad', 'Salad')
    for order, (col, child) in enumerate([('ChildIngredient', greens), ('ChildIngredient', ranch),
                                          ('ChildRecipe', vin)], start=1):
        lib.sql(f'INSERT INTO Connections (ParentRecipe, {col}, Quantity, SortOrder) VALUES (?, ?, 1, ?);',
                (rid, child, order))
    return rid, greens, ranch, vin


def test_cards_and_title_follow_the_recipe(lib):
    rid, greens, ranch, vin = _salad_with_sides(lib)
    db.set_recipe_print_card(rid, ('ingredient', ranch), False)
    db.set_recipe_print_card(rid, ('recipe', vin), True)
    data = db.recipe_print_data(rid)
    # A sub-recipe's card is per 1 fl oz of what it makes: 480 kcal in 2 fl oz.
    assert [(c['name'], c['serving'], c['nutrition']['Calories']) for c in data['cards']] == [
        ('House vinaigrette', '1 fl oz (28 g)', 240)]
    db.set_recipe_print_title(rid, 'Salad, with vinaigrette')
    assert db.recipe_print_data(rid)['nutrition_title'] == 'Salad, with vinaigrette'
    db.set_recipe_print_title(rid, '  ')
    db.set_recipe_print_card(rid, ('ingredient', ranch), None)
    db.set_recipe_print_card(rid, ('recipe', vin), None)
    data = db.recipe_print_data(rid)
    assert (data['title_override'], [c['name'] for c in data['cards']]) == (None, ['Ranch'])


def test_no_cards_no_title(lib):
    rid, _g, ranch, _v = _salad_with_sides(lib)
    db.set_recipe_print_card(rid, ('ingredient', ranch), False)
    data = db.recipe_print_data(rid)
    assert (data['cards'], data['nutrition_title']) == ([], None)


def test_print_settings_copy_and_clean_up(lib):
    rid, greens, ranch, vin = _salad_with_sides(lib)
    db.set_recipe_print_card(rid, ('ingredient', greens), True)
    copy = db.create_recipe_with('Salad 2', 'ea', 1, copy_from=rid)
    assert db.recipe_print_settings(copy)['cards'] == {('ingredient', greens): True}
    lib.sql('DELETE FROM Ingredients WHERE Id = ?;', (greens,))
    assert db.recipe_print_settings(rid)['cards'] == {}
    db.set_recipe_print_card(rid, ('recipe', vin), True)
    lib.sql('DELETE FROM Recipes WHERE Id = ?;', (rid,))
    rows, _ = lib.sql('SELECT COUNT(*) FROM recipe_print_cards WHERE recipe_id = ?;', (rid,))
    assert rows == [(0,)]



def test_without_portions_drops_tools_and_scoop_key():
    data = {'rows': [{'name': 'Kale', 'tool': object()}], 'tools_used': [object()]}
    out = rp.without_portions(data)
    assert out['rows'][0]['tool'] is None and out['tools_used'] == [] and out['portions'] is False
    assert data['rows'][0]['tool'] is not None      # the original is untouched


def test_label_rounding():
    assert [rp.label_calories(v) for v in (682, 682.5, 683, 2.4, None)] == [680, 685, 685, 0, 0]
    assert rp.label_amount('SodiumMilligrams', 2284) == 2280
    assert rp.label_amount('SodiumMilligrams', 1735) == 1740
    assert rp.label_amount('TTLFatGrams', 43.8) == 44
    assert rp.label_amount('SatFatGrams', 0.5) == 1
    assert rp.label_amount('CholesterolMilligrams', 117.6) == 118


def test_merge_brings_print_settings_with_a_new_recipe(lib, tmp_path):
    from utilities import backup
    rid, greens, ranch, vin = _salad_with_sides(lib)
    db.set_recipe_print_card(rid, ('recipe', vin), True)
    db.set_recipe_print_card(rid, ('ingredient', ranch), False)
    db.set_recipe_print_title(rid, 'As served')
    path = str(tmp_path / 'b.rwbackup')
    backup.create_backup(path, db_path=lib.path, images_dir=str(tmp_path))
    lib.sql('DELETE FROM Connections WHERE ParentRecipe = ?;', (rid,))
    lib.sql('DELETE FROM Recipes WHERE Id = ?;', (rid,))
    backup.restore_merge(path, db_path=lib.path, images_dir=str(tmp_path),
                         branding_dir=str(tmp_path / 'brand'), safety=False)
    (new_id,), _ = lib.sql("SELECT Id FROM Recipes WHERE Name = 'Salad';")
    data = db.recipe_print_data(new_id[0])
    assert (data['nutrition_title'], [c['name'] for c in data['cards']]) == ('As served', ['House vinaigrette'])


def _long_page(statement, rows=10):
    return {'name': 'Long', 'unit': 'each', 'output_qty': 1, 'weight': None, 'format': None, 'tags': [],
            'diets': [], 'allergens': [], 'facility': [], 'free_of': [], 'portions': False,
            'rows': [{'name': f'Item {i}', 'type': 'ingredient', 'amount': '1 oz', 'tool': None,
                      'allergens': '', 'facility': '', 'from_template': False, 'statement': statement}
                     for i in range(rows)]}


def test_a_long_page_shrinks_statements_before_spilling():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    _app = QApplication.instance() or QApplication([])
    from gui.printing import recipe_page as page
    words = 'water, salt, sugar, vinegar, spices, garlic powder, onion powder, xanthan gum, ' * 3
    natural = page.RecipePageLayout(_long_page(words), 612.0, 792.0, 'Disclaimer.')
    fitted = page._fitted_layout(_long_page(words), 612.0, 792.0, 'Disclaimer.')
    assert len(natural.pages) == 2 and len(fitted.pages) == 1
    assert fitted.statement_pt < page.FIT_STEPS[0][0]
    # A page that fits as is keeps the normal look.
    short = page._fitted_layout(_long_page('water, salt', rows=4), 612.0, 792.0, '')
    assert (short.statement_pt, short.row_pad) == page.FIT_STEPS[0]
    # One that doesn't fit at any step runs on at the normal size.
    huge = page._fitted_layout(_long_page(words * 3, rows=14), 612.0, 792.0, '')
    assert len(huge.pages) > 1 and huge.statement_pt == page.FIT_STEPS[0][0]
