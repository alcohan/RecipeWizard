from PySide6.QtCore import QSortFilterProxyModel, Qt
from utilities import fuzzy


class MultiColumnFilterProxy(QSortFilterProxyModel):
    '''Filter rows by case-insensitive substring match across all source columns.
    Sort comparisons use Qt.UserRole so numeric columns sort numerically.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self._needle = ''
        self.setSortRole(Qt.UserRole)

    def setFilterText(self, text):
        self._needle = (text or '').strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        if not self._needle:
            return True
        model = self.sourceModel()
        text = ' '.join(str(model.data(model.index(source_row, col, source_parent), Qt.DisplayRole) or '')
                        for col in range(model.columnCount()))
        return fuzzy.matches(self._needle, text)
