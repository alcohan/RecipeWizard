from PySide6.QtCore import (
    QAbstractTableModel, QMimeData, QModelIndex, QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor

import db
from gui.widgets.tag_badge import TagColorRole


# Extra roles read by the editor's delegates.
ShareRole = Qt.UserRole + 10        # float 0..1: this row's share of recipe cost
WasRole = Qt.UserRole + 11          # str: saved quantity when it differs, else None
ChangedRole = Qt.UserRole + 12      # bool: added or re-quantified since the last save
KindRole = Qt.UserRole + 13         # 'ingredient' | 'recipe' | 'template'


# Neutral fallback used when an ingredient has no category tag set, or for
# sub-recipe rows that aren't badged by category.
_FALLBACK_COLOR = '#94a3b8'

# Visual treatment for template-added rows: muted slate text, italic, so
# they read as "managed by the template" rather than user-owned components.
_TEMPLATE_ROW_FG = '#64748b'


_DRAG_MIME = 'application/x-recipewizard-component'


class RecipeComponentsModel(QAbstractTableModel):
    '''Components table for one recipe. Quantity is editable inline; on
    commit, the model emits `qtyEdited(row, new_qty)` so the recipe
    dialog can push the change through its QUndoStack (the model itself
    doesn't write to the DB).

    Rows are also drag-reorderable. The model emits `rowsReordered(
    before, after)` with both orderings as lists of (mode, child_id)
    tuples; the dialog pushes a ReorderComponentsCommand which updates
    the DB and refreshes us.

    Category grouping lived here briefly in Phase A but was removed —
    the Name column's category dot already carries that information,
    and the group-header rows made drag-reorder awkward (crossing a
    header would need to re-tag the ingredient).

    `set_baseline` hands the model the saved quantities so rows edited
    since the last save can show "was 3.5" and a highlight;
    `set_total_cost` gives the denominator for each row's share-of-cost
    bar (the whole recipe, packaging included).'''

    COLUMNS = ('Name', 'Quantity', 'Unit', 'Cost', 'Share', 'Calories', 'Allergens')
    HEADERS = {
        'Name': 'INGREDIENT', 'Quantity': 'QTY', 'Unit': 'UNIT', 'Cost': 'COST',
        'Share': 'SHARE OF COST', 'Calories': 'KCAL', 'Allergens': 'ALLERGENS',
    }

    qtyEdited = Signal(int, float)
    rowsReordered = Signal(list, list)

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        self._rows = []
        self._baseline = None    # {(Type, Id): qty} at the last save
        self._total_cost = 0.0
        self.refresh()

    def set_baseline(self, baseline):
        self.beginResetModel()
        self._baseline = dict(baseline) if baseline is not None else None
        self.endResetModel()

    def set_total_cost(self, total):
        self.beginResetModel()
        self._total_cost = float(total or 0)
        self.endResetModel()

    def quantities(self):
        '''{(Type, Id): qty} — what set_baseline expects.'''
        return {(r['Type'], r['Id']): float(r.get('QuantityRaw') or 0) for r in self._rows}

    def visible_cost(self):
        return sum(float(r.get('CostRaw') or 0) for r in self._rows)

    def _was(self, row):
        '''Saved qty as display text when this row's qty changed; None
        for unchanged rows and for rows added since the save.'''
        if self._baseline is None:
            return None
        saved = self._baseline.get((row['Type'], row['Id']))
        if saved is None or abs(saved - float(row.get('QuantityRaw') or 0)) < 1e-9:
            return None
        return '{:.2f}'.format(saved).rstrip('0').rstrip('.')

    def _changed(self, row):
        if self._baseline is None:
            return False
        key = (row['Type'], row['Id'])
        return key not in self._baseline or self._was(row) is not None

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
        row = self._rows[index.row()]
        is_template = row.get('FromTemplateTagId') is not None
        if is_template:
            # Template-added rows are managed by the template, not the
            # user: no quantity edits, no drag-reorder, no drop target.
            # Base flags (selectable + enabled) stay so the row can be
            # right-clicked for the context menu.
            return base
        f = base | Qt.ItemIsDragEnabled
        if self.COLUMNS[index.column()] == 'Quantity':
            f |= Qt.ItemIsEditable
        return f

    # --- drag-drop -----------------------------------------------------

    def supportedDropActions(self):
        return Qt.MoveAction

    def mimeTypes(self):
        return [_DRAG_MIME]

    def mimeData(self, indexes):
        if not indexes:
            return None
        # SingleSelection means indexes are all cells of one row; just
        # take whichever's first.
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

        # Defer the signal so Qt's drag-drop sequence finishes (incl.
        # the auto-remove call below) before the dialog rewrites
        # SortOrder and the model refreshes from the DB.
        QTimer.singleShot(0, lambda: self.rowsReordered.emit(before, after))
        return True

    def removeRows(self, row, count, parent=QModelIndex()):
        # No-op. Qt's drag-drop machinery calls this after a successful
        # dropMimeData; we don't actually want to touch self._rows here
        # because the deferred rowsReordered handler triggers a full
        # refresh from the (now-rewritten) DB.
        return True

    # --- data ----------------------------------------------------------

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self.COLUMNS[index.column()]
        row = self._rows[index.row()]
        is_template = row.get('FromTemplateTagId') is not None

        if role == KindRole:
            return 'template' if is_template else row.get('Type')
        if role == ChangedRole:
            return self._changed(row)
        if role == Qt.ToolTipRole and is_template:
            return 'Added by the format template — change it in Configure › Formats & templates.'
        if role == Qt.ForegroundRole and is_template:
            return QColor(_TEMPLATE_ROW_FG)
        if role == TagColorRole:
            # Category dot / share bar color. Sub-recipes have no
            # ingredient category; they take the neutral fallback.
            return row.get('TagColor') or _FALLBACK_COLOR

        if col == 'Quantity':
            if role == Qt.EditRole:
                # Hand the editor the precise underlying float, not the
                # rstrip-formatted display string.
                return row.get('QuantityRaw')
            if role == WasRole:
                return self._was(row)
        if col == 'Share' and role == ShareRole:
            if self._total_cost <= 0:
                return 0.0
            return max(0.0, min(1.0, float(row.get('CostRaw') or 0) / self._total_cost))

        if role == Qt.DisplayRole:
            if col == 'Cost':
                return '${:.2f}'.format(float(row.get('CostRaw') or 0))
            if col == 'Calories':
                return '{:,.0f}'.format(float(row.get('Calories') or 0))
            if col == 'Allergens':
                return row.get('Allergens') or '—'
            if col == 'Share':
                return ''
            value = row.get(col)
            return '' if value is None else str(value)
        if role == Qt.TextAlignmentRole and col in ('Quantity', 'Cost', 'Calories'):
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
        # Don't mutate _rows directly — the undo command runs the DB
        # update and refresh() reloads the model with the authoritative
        # new state.
        self.qtyEdited.emit(index.row(), new_qty)
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        col = self.COLUMNS[section]
        if role == Qt.DisplayRole:
            return self.HEADERS[col]
        if role == Qt.TextAlignmentRole and col in ('Quantity', 'Cost', 'Calories'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def row_dict(self, row):
        return self._rows[row]
