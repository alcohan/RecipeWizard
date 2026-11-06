'''Filter + sort proxy for the Recipes Library.

Filters come as one state dict (RecipesFacetPane.state(), which saved
views store as JSON), combined with AND across keys:
- formats: list of format names to show (SUB_RECIPES = no format);
  None means "no format filter".
- tags: recipe-tag ids (None = untagged); a recipe passes with any of
  them. Empty = no tag filter.
- diets: diet keys; a recipe must fit all of them.
- categories: ingredient-category ids; a recipe must contain all of
  them somewhere in its tree.
- free_from: allergen names; a recipe containing any is hidden.
- max_food_cost: percent, or None. Recipes without a menu price are
  hidden while it's set (their food cost is unknown).
- include_archived: archived recipes are hidden unless it's set.
- needs_review: only recipes with ReviewReasons (the Needs review view).

Plus the toolbar's text filter: a substring of name, format, unit,
allergens or tags (not part of the state; views don't save it).

matches() is shared with the filter pane, which counts each saved view.
The gallery filters through accepts_row, so both views show the same
recipes.
'''
from PySide6.QtCore import QSortFilterProxyModel, Qt

from gui.models.recipes_model import SORTS, SUB_RECIPES
from utilities import fuzzy


def matches(row, state):
    if row.get('Archived') and not state.get('include_archived'):
        return False
    if state.get('needs_review') and not row.get('ReviewReasons'):
        return False
    formats = state.get('formats')
    if formats is not None and (row.get('TagName') or SUB_RECIPES) not in formats:
        return False
    tags = state.get('tags') or ()
    if tags and not ((None in tags and not row['TagIds']) or set(tags).intersection(row['TagIds'])):
        return False
    diets = state.get('diets') or ()
    if diets and not set(diets).issubset(row['Diets']):
        return False
    categories = state.get('categories') or ()
    if categories and not set(categories).issubset(row['CategoryIds']):
        return False
    free_from = state.get('free_from') or ()
    # A facility warning isn't "free from" (the cautious reading).
    if free_from and set(free_from).intersection(row['Allergens'], row.get('FacilityAllergens') or ()):
        return False
    cap = state.get('max_food_cost')
    if cap is not None:
        pct = row.get('FoodCostPct')
        if pct is None or pct > cap:
            return False
    return True


class RecipesFacetProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self._state = {}
        self._text = ''

    def set_state(self, state):
        self._state = dict(state)
        self.invalidateFilter()

    def set_facets(self, formats, tags=(), diets=(), categories=(), free_from=(), max_food_cost=None,
                   include_archived=False, needs_review=False):
        self.set_state({'formats': formats, 'tags': list(tags or ()), 'diets': list(diets or ()),
                        'categories': list(categories or ()), 'free_from': list(free_from or ()),
                        'max_food_cost': max_food_cost, 'include_archived': include_archived,
                        'needs_review': needs_review})

    def includes_archived(self):
        return bool(self._state.get('include_archived'))

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
        if not matches(row, self._state):
            return False
        if self._text and not fuzzy.matches(self._text, row['SearchText']):
            return False
        return True

    def filterAcceptsRow(self, source_row, source_parent):
        return self.accepts_row(self.sourceModel().row_dict(source_row))
