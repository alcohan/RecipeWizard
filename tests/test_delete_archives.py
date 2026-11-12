'''Delete archives the selection in the Library and Ingredients pages;
in a recipe editor it still removes the selected component.'''
import os

import pytest


@pytest.fixture
def qapp():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName('RecipeWizardTests')
    QCoreApplication.setApplicationName('RecipeWizardTests')
    yield app
    for w in app.topLevelWidgets():
        w.close()
        w.deleteLater()
    app.processEvents()


@pytest.fixture(autouse=True)
def no_dialogs(monkeypatch):
    '''A dialog would block the test run: fail instead.'''
    from PySide6.QtWidgets import QMessageBox

    def boom(*_a, **_k):
        raise AssertionError('unexpected dialog')
    monkeypatch.setattr(QMessageBox, 'exec', boom)
    monkeypatch.setattr(QMessageBox, 'question', boom)


@pytest.fixture
def menu(lib):
    romaine = lib.ingredient('Romaine', '1 oz', 'Greens')
    bacon = lib.ingredient('Bacon', '1 oz', 'Protein')
    spare = lib.ingredient('Spare', '1 oz', 'Greens')
    cobb = lib.recipe('Cobb', 'Salad')
    for ing in (romaine, bacon):
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (cobb, ing))
    return {'cobb': cobb, 'caesar': lib.recipe('Caesar', 'Salad'), 'romaine': romaine, 'spare': spare}


def _show(widget, qapp):
    from PySide6.QtTest import QTest
    widget.resize(1200, 800)
    widget.show()
    widget.activateWindow()
    QTest.qWaitForWindowActive(widget)
    qapp.processEvents()


def _status(lib, table, rid):
    return lib.sql(f'SELECT status FROM {table} WHERE Id = ?;', (rid,))[0][0][0]


def _recipes_tab(qapp):
    from gui.models.recipes_model import RecipesModel
    from gui.tabs.recipes_tab import RecipesTab
    tab = RecipesTab(RecipesModel(), context_actions=[])
    _show(tab, qapp)
    return tab


@pytest.mark.parametrize('view', ['table', 'gallery'])
def test_delete_archives_selected_recipe(lib, menu, qapp, view):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    tab = _recipes_tab(qapp)
    tab._set_view(view, persist=False)
    qapp.processEvents()
    tab._select_id(menu['caesar'])
    assert tab._selected_id == menu['caesar']
    target = tab.table if view == 'table' else tab.gallery.scroll
    target.setFocus()
    QTest.keyClick(target, Qt.Key_Delete)
    assert _status(lib, 'Recipes', menu['caesar']) == 'archived'
    QTest.keyClick(target, Qt.Key_Z, Qt.ControlModifier)     # undoable like the menu item
    assert _status(lib, 'Recipes', menu['caesar']) in (None, 'active')


def test_delete_in_library_filter_field_edits_text(lib, menu, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    tab = _recipes_tab(qapp)
    tab._select_id(menu['caesar'])
    tab.filter_edit.setFocus()
    tab.filter_edit.setText('Cae')
    tab.filter_edit.setCursorPosition(0)
    QTest.keyClick(tab.filter_edit, Qt.Key_Delete)
    assert tab.filter_edit.text() == 'ae'
    assert _status(lib, 'Recipes', menu['caesar']) in (None, 'active')


def test_delete_in_recipe_editor_removes_component_not_recipe(lib, menu, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    tab = _recipes_tab(qapp)
    tab.open_in_editor(menu['cobb'])
    editor = tab.editor_tabs.current_editor()
    table = editor.components_table
    before = editor.components_model.rowCount()
    table.setFocus()
    table.setCurrentIndex(editor.components_model.index(0, 0))
    QTest.keyClick(table, Qt.Key_Delete)
    assert editor.components_model.rowCount() == before - 1
    assert _status(lib, 'Recipes', menu['cobb']) in (None, 'active')


def test_delete_archives_selected_ingredient(lib, menu, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from gui.models.ingredients_model import IngredientsModel
    from gui.tabs.ingredients_tab import IngredientsTab
    tab = IngredientsTab(IngredientsModel(), context_actions=[])
    _show(tab, qapp)
    tab._set_view('table', persist=False)
    qapp.processEvents()
    tab._select_id(menu['spare'])
    qapp.processEvents()
    assert tab._selected_id == menu['spare']
    tab.table.setFocus()
    QTest.keyClick(tab.table, Qt.Key_Delete)
    assert _status(lib, 'Ingredients', menu['spare']) == 'archived'
    QTest.keyClick(tab.table, Qt.Key_Delete)                 # already archived: nothing happens
    assert _status(lib, 'Ingredients', menu['spare']) == 'archived'


def test_ingredient_editor_archives_and_restores(lib, menu, qapp, monkeypatch):
    from gui.dialogs import ingredient_edit
    dlg = ingredient_edit.IngredientEditDialog(menu['spare'])
    assert dlg.archive_btn.text() == 'Archive'
    assert dlg.toggle_archived()                               # unused: no question
    assert _status(lib, 'Ingredients', menu['spare']) == 'archived'
    assert dlg.archive_btn.text() == 'Restore' and dlg.modified
    assert dlg.toggle_archived()
    assert _status(lib, 'Ingredients', menu['spare']) == 'active'
    dlg.close()

    # In use: it asks, and Cancel leaves it alone.
    asked = []
    monkeypatch.setattr(ingredient_edit, 'confirm_archive_ingredient',
                        lambda *a: asked.append(a) or False)
    used = ingredient_edit.IngredientEditDialog(menu['romaine'])
    assert not used.toggle_archived() and asked
    assert _status(lib, 'Ingredients', menu['romaine']) in (None, 'active')
    used.close()

    # An archived ingredient opens showing Restore.
    lib.sql("UPDATE Ingredients SET status = 'archived' WHERE Id = ?;", (menu['spare'],))
    again = ingredient_edit.IngredientEditDialog(menu['spare'])
    assert again.archive_btn.text() == 'Restore'
    again.close()


def test_inspector_archive_buttons_show_the_key(lib, menu, qapp):
    tab = _recipes_tab(qapp)
    tab._select_id(menu['caesar'])
    tab._update_inspector()
    assert tab.inspector.archive_btn.text() == 'Archive   Del'


def test_archiving_an_ingredient_selects_the_next_row(lib, menu, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from gui.models.ingredients_model import IngredientsModel
    from gui.tabs.ingredients_tab import IngredientsTab
    extra = lib.ingredient('Zest', '1 oz', 'Greens')            # unused, so no question
    tab = IngredientsTab(IngredientsModel(), context_actions=[])
    _show(tab, qapp)
    tab._set_view('table', persist=False)
    qapp.processEvents()
    order = [tab.source_model.id_at_row(tab.proxy.mapToSource(tab.proxy.index(r, 0)).row())
             for r in range(tab.proxy.rowCount())]
    target = menu['spare']
    expected = order[order.index(target) + 1] if order.index(target) + 1 < len(order) else order[order.index(target) - 1]
    tab._select_id(target)
    qapp.processEvents()
    tab.table.setFocus()
    QTest.keyClick(tab.table, Qt.Key_Delete)
    for _ in range(3):
        qapp.processEvents()
    assert tab._selected_id == expected
    assert tab.table.currentIndex().row() == order.index(target)   # same place in the list
    # The last row falls back to the one above; a lone row has none.
    rows = [tab.source_model.id_at_row(tab.proxy.mapToSource(tab.proxy.index(r, 0)).row())
            for r in range(tab.proxy.rowCount())]
    assert tab._neighbor_id(rows[-1]) == rows[-2]
    assert tab._neighbor_id(rows[0]) == rows[1]


@pytest.mark.parametrize('view', ['table', 'gallery'])
def test_archiving_a_recipe_selects_the_next_one(lib, menu, qapp, view):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    lib.recipe('Dill Salad', 'Salad')
    tab = _recipes_tab(qapp)
    tab._set_view(view, persist=False)
    qapp.processEvents()
    order = tab.gallery.visible_ids() if view == 'gallery' else tab.visible_ids()
    order = list(dict.fromkeys(order))
    target = menu['caesar']
    i = order.index(target)
    expected = order[i + 1] if i + 1 < len(order) else order[i - 1]
    tab._select_id(target)
    target_widget = tab.table if view == 'table' else tab.gallery.scroll
    target_widget.setFocus()
    QTest.keyClick(target_widget, Qt.Key_Delete)
    for _ in range(3):
        qapp.processEvents()
    assert _status(lib, 'Recipes', target) == 'archived'
    assert tab._selected_id == expected
