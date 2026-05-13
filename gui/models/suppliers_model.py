from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

import db


class SuppliersModel(QAbstractTableModel):
    # Display header -> DB field name
    COLUMNS = (('Name', 'name'), ('City', 'city'), ('State', 'state'))

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._rows = db.get_suppliers()
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        _, field = self.COLUMNS[index.column()]
        value = self._rows[index.row()].get(field)
        if role == Qt.DisplayRole:
            return '' if value is None else str(value)
        if role == Qt.UserRole:
            return '' if value is None else str(value).lower()
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section][0]
        return None

    def id_at_row(self, row):
        return self._rows[row]['id']

    def row_dict(self, row):
        return self._rows[row]
