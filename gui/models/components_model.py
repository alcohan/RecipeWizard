from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

import db


class RecipeComponentsModel(QAbstractTableModel):
    '''Components table for one recipe. Quantity is editable inline; on
    commit, the model emits `qtyEdited(row, new_qty)` so the recipe dialog
    can push the change through its QUndoStack (the model itself doesn't
    write to the DB).'''

    COLUMNS = ('Name', 'Quantity', 'Unit', 'Type', 'Cost')

    qtyEdited = Signal(int, float)

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

    def flags(self, index):
        base = super().flags(index)
        if index.isValid() and self.COLUMNS[index.column()] == 'Quantity':
            return base | Qt.ItemIsEditable
        return base

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self.COLUMNS[index.column()]
        row = self._rows[index.row()]
        if role == Qt.EditRole and col == 'Quantity':
            # Hand the editor the precise underlying float, not the
            # rstrip-formatted display string.
            return row.get('QuantityRaw')
        value = row.get(col)
        if role == Qt.DisplayRole:
            return '' if value is None else str(value)
        if role == Qt.TextAlignmentRole and col in ('Quantity', 'Cost'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        if self.COLUMNS[index.column()] != 'Quantity':
            return False
        try:
            new_qty = float(value)
        except (TypeError, ValueError):
            return False
        if new_qty <= 0:
            return False
        # Don't mutate _rows directly — the undo command runs the DB update
        # and refresh() reloads the model with the authoritative new state.
        self.qtyEdited.emit(index.row(), new_qty)
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def row_dict(self, row):
        return self._rows[row]
