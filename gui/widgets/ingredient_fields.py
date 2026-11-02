'''Field groups shared by the New and Edit ingredient dialogs, styled
per the Framework canvas. None of them write to the DB: the dialogs
read their values on Save.

- CategoryPills: one pill per ingredient category plus None.
- AllergenChecks: the allergen checkboxes, three columns.
- NutritionGrid: the nine nutrition inputs, three columns.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QWidget,
)

import config
import db
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.ingredient_table import tint


_KALE = '#082c00'
_ROMAINE = '#347200'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'


def num_text(value):
    '''Display a stored number without float noise ("2.2", not "2.2000").'''
    if value is None or value == '':
        return ''
    try:
        n = float(value)
    except (TypeError, ValueError):
        return str(value)
    return '{:.4f}'.format(n).rstrip('0').rstrip('.')


class CategoryPills(QWidget):
    changed = Signal(object)   # tag id or None

    def __init__(self, selected_id=None, parent=None):
        super().__init__(parent)
        self._selected = selected_id
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons = {}
        flow = FlowLayout(self, spacing=6)
        flow.setContentsMargins(0, 0, 0, 0)
        for tag in db.get_tags('ingredient') + [{'id': None, 'name': 'None', 'color': None}]:
            btn = QPushButton(tag['name'] if tag['id'] is None else f'●  {tag["name"]}')
            btn.setCheckable(True)
            btn.setChecked(tag['id'] == selected_id)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.PointingHandCursor)
            color = tag.get('color') or '#a7ad9c'
            btn.setStyleSheet(f'''
                QPushButton {{ padding: 4px 11px; border-radius: 12px; border: 1px solid {_BORDER};
                    background: #ffffff; color: {_KALE}; font-size: 12px; }}
                QPushButton:checked {{ border: 2px solid {_ROMAINE}; padding: 3px 10px;
                    background: {tint(color).name()}; font-weight: 600; }}
            ''')
            btn.clicked.connect(lambda _c=False, t=tag['id']: self._pick(t))
            self._group.addButton(btn)
            self._buttons[tag['id']] = btn
            flow.addWidget(btn)

    def selected(self):
        return self._selected

    def set_selected(self, tag_id):
        self._selected = tag_id
        btn = self._buttons.get(tag_id)
        if btn is not None:
            btn.setChecked(True)

    def _pick(self, tag_id):
        if tag_id != self._selected:
            self._selected = tag_id
            self.changed.emit(tag_id)


class AllergenChecks(QWidget):
    changed = Signal()

    def __init__(self, ingredient_id=None, parent=None):
        super().__init__(parent)
        self._boxes = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        # Id 0 matches no ingredient, so a new one gets every box unchecked.
        for i, a in enumerate(db.get_ingredient_allergens(ingredient_id or 0)):
            cb = QCheckBox(a['name'])
            cb.setChecked(bool(a['checked']))
            cb.toggled.connect(lambda _v, c=cb: self._on_toggle(c))
            self._style(cb)
            self._boxes[a['id']] = cb
            grid.addWidget(cb, i // 3, i % 3)

    def checked_ids(self):
        return sorted(a for a, cb in self._boxes.items() if cb.isChecked())

    def set_checked(self, ids):
        for a, cb in self._boxes.items():
            cb.setChecked(a in set(ids))

    def _on_toggle(self, cb):
        self._style(cb)
        self.changed.emit()

    def _style(self, cb):
        cb.setStyleSheet(f'QCheckBox {{ color: {_KALE}; font-weight: {600 if cb.isChecked() else 400}; }}')


class NutritionGrid(QWidget):
    changed = Signal()

    def __init__(self, values=None, parent=None):
        super().__init__(parent)
        self._edits = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        for i, (key, label) in enumerate(config.nutrition_fields.items()):
            edit = QLineEdit(num_text((values or {}).get(key)))
            edit.setValidator(QDoubleValidator(0.0, 1_000_000.0, 4))
            edit.setAlignment(Qt.AlignRight)
            edit.setFixedWidth(80)
            edit.textChanged.connect(lambda _t: self.changed.emit())
            cell = QHBoxLayout()
            name = QLabel(label)
            name.setStyleSheet(f'color: {_KALE};')
            cell.addWidget(name)
            cell.addStretch()
            cell.addWidget(edit)
            grid.addLayout(cell, i // 3, i % 3)
            self._edits[key] = edit

    def values(self):
        return {key: edit.text() for key, edit in self._edits.items()}

    def set_values(self, values):
        for key, edit in self._edits.items():
            if key in values:
                edit.setText(num_text(values[key]))

    def is_empty(self):
        return not any(e.text().strip() not in ('', '0') for e in self._edits.values())
