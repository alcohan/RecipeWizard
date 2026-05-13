from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

import db


class IngredientsModel(QAbstractTableModel):
    COLUMNS = ('Name', 'Unit')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._rows = db.get_ingredients()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self._rows[index.row()].get(self.COLUMNS[index.column()])
        if role == Qt.DisplayRole:
            return '' if value is None else str(value)
        if role == Qt.UserRole:
            return '' if value is None else str(value).lower()
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def id_at_row(self, row):
        return self._rows[row]['Id']
