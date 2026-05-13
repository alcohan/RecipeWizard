from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt

import db


class IngredientsModel(QAbstractTableModel):
    COLUMNS = ('Name', 'Portion', 'Unit', 'Calories')
    NUMERIC_COLUMNS = ('Calories',)

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
        col = self.COLUMNS[index.column()]
        value = self._rows[index.row()].get(col)
        if role == Qt.DisplayRole:
            if col in self.NUMERIC_COLUMNS:
                return _format_num(value)
            return '' if value is None else str(value)
        if role == Qt.UserRole:
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


def _format_num(value):
    '''Display 35 as "35" (not "35.0"), 12.3 as "12.3". Blank for None/empty.'''
    if value is None or value == '':
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    if n == int(n):
        return str(int(n))
    return f'{n:.1f}'
