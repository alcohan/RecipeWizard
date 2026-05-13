from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox

import db


class TagCheckboxGrid(QGroupBox):
    '''Grid of recipe-tag checkboxes. Unlike AllergenCheckboxGrid, this widget
    does NOT auto-save to the DB — the parent dialog routes the toggle through
    a QUndoStack so the action is undoable.'''

    toggled = Signal(int, str, bool)

    def __init__(self, recipe_id, columns=6, parent=None):
        super().__init__('Tags', parent)
        self.recipe_id = recipe_id
        self._checkboxes = {}
        layout = QGridLayout(self)
        for i, row in enumerate(db.get_recipe_tags(recipe_id)):
            cb = QCheckBox(row['name'])
            cb.setChecked(bool(row['checked']))
            tid = row['id']
            tname = row['name']
            cb.toggled.connect(lambda state, t=tid, n=tname: self.toggled.emit(t, n, state))
            self._checkboxes[tid] = cb
            layout.addWidget(cb, i // columns, i % columns)

    def set_checked(self, tag_id, state):
        '''Programmatic update (e.g. from an undo). Signals are blocked so the
        widget doesn't re-emit `toggled` and create a feedback loop.'''
        cb = self._checkboxes.get(tag_id)
        if cb is None:
            return
        cb.blockSignals(True)
        cb.setChecked(state)
        cb.blockSignals(False)
