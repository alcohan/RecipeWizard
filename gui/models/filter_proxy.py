from PySide6.QtCore import QSortFilterProxyModel, Qt


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
        for col in range(model.columnCount()):
            value = model.data(model.index(source_row, col, source_parent), Qt.DisplayRole)
            if value is not None and self._needle in str(value).lower():
                return True
        return False
