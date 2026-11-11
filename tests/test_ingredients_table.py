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


def _order(tab):
    from gui.models.ingredients_model import RowRole
    proxy = tab.proxy
    return [proxy.index(r, 0).data(RowRole)['Name'] for r in range(proxy.rowCount())]


def test_category_column_is_the_default_sort_and_gets_back_to_it(lib, qapp):
    from PySide6.QtCore import Qt
    from gui.models.ingredients_model import IngredientsModel
    from gui.tabs.ingredients_tab import IngredientsTab
    tags = {name: lib.tag(name, 'ingredient') for name in ('Greens', 'Protein')}
    first, second = 'Protein', 'Greens'                   # Configure's order, not alphabetical
    lib.sql('UPDATE tags SET sortOrder = 1 WHERE id = ?;', (tags[first],))
    lib.sql('UPDATE tags SET sortOrder = 2 WHERE id = ?;', (tags[second],))
    lib.ingredient('Zucchini', '1 oz', first)
    lib.ingredient('Apple', '1 oz', second)
    lib.ingredient('Kale', '1 oz', first)
    lib.ingredient('Mystery', '1 oz')                      # uncategorized sorts last

    model = IngredientsModel()
    tab = IngredientsTab(model, context_actions=[])
    tab._set_view('table', persist=False)
    tab.show()
    qapp.processEvents()
    header = tab.table.horizontalHeader()
    cat = model.COLUMNS.index('Category')
    default = ['Kale', 'Zucchini', 'Apple', 'Mystery']
    assert header.sortIndicatorSection() == cat
    assert _order(tab) == default
    assert 'sorted by category' in tab.count_label.text()

    tab.table.sortByColumn(model.COLUMNS.index('Name'), Qt.AscendingOrder)
    assert _order(tab) == ['Apple', 'Kale', 'Mystery', 'Zucchini']
    tab.table.sortByColumn(cat, Qt.AscendingOrder)       # the Category header: back to the default
    assert _order(tab) == default

    row = model.row_dict(model.row_for_id(next(r['Id'] for r in model._rows if r['Name'] == 'Mystery')))
    assert model.data(model.index(model.row_for_id(row['Id']), cat)) == 'Uncategorized'
