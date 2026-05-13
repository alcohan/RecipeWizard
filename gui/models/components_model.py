from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

import db


class RecipeComponentsModel(QAbstractTableModel):
    COLUMNS = ('Name', 'Quantity', 'Unit', 'Type', 'Cost')

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._rows = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._rows = db.recipe_components(self.recipe_id)
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
        if role == Qt.TextAlignmentRole and col in ('Quantity', 'Cost'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def row_dict(self, row):
        return self._rows[row]
