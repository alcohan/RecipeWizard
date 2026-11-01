'''Multi-facet filter proxy for the Recipes place.

Extends the plain text-filter idea with:
  - formats     — set of allowed format names (None = all)
  - free_from   — set of allergen names to EXCLUDE

The allergen index is kept in self._allergens_by_id and rebuilt on
every source-model reset so edits to recipes anywhere else in the app
show up here on next refresh.
'''
from PySide6.QtCore import QSortFilterProxyModel, Qt

import db


class RecipesFacetProxy(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ''
        self._formats = None            # None = no format filter
        self._free_from = set()         # excluded allergens
        self._allergens_by_id = {}      # populated by _refresh_allergens
        self.setSortRole(Qt.UserRole)

    def setSourceModel(self, model):
        super().setSourceModel(model)
        self._refresh_allergens()
        model.modelReset.connect(self._refresh_allergens)

    # --- facet setters -------------------------------------------------

    def setFilterText(self, text):
        self._needle = (text or '').strip().lower()
        self.invalidateFilter()

    def setFormats(self, formats):
        '''Pass None (or empty set) to clear the format filter and show
        every recipe regardless of format tag. Otherwise show only
        recipes whose TagName is in the given set.'''
        self._formats = set(formats) if formats else None
        self.invalidateFilter()

    def setFreeFrom(self, allergens):
        self._free_from = set(allergens or ())
        self.invalidateFilter()

    # --- allergen index ------------------------------------------------

    def _refresh_allergens(self):
        try:
            raw = db.get_all_recipe_allergens()
        except Exception:
            raw = {}
        self._allergens_by_id = {rid: set(names) for rid, names in raw.items()}
        self.invalidateFilter()

    # --- Qt filter -----------------------------------------------------

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        if model is None:
            return True
        try:
            row = model.row_dict(source_row)
        except (AttributeError, IndexError):
            return True

        # Text — match across the visible display columns.
        if self._needle:
            matched = False
            for key in ('Name', 'Unit', 'Cost', 'TagName'):
                v = row.get(key)
                if v is not None and self._needle in str(v).lower():
                    matched = True
                    break
            if not matched:
                return False

        # Format — recipes without a format tag never match a format filter
        # (users who want "untagged" can clear the filter).
        if self._formats is not None:
            if (row.get('TagName') or '') not in self._formats:
                return False

        # Free-from allergens — reject if the recipe contains any of the
        # excluded allergens. Recipes with no allergens are always clean.
        if self._free_from:
            rid = row.get('Id')
            allergens = self._allergens_by_id.get(rid, set())
            if allergens & self._free_from:
                return False

        return True
