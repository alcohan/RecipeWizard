from PySide6.QtCore import (
    QAbstractTableModel, QMimeData, QModelIndex, QTimer, Qt, Signal,
)

import db


_DRAG_MIME = 'application/x-recipewizard-component'


class RecipeComponentsModel(QAbstractTableModel):
    '''Components table for one recipe. Quantity is editable inline; on
    commit, the model emits `qtyEdited(row, new_qty)` so the recipe dialog
    can push the change through its QUndoStack (the model itself doesn't
    write to the DB).

    Rows are also drag-reorderable. The model emits `rowsReordered(before,
    after)` with both orderings as lists of (mode, child_id) tuples; the
    dialog pushes a ReorderComponentsCommand which updates the DB and
    refreshes us.'''

    COLUMNS = ('Name', 'Quantity', 'Unit', 'Type', 'Cost')

    qtyEdited = Signal(int, float)
    rowsReordered = Signal(list, list)

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
        if not index.isValid():
            # Drops between rows are allowed at the root level.
            return base | Qt.ItemIsDropEnabled
        f = base | Qt.ItemIsDragEnabled
        if self.COLUMNS[index.column()] == 'Quantity':
            f |= Qt.ItemIsEditable
        # Deliberately NOT including ItemIsDropEnabled on cells, so the user
        # can only drop between rows, never "on" another row.
        return f

    # --- drag-drop ----------------------------------------------------------

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [_DRAG_MIME]

    def mimeData(self, indexes):
        if not indexes:
            return None
        # SingleSelection means indexes are all cells of one row; just take
        # whichever's first.
        mime = QMimeData()
        mime.setData(_DRAG_MIME, str(indexes[0].row()).encode())
        return mime

    def dropMimeData(self, data, action, row, column, parent):
        if action != Qt.MoveAction or not data.hasFormat(_DRAG_MIME):
            return False
        try:
            src_row = int(bytes(data.data(_DRAG_MIME)).decode())
        except (ValueError, UnicodeDecodeError):
            return False
        if row == -1:
            dest_row = parent.row() if parent.isValid() else self.rowCount()
        else:
            dest_row = row
        if not (0 <= src_row < len(self._rows)):
            return False
        # No-op cases: dropping a row onto itself or just below itself.
        if dest_row == src_row or dest_row == src_row + 1:
            return False

        before = [(r['Type'], r['Id']) for r in self._rows]
        rows = list(self._rows)
        moving = rows.pop(src_row)
        insert_at = dest_row - 1 if dest_row > src_row else dest_row
        rows.insert(insert_at, moving)
        after = [(r['Type'], r['Id']) for r in rows]

        # Defer the signal so Qt's drag-drop sequence finishes (incl. the
        # auto-remove call below) before the dialog rewrites SortOrder and
        # the model refreshes from the DB.
        QTimer.singleShot(0, lambda: self.rowsReordered.emit(before, after))
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        # No-op. Qt's drag-drop machinery calls this after a successful
        # dropMimeData; we don't actually want to touch self._rows here
        # because the deferred rowsReordered handler triggers a full
        # refresh from the (now-rewritten) DB.
        return True

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
