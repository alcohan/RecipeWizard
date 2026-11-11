'''Archived ingredients: kept, and still used by recipes, but hidden from
the Ingredients place (unless Include archived is on), the add-to-recipe
picker and duplicate checks. Ctrl+K still finds them, last.'''
import db
from gui.models.ingredients_facet_proxy import IngredientsFacetProxy
from gui.models.ingredients_model import IngredientsModel
from gui.widgets.command_palette import CommandPalette


def _status(lib, iid):
    (row,), _ = lib.sql('SELECT status, updated_at FROM Ingredients WHERE Id = ?;', (iid,))
    return row


def test_archive_and_restore_are_not_edits(lib):
    iid = lib.ingredient('Old ranch', '1 f.oz', 'Dressing')
    lib.sql("UPDATE Ingredients SET updated_at = '2026-01-01 00:00:00' WHERE Id = ?;", (iid,))
    assert _status(lib, iid) == ('active', '2026-01-01 00:00:00')
    db.set_ingredient_status(iid, 'archived')
    assert _status(lib, iid) == ('archived', '2026-01-01 00:00:00')
    db.set_ingredient_status(iid, 'active')
    assert _status(lib, iid)[0] == 'active'


def test_recipes_keep_archived_ingredients(lib):
    iid = lib.ingredient('Old ranch', '1 f.oz', 'Dressing')
    rid = lib.recipe('Salad')
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (rid, iid))
    db.set_ingredient_status(iid, 'archived')
    assert [u['Name'] for u in db.get_ingredient_usage(iid)] == ['Salad']
    assert [r['name'] for r in db.recipe_print_data(rid)['rows']] == ['Old ranch']


def test_picker_leaves_out_archived(lib):
    keep = lib.ingredient('Ranch', '1 f.oz')
    old = lib.ingredient('Old ranch', '1 f.oz')
    rid = lib.recipe('Salad')
    db.set_ingredient_status(old, 'archived')
    names = {row[2] for row in db.get_eligible_ingredients(rid) if row[1] == 'ingredient'}
    assert keep and names == {'Ranch'}


def test_archiving_a_duplicate_settles_it(lib):
    a = lib.ingredient('Ranch', '1 f.oz')
    lib.ingredient('ranch', '1 f.oz')
    assert db.library_health()['duplicates'] == ['Ranch']
    db.set_ingredient_status(a, 'archived')
    assert db.library_health()['duplicates'] == []


def test_library_hides_archived_until_included(lib):
    lib.ingredient('Ranch', '1 f.oz')
    old = lib.ingredient('Old ranch', '1 f.oz')
    db.set_ingredient_status(old, 'archived')
    model = IngredientsModel()
    proxy = IngredientsFacetProxy()
    proxy.setSourceModel(model)
    proxy.set_facets(None, (), None)
    assert proxy.rowCount() == 1 and model.archived_count() == 1
    archived = model.row_dict(model.row_for_id(old))
    assert archived['Archived'] and not any(archived['Flags'].values())
    proxy.set_facets(None, (), None, (), include_archived=True)
    assert proxy.rowCount() == 2


def test_palette_ranks_archived_last():
    items = [(1, 'Old ranch', True), (2, 'Ranch', False), (3, 'Ranch dip')]
    assert CommandPalette._match(items, 'ranch') == [(2, 'Ranch', False), (3, 'Ranch dip', False),
                                                     (1, 'Old ranch', True)]
    assert [t[0] for t in CommandPalette._match(items, '')] == [2, 3, 1]


def test_purchase_import_skips_archived_for_new_mappings(lib):
    from utilities import purchase_import as pi
    keep = lib.ingredient('Romaine Hearts', '1 cup')
    old = lib.ingredient('Romaine Chopped', '1 cup')
    db.set_ingredient_status(old, 'archived')
    ings = pi.get_ingredients()
    assert {i['Id']: bool(i['Archived']) for i in ings} == {keep: False, old: True}
    item = {'vendor_key': 'k', 'inventory_item': '', 'description': 'ROMAINE CHOPPED HEARTS 6CT'}
    # Both names fit the text; only the active one may be suggested.
    assert pi.suggest_mapping(item, ings, [])['ingredient_id'] == keep
    sibling = {'vendor_key': 's', 'status': 'mapped', 'ingredient_id': old, 'inventory_item': 'Produce - Romaine'}
    item = dict(item, inventory_item='Produce - Romaine', description='LETTUCE')
    assert pi.suggest_mapping(item, ings, [sibling]) is None


def test_vendor_editor_keeps_an_archived_mapping(lib):
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from utilities import purchase_import as pi
    from gui.widgets.vendor_item_editor import VendorItemEditor
    keep = lib.ingredient('Ranch', '1 f.oz')
    old = lib.ingredient('Old ranch', '1 f.oz')
    db.set_ingredient_status(old, 'archived')
    editor = VendorItemEditor()
    editor.set_ingredients(pi.get_ingredients())
    assert editor.ingredient.findData(old) < 0            # not offered for new mappings
    editor.set_item({'ingredient_id': old, 'pack_size': ''})
    assert editor.ingredient.currentData() == old         # an existing one stays
    editor.set_item({'ingredient_id': keep, 'pack_size': ''})
    assert editor.ingredient.findData(old) < 0


def test_duplicate_keeps_print_settings(lib):
    dressing = lib.ingredient('Ranch', '1 f.oz', 'Dressing')
    rid = lib.recipe('Cobb')
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (rid, dressing))
    db.set_recipe_print_title(rid, 'Cobb, dressed')
    db.set_recipe_print_card(rid, ('ingredient', dressing), False)
    copy = db.duplicate_recipe(rid)
    assert db.recipe_print_settings(copy) == db.recipe_print_settings(rid)
