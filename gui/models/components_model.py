from PySide6.QtCore import (
    QAbstractTableModel, QMimeData, QModelIndex, QTimer, Qt, Signal,
)
from PySide6.QtGui import QColor, QFont

import db
from gui.widgets.tag_badge import TagColorRole


# Neutral fallback used when an ingredient has no category tag set, or for
# sub-recipe rows that aren't badged by category.
_FALLBACK_COLOR = '#94a3b8'

# Visual treatment for template-added rows: muted slate text, italic, so
# they read as "managed by the template" rather than user-owned components.
_TEMPLATE_ROW_FG = '#64748b'


_DRAG_MIME = 'application/x-recipewizard-component'


# Fixed category order used to group the components table. The order
# matches the design canvas: greens → grains → protein → cheese → …,
# packaging last. Unlisted categories fall through to '(Uncategorized)',
# sub-recipes (Type == 'recipe') bucket into 'Sub-recipes'. Both appear
# AFTER the canonical categories.
_CATEGORY_ORDER = (
    'Greens', 'Grains', 'Protein', 'Cheese', 'Toppings',
    'Dressing', 'Crunchies', 'Premiums', 'Finish', 'Packaging',
)
_SUB_RECIPE_BUCKET = 'Sub-recipes'
_UNCATEGORIZED_BUCKET = '(Uncategorized)'
_SUB_RECIPE_COLOR = '#7c3aed'    # same violet as the generic recipe badge
_UNCATEGORIZED_COLOR = _FALLBACK_COLOR


def _bucket_for(component):
    '''Decide which group a component belongs to, with the color we'll
    paint on the group header. Sub-recipes get a dedicated bucket; a
    plain ingredient with no category tag falls through to Uncategorized.'''
    if component.get('Type') == 'recipe':
        return _SUB_RECIPE_BUCKET, _SUB_RECIPE_COLOR
    tag = component.get('TagName') or ''
    if tag in _CATEGORY_ORDER:
        return tag, component.get('TagColor') or _FALLBACK_COLOR
    return _UNCATEGORIZED_BUCKET, _UNCATEGORIZED_COLOR


def _bucket_sort_key(bucket):
    '''Sort rank: canonical categories first in design order, then
    sub-recipes, then uncategorized. Equal buckets break the tie by
    name within the group's existing SortOrder (left to the caller).'''
    try:
        return _CATEGORY_ORDER.index(bucket)
    except ValueError:
        if bucket == _SUB_RECIPE_BUCKET:
            return len(_CATEGORY_ORDER)
        return len(_CATEGORY_ORDER) + 1


class RecipeComponentsModel(QAbstractTableModel):
    '''Components table for one recipe. Rows are grouped by ingredient
    category with a synthetic header row at the start of each group; the
    header carries the category name and its cost subtotal.

    Quantity is editable inline on component rows (not headers); on
    commit, the model emits `qtyEdited(row, new_qty)` so the recipe
    dialog can push the change through its QUndoStack (the model itself
    doesn't write to the DB).

    Drag-reorder is disabled while grouping is active — crossing a
    category header would need to re-tag the ingredient, which the user
    should do deliberately in the ingredient editor rather than by
    accident during a drag.'''

    COLUMNS = ('Name', 'Quantity', 'Unit', 'Type', 'Cost')

    qtyEdited = Signal(int, float)
    rowsReordered = Signal(list, list)  # retained for future un-grouped mode

    # Role used by the delegate to recognize a group-header row and paint
    # it as a full-width band. Picked above UserRole to avoid colliding
    # with any model-defined role.
    HeaderRowRole = Qt.UserRole + 100
    HeaderColorRole = Qt.UserRole + 101

    def __init__(self, recipe_id, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe_id
        # _display is a list of either:
        #   {'kind': 'header', 'name': 'Greens', 'color': '#...', 'subtotal': 0.38}
        #   {'kind': 'component', 'row': <dict from db.recipe_components>, 'source': <int>}
        self._display = []
        # _source is the original list, index-aligned with 'source' values
        # on component display entries.
        self._source = []
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        self._source = db.recipe_components(self.recipe_id)
        self._display = self._build_display(self._source)
        self.endResetModel()

    @staticmethod
    def _build_display(source_rows):
        '''Attach a bucket to every component, sort stably by (bucket
        order, original index), and insert a synthetic header before
        each new bucket. Returns the flat _display list.'''
        if not source_rows:
            return []
        # Decorate with bucket + preserve original order within group.
        decorated = []
        for i, comp in enumerate(source_rows):
            bucket, color = _bucket_for(comp)
            decorated.append((_bucket_sort_key(bucket), bucket, color, i, comp))
        decorated.sort(key=lambda t: (t[0], t[3]))

        out = []
        current_bucket = None
        bucket_total = 0.0
        header_slot = None  # index of the current bucket's header in `out`
        for rank, bucket, color, source_i, comp in decorated:
            if bucket != current_bucket:
                # Close out previous bucket's running subtotal into its header.
                if header_slot is not None:
                    out[header_slot]['subtotal'] = round(bucket_total, 2)
                header_slot = len(out)
                out.append({'kind': 'header', 'name': bucket, 'color': color,
                            'subtotal': 0.0})
                current_bucket = bucket
                bucket_total = 0.0
            bucket_total += float(comp.get('CostRaw') or 0)
            out.append({'kind': 'component', 'row': comp, 'source': source_i})
        if header_slot is not None:
            out[header_slot]['subtotal'] = round(bucket_total, 2)
        return out

    # --- row-kind queries ------------------------------------------------

    def is_header_row(self, row):
        '''Rows that are category group-headers (not editable, no context
        actions). The dialog's handlers (context menu, double-click)
        consult this before dispatching.'''
        return 0 <= row < len(self._display) and self._display[row]['kind'] == 'header'

    def source_row_index(self, row):
        '''Original source-model index for a display row, or -1 for headers.'''
        if 0 <= row < len(self._display) and self._display[row]['kind'] == 'component':
            return self._display[row]['source']
        return -1

    def row_dict(self, row):
        '''Return the underlying component dict for a display row, or
        None for header rows.'''
        if 0 <= row < len(self._display) and self._display[row]['kind'] == 'component':
            return self._display[row]['row']
        return None

    # --- Qt model API ----------------------------------------------------

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._display)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def flags(self, index):
        base = super().flags(index)
        if not index.isValid():
            return base
        entry = self._display[index.row()]
        if entry['kind'] == 'header':
            # Readable but inert: no selection, no edit, no drag, no drop.
            return Qt.ItemIsEnabled
        row = entry['row']
        is_template = row.get('FromTemplateTagId') is not None
        if is_template:
            return base
        f = base
        if self.COLUMNS[index.column()] == 'Quantity':
            f |= Qt.ItemIsEditable
        return f

    # Drag-drop is intentionally disabled while grouping is active (see
    # class docstring). The signatures stay in place so a future
    # un-grouped mode can switch them back on without touching callers.
    def supportedDropActions(self):
        return Qt.IgnoreAction

    def mimeTypes(self):
        return [_DRAG_MIME]

    def mimeData(self, indexes):
        return None

    def dropMimeData(self, data, action, row, column, parent):
        return False

    def removeRows(self, row, count, parent=QModelIndex()):
        return True

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        entry = self._display[index.row()]
        if entry['kind'] == 'header':
            return self._header_data(entry, index.column(), role)
        return self._component_data(entry['row'], index.column(), role)

    def _header_data(self, entry, column, role):
        if role == self.HeaderRowRole:
            return True
        if role == self.HeaderColorRole:
            return entry['color']
        if role == Qt.FontRole:
            f = QFont()
            f.setBold(True)
            return f
        if role == Qt.BackgroundRole:
            # Pale tint of the category color so the row reads as a band.
            return _tint(entry['color'])
        if role == Qt.DisplayRole:
            # Name in column 0, subtotal in the Cost column, else blank.
            if column == 0:
                return entry['name']
            if self.COLUMNS[column] == 'Cost':
                return '$ {:.2f}'.format(float(entry['subtotal']))
            return ''
        if role == Qt.TextAlignmentRole and self.COLUMNS[column] == 'Cost':
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def _component_data(self, row, column, role):
        col = self.COLUMNS[column]
        is_template = row.get('FromTemplateTagId') is not None

        if role == self.HeaderRowRole:
            return False
        if is_template:
            if role == Qt.ForegroundRole:
                return QColor(_TEMPLATE_ROW_FG)
            if role == Qt.FontRole:
                f = QFont()
                f.setItalic(True)
                return f
            if role == Qt.ToolTipRole:
                return 'Added by template — edit in the Template Editor.'

        if role == Qt.EditRole and col == 'Quantity':
            return row.get('QuantityRaw')
        if col == 'Type':
            if role == Qt.DisplayRole:
                if row.get('Type') == 'ingredient':
                    return row.get('TagName') or 'ingredient'
                return 'recipe'
            if role == TagColorRole:
                if row.get('Type') == 'ingredient':
                    return row.get('TagColor') or _FALLBACK_COLOR
                return _SUB_RECIPE_COLOR
            return None
        value = row.get(col)
        if role == Qt.DisplayRole:
            if col == 'Name' and is_template:
                return f'{value} · template'
            # Indent component names so they visually sit under the group
            # header, matching the design.
            if col == 'Name':
                return f'    {value}' if value is not None else ''
            return '' if value is None else str(value)
        if role == Qt.TextAlignmentRole and col in ('Quantity', 'Cost'):
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        if self.COLUMNS[index.column()] != 'Quantity':
            return False
        entry = self._display[index.row()]
        if entry['kind'] != 'component':
            return False
        try:
            new_qty = float(value)
        except (TypeError, ValueError):
            return False
        if new_qty <= 0:
            return False
        # Emit the DISPLAY row so handlers can use row_dict(row) directly;
        # the undo command works off (Type, Id) from that dict, not an
        # index, so display vs source doesn't matter downstream.
        self.qtyEdited.emit(index.row(), new_qty)
        return True

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None


def _tint(hex_color):
    '''Return a QColor that's a pale version of hex_color — used as the
    group-header background. Keeps the row readable while making the
    category instantly recognizable.'''
    c = QColor(hex_color)
    if not c.isValid():
        c = QColor('#E8E6DF')
    # Blend toward paper white (#fffaf2 in the design) at ~85% — subtle
    # enough that body text passes contrast, saturated enough to read as
    # a band.
    bg = QColor('#fffaf2')
    r = int(c.red() * 0.18 + bg.red() * 0.82)
    g = int(c.green() * 0.18 + bg.green() * 0.82)
    b = int(c.blue() * 0.18 + bg.blue() * 0.82)
    return QColor(r, g, b)
