from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QGridLayout, QGroupBox

import db


class AllergenCheckboxGrid(QGroupBox):
    '''Grid of allergen checkboxes for an ingredient. Toggles auto-save and
    emit `changed(allergen_id, state)` so callers can refresh derived views.'''

    changed = Signal(int, bool)

    def __init__(self, ingredient_id, columns=6, parent=None):
        super().__init__('Allergens', parent)
        self.ingredient_id = ingredient_id
        layout = QGridLayout(self)
        for i, row in enumerate(db.get_ingredient_allergens(ingredient_id)):
            cb = QCheckBox(row['name'])
            cb.setChecked(bool(row['checked']))
            aid = row['id']
            cb.toggled.connect(lambda state, a=aid: self._on_toggle(a, state))
            layout.addWidget(cb, i // columns, i % columns)

    def _on_toggle(self, allergen_id, state):
        db.modify_ingredient_allergen(self.ingredient_id, allergen_id, state)
        self.changed.emit(allergen_id, state)
