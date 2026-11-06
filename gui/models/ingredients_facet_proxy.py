'''Filter + sort proxy for the Ingredients place.

Facets, combined with AND across groups:
- categories: set of category tag ids to show (None = uncategorized);
  None means "no category filter".
- attention: set of ATTENTION_KEYS; an ingredient passes if it has ANY
  of the checked flags. Empty set = no attention filter.
- suppliers: set of supplier ids to show (None = no supplier); None
  means "no supplier filter".
- allergens: set of allergen names; an ingredient passes if it
  contains ANY of them (NO_ALLERGENS matches ingredients with none).
  Empty set = no allergen filter.
- text: substring of name, category, supplier, allergens, unit or tool.

With no header sort the proxy keeps the source order, which is
category order then name.
'''
from PySide6.QtCore import QSortFilterProxyModel, Qt

from gui.models.ingredients_model import NO_ALLERGENS, RowRole
from utilities import fuzzy


class IngredientsFacetProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortRole(Qt.UserRole)
        self._categories = None
        self._attention = set()
        self._suppliers = None
        self._allergens = set()
        self._text = ''

    def set_facets(self, categories, attention, suppliers, allergens=()):
        self._categories = categories
        self._attention = set(attention or ())
        self._suppliers = suppliers
        self._allergens = set(allergens or ())
        self.invalidateFilter()

    def setFilterText(self, text):
        self._text = (text or '').strip().lower()
        self.invalidateFilter()

    def accepts_row(self, row):
        '''Same test as filterAcceptsRow, on a row dict (the gallery
        uses it to filter cards without going through indexes).'''
        if self._categories is not None and row.get('TagId') not in self._categories:
            return False
        if self._suppliers is not None and row.get('SupplierId') not in self._suppliers:
            return False
        if self._attention and not any(row['Flags'][k] for k in self._attention):
            return False
        if self._allergens:
            has = row['AllergenList']
            if not ((NO_ALLERGENS in self._allergens and not has)
                    or any(a in self._allergens for a in has)):
                return False
        if self._text and not fuzzy.matches(self._text, row['SearchText']):
            return False
        return True

    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        return self.accepts_row(index.data(RowRole))
