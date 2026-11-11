import hashlib

import pytest

from utilities import scenarios as sc


def _connect(lib, parent, ingredient=None, qty=1.0, recipe=None):
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, ChildRecipe, Quantity) VALUES (?, ?, ?, ?);',
            (parent, ingredient, recipe, qty))


def _price(lib, rid, price):
    lib.sql('UPDATE Recipes SET menu_price = ? WHERE Id = ?;', (price, rid))


@pytest.fixture
def menu(lib):
    '''A salad, a bowl and a wrap, each with lettuce and its packaging.'''
    m = {
        'lettuce': lib.ingredient('Lettuce', '1 cup', cost=1.00),
        'salad_bowl': lib.ingredient('Salad Bowl 32oz', '1 ea', 'Packaging', cost=0.30),
        'grain_bowl': lib.ingredient('Grain Bowl 24oz', '1 ea', 'Packaging', cost=0.25),
        'tortilla': lib.ingredient('Tortilla', '1 ea', cost=0.40),
        'air_salad': lib.ingredient('Airport Salad Bowl', '1 ea', 'Packaging', cost=0.50),
        'air_grain': lib.ingredient('Airport Grain Bowl', '1 ea', 'Packaging', cost=0.45),
        'bag': lib.ingredient('Paper Bag', '1 ea', 'Packaging', cost=0.10),
    }
    m['salad'] = lib.recipe('Cobb Salad', 'Salad')
    m['bowl'] = lib.recipe('Teriyaki Bowl', 'Bowl')
    m['wrap'] = lib.recipe('Chicken Wrap', 'Wrap')
    _connect(lib, m['salad'], m['lettuce'], 2)
    _connect(lib, m['salad'], m['salad_bowl'])
    _connect(lib, m['bowl'], m['lettuce'])
    _connect(lib, m['bowl'], m['grain_bowl'])
    _connect(lib, m['wrap'], m['lettuce'])
    _connect(lib, m['wrap'], m['tortilla'])
    _price(lib, m['salad'], 10.0)
    _price(lib, m['bowl'], 12.0)
    _price(lib, m['wrap'], 10.0)
    m['Salad'] = lib.tag('Salad', 'recipe')
    m['Bowl'] = lib.tag('Bowl', 'recipe')
    m['Wrap'] = lib.tag('Wrap', 'recipe')
    return m


def _cells(result, sid):
    return {r['id']: r['cells'][sid] for r in result['recipes']}


def _base(result):
    return {r['id']: r['base'] for r in result['recipes']}


def test_empty_scenario_equals_baseline(lib, menu):
    sid = sc.create_scenario('Nothing')
    result = sc.matrix()
    for rid, base in _base(result).items():
        cell = _cells(result, sid)[rid]
        assert cell['cost'] == pytest.approx(base['cost'])
        assert cell['price'] == base['price']
        assert cell['applied'] == []
    assert _base(result)[menu['salad']]['cost'] == pytest.approx(2.30)
    assert _base(result)[menu['salad']]['pct'] == pytest.approx(23.0)


def test_substitution_scoped_to_format(lib, menu):
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    sc.add_rule(sid, 'substitute', menu['Bowl'], menu['grain_bowl'], menu['air_grain'])
    cells = _cells(sc.matrix(), sid)
    assert cells[menu['salad']]['cost'] == pytest.approx(2.50)
    assert cells[menu['bowl']]['cost'] == pytest.approx(1.45)
    assert cells[menu['wrap']]['cost'] == pytest.approx(1.40)
    assert cells[menu['wrap']]['applied'] == []
    assert cells[menu['salad']]['applied'][0]['delta'] == pytest.approx(0.20)


def test_substitution_ratio(lib, menu):
    sid = sc.create_scenario('Double')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'], quantity=2)
    assert _cells(sc.matrix(), sid)[menu['salad']]['cost'] == pytest.approx(3.00)


def test_add_and_remove(lib, menu):
    out = sc.create_scenario('Take-out')
    sc.add_rule(out, 'add', to_ingredient=menu['bag'], quantity=1)
    inside = sc.create_scenario('In-store')
    sc.add_rule(inside, 'remove', menu['Salad'], from_ingredient=menu['salad_bowl'])
    result = sc.matrix()
    assert _cells(result, out)[menu['wrap']]['cost'] == pytest.approx(1.50)
    assert _cells(result, out)[menu['salad']]['cost'] == pytest.approx(2.40)
    assert _cells(result, inside)[menu['salad']]['cost'] == pytest.approx(2.00)
    assert _cells(result, inside)[menu['bowl']]['cost'] == pytest.approx(1.25)


def test_add_divides_by_output(lib, menu):
    batch = lib.recipe('Big Salad', 'Salad')
    lib.sql('UPDATE Recipes SET OutputQty = 4 WHERE Id = ?;', (batch,))
    _connect(lib, batch, menu['lettuce'], 4)
    sid = sc.create_scenario('Take-out')
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'], quantity=4)
    assert _cells(sc.matrix([batch]), sid)[batch]['cost'] == pytest.approx(1.10)


def test_nested_sub_recipe(lib, menu):
    kit = lib.recipe('Salad Kit')
    _connect(lib, kit, menu['salad_bowl'])
    outer = lib.recipe('Kit Salad', 'Salad')
    _connect(lib, outer, menu['lettuce'])
    _connect(lib, outer, recipe=kit)
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    cells = _cells(sc.matrix([outer, kit]), sid)
    assert cells[outer]['cost'] == pytest.approx(1.50)
    # The kit itself has no format, so the Salad rule doesn't reach it.
    assert cells[kit]['cost'] == pytest.approx(0.30)


def test_specific_format_beats_all_recipes(lib, menu):
    sid = sc.create_scenario('Mixed')
    sc.add_rule(sid, 'remove', None, from_ingredient=menu['salad_bowl'])
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    cell = _cells(sc.matrix(), sid)[menu['salad']]
    assert cell['cost'] == pytest.approx(2.50)
    assert [a['action'] for a in cell['applied']] == ['substitute']


def test_first_rule_wins_among_equals(lib, menu):
    sid = sc.create_scenario('Twice')
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'], quantity=1)
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'], quantity=3)
    assert _cells(sc.matrix(), sid)[menu['wrap']]['cost'] == pytest.approx(1.50)


def test_rule_exclusion_by_tag(lib, menu):
    kids = lib.sql("INSERT INTO tags (name, kind) VALUES ('Kids', 'recipe_tag');")[1]
    kid = lib.recipe('Kids Salad', 'Salad')
    _connect(lib, kid, menu['salad_bowl'])
    lib.sql('INSERT INTO recipe_tags_mapping (tag_id, recipe_id) VALUES (?, ?);', (kids, kid))
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'], except_tags=[kids])
    cells = _cells(sc.matrix(), sid)
    assert cells[kid]['cost'] == pytest.approx(0.30)
    assert cells[menu['salad']]['cost'] == pytest.approx(2.50)


def test_scenario_exclusion_by_format(lib, menu):
    sid = sc.create_scenario('No wraps')
    sc.set_scenario_exclusions(sid, [menu['Wrap']])
    cells = _cells(sc.matrix(), sid)
    assert cells[menu['wrap']]['excluded'] is True
    assert cells[menu['wrap']]['cost'] is None
    assert cells[menu['salad']]['excluded'] is False


def test_menu_prices(lib, menu):
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'price_adjust', menu['Salad'], amount=1.50)
    sc.add_rule(sid, 'price_adjust', None, amount=0.50)
    sc.set_price(sid, menu['bowl'], 15.0)
    unpriced = lib.recipe('New Salad', 'Salad')
    _connect(lib, unpriced, menu['lettuce'])
    cells = _cells(sc.matrix(), sid)
    assert cells[menu['salad']]['price'] == pytest.approx(11.50)   # Salad rule beats the general one
    assert cells[menu['wrap']]['price'] == pytest.approx(10.50)
    assert cells[menu['bowl']]['price'] == pytest.approx(15.0)     # per-recipe price wins
    assert cells[menu['bowl']]['pct'] == pytest.approx(1.25 / 15 * 100)
    assert cells[unpriced]['price'] is None and cells[unpriced]['pct'] is None
    sc.set_price(sid, menu['bowl'], None)
    assert _cells(sc.matrix(), sid)[menu['bowl']]['price'] == pytest.approx(12.50)


def test_matrix_never_writes(lib, menu):
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'])
    sc.add_rule(sid, 'price_adjust', amount=2)
    sc.set_price(sid, menu['bowl'], 15.0)
    before = hashlib.sha256(open(lib.path, 'rb').read()).hexdigest()
    sc.matrix()
    sc.matrix([menu['salad']], [sid])
    assert hashlib.sha256(open(lib.path, 'rb').read()).hexdigest() == before
    rows, _ = lib.sql('SELECT menu_price FROM Recipes WHERE Id = ?;', (menu['bowl'],))
    assert rows == [(12.0,)]


def test_matrix_order_and_subset(lib, menu):
    a, b = sc.create_scenario('A'), sc.create_scenario('B')
    sc.reorder_scenarios([b, a])
    assert [s['name'] for s in sc.matrix()['scenarios']] == ['B', 'A']
    result = sc.matrix([menu['wrap'], menu['salad']], [a])
    assert [r['id'] for r in result['recipes']] == [menu['wrap'], menu['salad']]
    assert list(result['recipes'][0]['cells']) == [a]


def test_archived_recipes_left_out_by_default(lib, menu):
    lib.sql("UPDATE Recipes SET status = 'archived' WHERE Id = ?;", (menu['wrap'],))
    assert menu['wrap'] not in {r['id'] for r in sc.matrix()['recipes']}


def test_rule_validation(lib, menu):
    sid = sc.create_scenario('Bad')
    with pytest.raises(ValueError):
        sc.add_rule(sid, 'substitute', from_ingredient=menu['salad_bowl'])
    with pytest.raises(ValueError):
        sc.add_rule(sid, 'explode')
    rule = sc.add_rule(sid, 'add', to_ingredient=menu['bag'])
    with pytest.raises(ValueError):
        sc.update_rule(rule, action='remove')
    sc.update_rule(rule, quantity=2)
    assert sc.get_scenarios()[0]['rules'][0]['quantity'] == 2


def test_snapshot_restore_and_duplicate(lib, menu):
    kids = lib.sql("INSERT INTO tags (name, kind) VALUES ('Kids', 'recipe_tag');")[1]
    sid = sc.create_scenario('SeaTac')
    rule = sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'], except_tags=[kids])
    sc.set_scenario_exclusions(sid, [menu['Wrap']])
    sc.set_price(sid, menu['bowl'], 15.0)
    snap = sc.snapshot(sid)
    before = sc.get_scenarios()
    sc.delete_rule(rule)
    sc.set_price(sid, menu['bowl'], None)
    sc.set_scenario_exclusions(sid, [])
    sc.restore(sid, snap)
    assert sc.get_scenarios() == before

    copy = sc.duplicate_scenario(sid, 'SeaTac copy')
    got = {s['name']: s for s in sc.get_scenarios()}['SeaTac copy']
    assert got['id'] == copy
    assert got['rules'][0]['except_tags'] == [kids]
    assert got['rules'][0]['id'] != rule
    assert got['exclusions'] == [menu['Wrap']] and got['prices'] == {menu['bowl']: 15.0}


def test_deletes_cascade(lib, menu):
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'])
    sc.set_price(sid, menu['wrap'], 11.0)
    lib.sql('DELETE FROM Ingredients WHERE Id = ?;', (menu['bag'],))
    lib.sql('DELETE FROM Recipes WHERE Id = ?;', (menu['wrap'],))
    s = sc.get_scenarios()[0]
    assert s['rules'] == [] and s['prices'] == {}
    sc.delete_scenario(sid)
    for table in ('scenario_rules', 'scenario_exclusions', 'scenario_prices'):
        assert lib.sql(f'SELECT COUNT(*) FROM {table};')[0] == [(0,)]


def test_backup_merge_brings_scenarios(lib, menu, tmp_path):
    from utilities import backup
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    sc.set_price(sid, menu['bowl'], 15.0)
    path = str(tmp_path / 'b.rwbackup')
    backup.create_backup(path, db_path=lib.path, images_dir=str(tmp_path))
    sc.delete_scenario(sid)
    report = backup.restore_merge(path, db_path=lib.path, images_dir=str(tmp_path),
                                  branding_dir=str(tmp_path / 'brand'), safety=False)
    assert report.added['scenarios'] == ['SeaTac']
    got = sc.get_scenarios()[0]
    assert got['rules'][0]['to_ingredient'] == menu['air_salad']
    assert got['prices'] == {menu['bowl']: 15.0}


def test_snapshot_all_restores_ids(lib, menu):
    sid = sc.create_scenario('SeaTac')
    rule = sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    sc.set_rule_exclusions(rule, [menu['Wrap']])
    sc.set_price(sid, menu['bowl'], 15.0)
    snap = sc.snapshot_all()
    before = sc.get_scenarios()
    sc.delete_scenario(sid)
    sc.create_scenario('Other')
    sc.restore_all(snap)
    assert sc.get_scenarios() == before


def test_restore_all_skips_deleted_references(lib, menu):
    sid = sc.create_scenario('Take-out')
    sc.add_rule(sid, 'add', to_ingredient=menu['bag'])
    snap = sc.snapshot_all()
    lib.sql('DELETE FROM Ingredients WHERE Id = ?;', (menu['bag'],))
    sc.restore_all(snap)
    assert sc.get_scenarios()[0]['rules'] == []


# --- the Configure page --------------------------------------------------

@pytest.fixture
def qapp():
    import os
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    # Keep the tests' QSettings away from the real app's.
    QCoreApplication.setOrganizationName('RecipeWizardTests')
    QCoreApplication.setApplicationName('RecipeWizardTests')
    QSettings().remove('analytics')
    return app


def test_page_edits_undo_and_redo(lib, menu, qapp):
    from gui.tabs.scenarios_page import ScenariosPage
    page = ScenariosPage()
    assert page.empty.isVisibleTo(page) and not page.scroll.isVisibleTo(page)
    page.new_scenario()
    sid = page.current_id()
    assert [s['name'] for s in sc.get_scenarios()] == ['New scenario']
    page._do('Add rule', lambda: sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'],
                                               menu['air_salad']) and None)
    # one card per format plus All recipes
    assert page.rules_box.count() == len(page._formats) + 1
    page.name_edit.setText('SeaTac')
    page._on_name()
    assert sc.get_scenarios()[0]['name'] == 'SeaTac'

    page.undo_stack.undo()      # rename
    page.undo_stack.undo()      # rule
    assert sc.get_scenarios()[0]['name'] == 'New scenario'
    assert sc.get_scenarios()[0]['rules'] == []
    page.undo_stack.redo()
    page.undo_stack.redo()
    s = sc.get_scenarios()[0]
    assert s['name'] == 'SeaTac' and len(s['rules']) == 1 and page.current_id() == sid


def test_page_price_cell_and_delete_undo(lib, menu, qapp):
    from gui.tabs.scenarios_page import ScenariosPage
    page = ScenariosPage()
    page.new_scenario()
    sid = page.current_id()
    row = next(i for i in range(page.prices.rowCount())
               if page.prices.item(i, 0).data(0x0100) == menu['bowl'])
    page.prices.item(row, 2).setText('$15.00')
    qapp.processEvents()
    assert sc.get_scenarios()[0]['prices'] == {menu['bowl']: 15.0}

    # Delete asks first; go through _do as delete_current does after Yes.
    page._do('Delete scenario', lambda: sc.delete_scenario(sid) or 0)
    assert sc.get_scenarios() == [] and page.empty.isVisibleTo(page)
    page.undo_stack.undo()
    assert sc.get_scenarios()[0]['id'] == sid and page.current_id() == sid
    assert sc.get_scenarios()[0]['prices'] == {menu['bowl']: 15.0}


# --- Analytics --------------------------------------------------------------

def _seatac(menu):
    sid = sc.create_scenario('SeaTac')
    sc.add_rule(sid, 'substitute', menu['Salad'], menu['salad_bowl'], menu['air_salad'])
    sc.set_price(sid, menu['bowl'], 15.0)
    return sid


def test_describe_rule(lib, menu):
    names = {menu['salad_bowl']: 'Salad Bowl', menu['air_salad']: 'Airport Bowl', menu['bag']: 'Bag'}
    assert sc.describe_rule({'action': 'substitute', 'from_ingredient': menu['salad_bowl'],
                             'to_ingredient': menu['air_salad'], 'quantity': None,
                             'except_tags': [7]}, names, {7: 'Kids'}) == 'Swap Salad Bowl → Airport Bowl · except Kids'
    assert sc.describe_rule({'action': 'add', 'to_ingredient': menu['bag'], 'quantity': 2}, names) == 'Add Bag × 2'
    assert sc.describe_rule({'action': 'price_adjust', 'amount': -0.5}, names) == 'Menu price −$0.50'


def test_csv_rows_and_averages(lib, menu):
    sid = _seatac(menu)
    out = sc.create_scenario('Take-out')
    sc.set_scenario_exclusions(out, [menu['Wrap']])
    result = sc.matrix()
    rows = sc.csv_rows(result, {menu['Salad']: 'Salad'})
    assert rows[0] == list(sc.CSV_HEADER)
    assert len(rows) == 1 + 3 * 3
    cobb = [r for r in rows if r[0] == 'Cobb Salad']
    assert cobb[0][:6] == ['Cobb Salad', 'Salad', 'Baseline', 2.3, 10.0, 23.0]
    assert cobb[1][2:8] == ['SeaTac', 2.5, 10.0, 25.0, 0.2, 2.0]
    assert [r for r in rows if r[0] == 'Chicken Wrap'][2][-1] == 'Yes'
    avg = sc.averages(result, [menu['salad'], menu['bowl']])
    assert avg['base'] == pytest.approx((23.0 + 1.25 / 12 * 100) / 2)
    assert avg[sid] == pytest.approx((25.0 + 1.25 / 15 * 100) / 2)   # bowl keeps its packaging
    assert sc.averages(result, [menu['wrap']])[out] is None


def test_matrix_view_filters_and_export(lib, menu, qapp):
    from gui.widgets.scenario_matrix import ScenarioMatrix
    view = ScenarioMatrix()
    view.refresh()
    assert view.empty_card.isVisibleTo(view) and not view.body.isVisibleTo(view)
    sid = _seatac(menu)
    sc.create_scenario('Take-out')
    view.refresh()
    assert view.body.isVisibleTo(view)
    assert len(view.scenario_ids()) == 2                     # all chosen by default
    assert view.table.columnCount() == 3 + 2 * 3
    assert view.table.rowCount() == 3 + 1                    # recipes + average row
    view.set_chosen(view.scenario_ids()[1], False)
    assert view.scenario_ids() == [sid] and view.table.columnCount() == 6

    view.changed_only.setChecked(True)
    assert {r['id'] for r in view.visible_recipes()} == {menu['salad'], menu['bowl']}
    view.changed_only.setChecked(False)
    view.format_combo.setCurrentIndex(view.format_combo.findData(menu['Salad']))
    view._on_filter()
    assert [r['id'] for r in view.visible_recipes()] == [menu['salad']]
    tip = view.table.item(0, 3).toolTip()
    assert 'Swap Salad Bowl 32oz → Airport Salad Bowl' in tip and '+$0.20' in tip

    rows = view.csv_rows()
    assert [r[2] for r in rows[1:]] == ['Baseline', 'SeaTac']


def test_matrix_view_left_out_spans(lib, menu, qapp):
    from gui.widgets.scenario_matrix import ScenarioMatrix
    sid = sc.create_scenario('No wraps')
    sc.set_scenario_exclusions(sid, [menu['Wrap']])
    view = ScenarioMatrix()
    view.refresh()
    row = next(i for i, r in enumerate(view._shown) if r['id'] == menu['wrap'])
    assert view.table.item(row, 3).text() == 'Left out'
    assert view.table.columnSpan(row, 3) == 3
