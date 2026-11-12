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


def test_clicking_the_component_list_copies_it(lib, qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtTest import QTest
    from gui.models.recipes_model import RecipesModel
    from gui.widgets.recipe_inspector import RecipeInspector
    cobb = lib.recipe('Cobb', 'Salad')
    for name in ('Romaine', 'Bacon'):
        ing = lib.ingredient(name, '1 oz', 'Greens')
        lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (cobb, ing))
    model = RecipesModel()
    inspector = RecipeInspector()
    inspector.resize(360, 900)
    inspector.show()
    inspector.show_recipe(model.row_dict(model.row_for_id(cobb)))
    qapp.processEvents()
    QGuiApplication.clipboard().setText('')
    label = inspector.component_list
    QTest.mouseClick(label, Qt.LeftButton, pos=label.rect().center())
    copied = QGuiApplication.clipboard().text()
    assert sorted(copied.split(' • ')) == ['Bacon', 'Romaine']
    assert ' ' not in copied
    assert inspector.components_title.text() == 'COPIED'
    inspector._copied_timer.timeout.emit()
    assert inspector.components_title.text() == '2 COMPONENTS'


def test_pricing_ingredients_column_is_a_hover_list(qapp):
    from gui.widgets.recipe_matrix import RecipeMatrix
    from utilities import compare
    rows = [{'Id': 1, 'Name': 'Cobb', 'MenuPrice': 10}, {'Id': 2, 'Name': 'Ranch', 'MenuPrice': 0}]
    details = [{'recipe_id': 1, 'ingredient_name': 'Romaine', 'category': 'Greens', 'cost': 1},
               {'recipe_id': 1, 'ingredient_name': 'Bowl', 'category': 'Packaging', 'cost': 0.3},
               {'recipe_id': 2, 'ingredient_name': 'Buttermilk', 'category': 'Dairy', 'cost': 0.4}]
    data = compare.build(details, rows, [1, 2], ['Greens', 'Dairy', 'Packaging'])
    matrix = RecipeMatrix('pricing')
    matrix.set_data(data)
    col = [c[0] for c in matrix._columns].index('ingredients')
    item = matrix.table.item(0, col)
    assert item.text() == ''                                  # no count
    assert 'Greens: Romaine' in item.toolTip() and 'Packaging: Bowl' in item.toolTip()
    order = [r['id'] for r in matrix.rows()]
    matrix._on_header_clicked(col)                            # not sortable
    assert matrix._sort is None and [r['id'] for r in matrix.rows()] == order


def test_blanks_sort_lowest(qapp):
    from gui.models import ingredients_model, recipes_model
    from gui.widgets.recipe_matrix import RecipeMatrix
    from utilities import compare
    rows = [{'Id': 1, 'Name': 'Priced', 'MenuPrice': 10}, {'Id': 2, 'Name': 'Unpriced', 'MenuPrice': None},
            {'Id': 3, 'Name': 'Cheap', 'MenuPrice': 20}]
    details = [{'recipe_id': i, 'ingredient_name': 'X', 'category': 'Greens', 'cost': 1} for i in (1, 2, 3)]
    matrix = RecipeMatrix('pricing')
    matrix.set_data(compare.build(details, rows, [1, 2, 3], ['Greens']))
    for key in ('pct', 'price'):
        matrix.sort_by(key, descending=True)
        assert [r['name'] for r in matrix.rows()][-1] == 'Unpriced'
        matrix.sort_by(key, descending=False)
        assert [r['name'] for r in matrix.rows()][0] == 'Unpriced'

    # Ingredients: no supplier ("—") below any supplier name.
    assert ingredients_model._sort_key('Supplier', {'SupplierName': None}) < \
        ingredients_model._sort_key('Supplier', {'SupplierName': 'Apex'})

    # Library table: an unpriced recipe's food cost below 0%.
    model = recipes_model.RecipesModel.__new__(recipes_model.RecipesModel)
    from PySide6.QtCore import QAbstractTableModel
    QAbstractTableModel.__init__(model)
    model._rows = [{'Name': 'A', 'FoodCostPct': None, 'Archived': False},
                   {'Name': 'B', 'FoodCostPct': 0.0, 'Archived': False}]
    col = model.COLUMNS.index('FoodCostPct')
    from PySide6.QtCore import Qt
    keys = [model.data(model.index(r, col), Qt.UserRole) for r in range(2)]
    assert keys[0] < keys[1]


def test_sorting_keeps_column_widths(qapp):
    from gui.widgets.recipe_matrix import RecipeMatrix
    from utilities import compare
    rows = [{'Id': i, 'Name': f'Recipe {i}', 'MenuPrice': 10 + i} for i in (1, 2, 3)]
    details = [{'recipe_id': i, 'ingredient_name': 'X', 'category': 'Greens', 'cost': i} for i in (1, 2, 3)]
    for mode in ('pricing', 'nutrition'):
        matrix = RecipeMatrix(mode)
        matrix.resize(1400, 600)
        matrix.show()
        matrix.set_data(compare.build(details, rows, [1, 2, 3], ['Greens']))
        widths = lambda: [matrix.table.columnWidth(c) for c in range(matrix.table.columnCount())]
        before = widths()
        for col, (key, _h, _a, sort_key, _cell) in enumerate(matrix._columns):
            if sort_key is None:
                continue
            matrix._on_header_clicked(col)
            assert matrix.table.horizontalHeader().isSortIndicatorShown()
            assert widths() == before, (mode, key)
            matrix._on_header_clicked(col)
            assert widths() == before, (mode, key)
