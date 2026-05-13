from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

import db


class RecipesModel(QAbstractTableModel):
    # db.recipe_info() pre-formats Cost as "$ X.XX"; we keep that for display
    # but expose a numeric value via UserRole so column sort works correctly.
    COLUMNS = ('Name', 'Unit', 'Cost', 'Calories', 'Components')
    NUMERIC_COLUMNS = ('Cost', 'Calories', 'Components')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._rows = db.recipe_info()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self.COLUMNS[index.column()]
        value = self._rows[index.row()].get(col)
        if role == Qt.DisplayRole:
            return '' if value is None else str(value)
        if role == Qt.UserRole:
            if col == 'Cost':
                try:
                    return float(str(value).replace('$', '').strip())
                except (ValueError, AttributeError, TypeError):
                    return 0.0
            if col in self.NUMERIC_COLUMNS:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
            return '' if value is None else str(value).lower()
        if role == Qt.TextAlignmentRole and col in self.NUMERIC_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def id_at_row(self, row):
        return self._rows[row]['Id']

    def row_dict(self, row):
        return self._rows[row]
