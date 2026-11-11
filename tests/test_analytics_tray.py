'''The compare tray's one job now: choosing what Analytics shows.'''
import os

import pytest


@pytest.fixture
def qapp():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QCoreApplication, QSettings
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    QCoreApplication.setOrganizationName('RecipeWizardTests')
    QCoreApplication.setApplicationName('RecipeWizardTests')
    QSettings().remove('analytics')
    yield app
    for w in app.topLevelWidgets():     # leave no window to steal focus from later tests
        w.close()
        w.deleteLater()
    app.processEvents()
    QSettings().remove('analytics')


@pytest.fixture
def menu(lib):
    ids = {'cobb': lib.recipe('Cobb', 'Salad'), 'caesar': lib.recipe('Caesar', 'Salad'),
           'teriyaki': lib.recipe('Teriyaki', 'Bowl'), 'old': lib.recipe('Old Wrap', 'Wrap')}
    lib.sql("UPDATE Recipes SET status = 'archived' WHERE Id = ?;", (ids['old'],))
    return ids


def _tab():
    from gui.models.recipes_model import RecipesModel
    from gui.tabs.analytics_tab import AnalyticsTab
    model = RecipesModel()
    tab = AnalyticsTab(model)
    tab.show()                  # it rebuilds while visible, as in the app
    tab.refresh()
    return model, tab


def _names(tab):
    return [r['name'] for r in tab.data['recipes']]


def test_empty_tray_shows_every_active_recipe(lib, menu, qapp):
    _m, tab = _tab()
    assert tab.recipe_ids() == []
    assert set(tab.shown_ids()) == {menu['cobb'], menu['caesar'], menu['teriyaki']}
    assert tab.tray_note.isVisibleTo(tab) and not tab.clear_btn.isVisibleTo(tab)


def test_adding_narrows_to_the_tray_in_order_archived_included(lib, menu, qapp):
    _m, tab = _tab()
    assert tab.add_by_name('teriyaki') == menu['teriyaki']
    assert tab.add_by_name('Old') == menu['old']       # contains-match; archived is allowed when asked for
    assert tab.add_by_name('nope') is None
    assert tab.add_by_name('Teriyaki') == menu['teriyaki']   # already in: no duplicate
    assert tab.shown_ids() == [menu['teriyaki'], menu['old']]
    assert _names(tab) == ['Teriyaki', 'Old Wrap']
    assert [r.recipe_id for r in tab.tray_list.rows] == [menu['teriyaki'], menu['old']]
    assert tab.clear_btn.isVisibleTo(tab)


def test_filters_narrow_tray_or_all(lib, menu, qapp):
    _m, tab = _tab()
    salad = next(t['id'] for t in tab._formats if t['name'] == 'Salad')
    tab.set_filter('format', salad)
    assert set(tab.shown_ids()) == {menu['cobb'], menu['caesar']}
    tab.add_by_name('Teriyaki')
    assert tab.shown_ids() == []                        # tray ∩ filter
    assert tab._empty_notes['pricing'].text() == 'No recipes match the filters.'


def test_clear_all_resets_tray_and_filters(lib, menu, qapp):
    _m, tab = _tab()
    tab.add_by_name('Cobb')
    tab.set_filter('format', tab._formats[0]['id'])
    tab.clear_all()
    assert tab.recipe_ids() == [] and tab.filters() == {'format': None, 'tag': None}
    assert tab.format_combo.currentIndex() == 0
    assert len(tab.shown_ids()) == 3
    tab.clear_all()                                      # clearing an empty tray still works
    assert len(tab.shown_ids()) == 3


def test_tray_and_filters_are_remembered(lib, menu, qapp):
    _m, tab = _tab()
    tab.add_by_name('Caesar')
    tab.add_by_name('Cobb')
    _m2, again = _tab()
    assert again.recipe_ids() == [menu['caesar'], menu['cobb']]


def test_deleted_recipe_leaves_the_tray(lib, menu, qapp):
    import db
    model, tab = _tab()
    tab.add_by_name('Caesar')
    tab.add_by_name('Cobb')
    db.delete_recipe(menu['cobb'])
    model.refresh()
    tab.refresh()
    assert tab._tray.ids() == [menu['caesar']]
    _m2, again = _tab()                                 # and the saved tray follows
    assert again._tray.ids() == [menu['caesar']]


def test_tray_change_while_hidden_shows_on_return(lib, menu, qapp):
    _m, tab = _tab()
    qapp.processEvents()
    tab.hide()
    tab._tray.add(menu['cobb'])
    assert tab.tray_list.rows == []                      # not rebuilt while hidden
    tab.show()
    qapp.processEvents()
    assert [r.recipe_id for r in tab.tray_list.rows] == [menu['cobb']]
    assert tab.shown_ids() == [menu['cobb']]
    tab.hide()


def test_print_shown_emits_what_is_shown(lib, menu, qapp):
    _m, tab = _tab()
    got = []
    tab.printRequested.connect(lambda ids, portions: got.append((ids, portions)))
    tab.print_shown()
    assert set(got[0][0]) == {menu['cobb'], menu['caesar'], menu['teriyaki']} and got[0][1] is True
    tab.add_by_name('Cobb')
    tab.print_shown(portions=False)
    assert got[1] == ([menu['cobb']], False)
    assert tab.print_btn.isEnabled()
    tab.set_filter('format', next(t['id'] for t in tab._formats if t['name'] == 'Bowl'))
    assert tab.print_shown() == [] and len(got) == 2 and not tab.print_btn.isEnabled()


def test_saved_comparison_keeps_tray_and_filters(lib, menu, qapp):
    _m, tab = _tab()
    tab.add_by_name('Cobb')
    tab.add_by_name('Teriyaki')
    salad = next(t['id'] for t in tab._formats if t['name'] == 'Salad')
    tab.set_filter('format', salad)
    cid = tab.save_comparison('Salads')
    assert tab.active_saved() == cid
    tab.clear_all()
    assert tab.active_saved() is None
    tab.load_comparison(cid)
    assert tab.recipe_ids() == [menu['cobb'], menu['teriyaki']]
    assert tab.filters()['format'] == salad and tab.shown_ids() == [menu['cobb']]
    assert tab.active_saved() == cid
