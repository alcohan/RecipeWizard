'''Filter + sort proxy for the Recipes Library.

Facets, combined with AND across groups (see RecipesFacetPane):
- formats: set of format names to show (SUB_RECIPES = no format);
  None means "no format filter".
- tags: set of recipe-tag ids (None = untagged); a recipe passes with
  any of them. Empty set = no tag filter.
- diets: set of diet keys; a recipe must fit all of them.
- categories: set of ingredient-category ids; a recipe must contain
  all of them somewhere in its tree.
- free_from: set of allergen names; a recipe containing any is hidden.
- max_food_cost: percent, or None. Recipes without a menu price are
  hidden while it's set (their food cost is unknown).
- text: substring of name, format, unit, allergens or tags.

The gallery filters through accepts_row, so both views show the same
recipes.
'''
from PySide6.QtCore import QSortFilterProxyModel, Qt

from gui.models.recipes_model import SORTS
from gui.widgets.recipes_facet_pane import SUB_RECIPES


class RecipesFacetProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self._formats = None
        self._tags = set()
        self._diets = set()
        self._categories = set()
        self._free_from = set()
        self._max_food_cost = None
        self._text = ''

    def set_facets(self, formats, tags=(), diets=(), categories=(), free_from=(), max_food_cost=None):
        self._formats = formats
        self._tags = set(tags or ())
        self._diets = set(diets or ())
        self._categories = set(categories or ())
        self._free_from = set(free_from or ())
        self._max_food_cost = max_food_cost
        self.invalidateFilter()

    def setFilterText(self, text):
        self._text = (text or '').strip().lower()
        self.invalidateFilter()

    def sort_by(self, key):
        '''Sort by one of the Sort menu's keys (recipes_model.SORTS).
        A header click afterwards goes back to sorting by that column.'''
        self._sort_key = SORTS[key][1]
        if self.sortColumn() == 0 and self.sortOrder() == Qt.AscendingOrder:
            # Already "sorted by column 0": Qt won't re-sort for the same
            # column, so force it with the new key.
            self.invalidate()
            return
        self._custom_sort = True
        try:
            self.sort(0, Qt.AscendingOrder)
        finally:
            self._custom_sort = False

    def sort(self, column, order=Qt.AscendingOrder):
        if not getattr(self, '_custom_sort', False):
            self._sort_key = None
        super().sort(column, order)

    def lessThan(self, left, right):
        key = getattr(self, '_sort_key', None)
        if key is None:
            return super().lessThan(left, right)
        model = self.sourceModel()
        return key(model.row_dict(left.row())) < key(model.row_dict(right.row()))

    def accepts_row(self, row):
        if self._formats is not None and (row.get('TagName') or SUB_RECIPES) not in self._formats:
            return False
        if self._tags and not ((None in self._tags and not row['TagIds'])
                               or self._tags.intersection(row['TagIds'])):
            return False
        if self._diets and not self._diets.issubset(row['Diets']):
            return False
        if self._categories and not self._categories.issubset(row['CategoryIds']):
            return False
        if self._free_from and self._free_from.intersection(row['Allergens']):
            return False
        if self._max_food_cost is not None:
            pct = row.get('FoodCostPct')
            if pct is None or pct > self._max_food_cost:
                return False
        if self._text and self._text not in row['SearchText']:
            return False
        return True

    def filterAcceptsRow(self, source_row, source_parent):
        return self.accepts_row(self.sourceModel().row_dict(source_row))
