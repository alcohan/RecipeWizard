'''Single-select tag picker — radio buttons with colored swatches.

Used by both the ingredient edit dialog (autosave mode, like the allergen
grid) and the recipe edit dialog (no autosave; the toggle is routed through
QUndoStack so it can be undone with Ctrl+Z).

The widget loads tags via db.get_tags(kind=kind) and the current selection
via db.get_ingredient_tag / db.get_recipe_tag. A "(none)" option is always
included so the user can unset.'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QGridLayout, QGroupBox, QLabel, QRadioButton,
)

import db


_DEFAULT_COLOR = '#64748b'


def _swatch_pixmap(hex_color, size=14):
    '''Small rounded color chip painted next to a radio button.'''
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    color = QColor(hex_color or _DEFAULT_COLOR)
    if not color.isValid():
        color = QColor(_DEFAULT_COLOR)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(0, 0, size, size, 3, 3)
    painter.end()
    return pixmap


class TagSelector(QGroupBox):
    '''Single-select tag radio grid.

    Parameters
    ----------
    kind        : 'recipe' or 'ingredient' — which tags to show.
    item_id     : recipe or ingredient id to read the current selection from.
    autosave    : when True, persist immediately on change. When False, only
                  emit `selectionChanged(new_tag_id, prev_tag_id)` and let
                  the caller drive the DB write (e.g. via QUndoCommand).
    columns     : layout width (chip + radio counts as one column).
    '''

    selectionChanged = Signal(object, object)  # new_tag_id|None, prev_tag_id|None

    def __init__(self, kind, item_id, *, title='Tag', autosave=False,
                 columns=4, parent=None):
        super().__init__(title, parent)
        self.kind = kind
        self.item_id = item_id
        self._autosave = autosave
        self._current_id = None
        self._buttons = {}      # tag_id -> QRadioButton
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)

        self._tags = db.get_tags(kind=kind)
        current = (
            db.get_recipe_tag(item_id) if kind == 'recipe'
            else db.get_ingredient_tag(item_id)
        )
        self._current_id = current['id'] if current else None

        layout = QGridLayout(self)

        none_radio = QRadioButton('(none)')
        none_radio.setChecked(self._current_id is None)
        none_radio.toggled.connect(
            lambda checked: checked and self._on_pick(None),
        )
        # Reserve column 0 for the swatch — (none) has no swatch, so the radio
        # spans both columns to stay left-aligned with the others.
        layout.addWidget(none_radio, 0, 0, 1, 2)
        self._group.addButton(none_radio)
        self._none_radio = none_radio

        per_row_columns = columns
        # Each tag occupies 2 grid columns (swatch + radio), so the wrap point
        # in terms of grid columns is 2 * per_row_columns.
        for i, tag in enumerate(self._tags):
            row = 1 + i // per_row_columns
            col = (i % per_row_columns) * 2

            swatch = QLabel()
            swatch.setPixmap(_swatch_pixmap(tag.get('color')))
            swatch.setFixedWidth(18)

            radio = QRadioButton(tag['name'])
            tid = tag['id']
            radio.setChecked(self._current_id == tid)
            radio.toggled.connect(
                lambda checked, t=tid: checked and self._on_pick(t),
            )
            self._group.addButton(radio)
            self._buttons[tid] = radio

            layout.addWidget(swatch, row, col, alignment=Qt.AlignVCenter)
            layout.addWidget(radio, row, col + 1)

        layout.setColumnStretch(2 * per_row_columns - 1, 1)

    def _on_pick(self, tag_id):
        prev = self._current_id
        if tag_id == prev:
            return
        self._current_id = tag_id
        if self._autosave:
            if self.kind == 'recipe':
                db.set_recipe_tag(self.item_id, tag_id)
            else:
                db.set_ingredient_tag(self.item_id, tag_id)
        self.selectionChanged.emit(tag_id, prev)

    def set_selected(self, tag_id):
        '''Programmatic selection update (e.g. from an undo). Does NOT
        re-emit selectionChanged — caller already knows what changed.'''
        self._current_id = tag_id
        # Block the QButtonGroup so toggling doesn't fire _on_pick.
        for btn in self._group.buttons():
            btn.blockSignals(True)
        if tag_id is None:
            self._none_radio.setChecked(True)
        else:
            btn = self._buttons.get(tag_id)
            if btn is not None:
                btn.setChecked(True)
            else:
                self._none_radio.setChecked(True)
        for btn in self._group.buttons():
            btn.blockSignals(False)

    def current_id(self):
        return self._current_id
