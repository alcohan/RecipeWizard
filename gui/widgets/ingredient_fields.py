'''Field groups shared by the New and Edit ingredient dialogs, styled
per the Framework canvas. None of them write to the DB: the dialogs
read their values on Save.

- CategoryPills: one pill per ingredient category plus None.
- AllergenChecks: allergen chips (off / contains / facility), three columns.
- NutritionGrid: the nine nutrition inputs, three columns.
- StatementBox: the ingredient statement pasted from the package label.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QMenu, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

import config
import db
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.ingredient_table import tint
from utilities import diets


_KALE = '#082c00'
_ROMAINE = '#347200'
_BORDER = '#ebe1cd'
_FIELD_BORDER = '#7d8771'
_MUTED = '#55624c'


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


OFF, CONTAINS, FACILITY = 0, 1, 2
_ALERT, _ALERT_BG = '#b80700', '#ffe8e3'
_FAC, _FAC_BG = '#8a4a00', '#fff0dc'


class AllergenChecks(QWidget):
    '''One chip per allergen, each off, Contains or Facility ("made in a
    facility that also handles"). A click cycles off → Contains →
    Facility → off; right-click picks one. "Mark all as facility" turns
    every flagged allergen into a facility warning (spice blends with a
    long may-contain list), and back.'''
    changed = Signal()

    def __init__(self, ingredient_id=None, parent=None):
        super().__init__(parent)
        self._chips = {}     # allergen id -> QPushButton
        self._state = {}     # allergen id -> OFF / CONTAINS / FACILITY
        self._diets = db.get_diets()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        # The chip's look carries the state, so its text stays just the
        # name and three chips fit the editor's narrow side panel.
        legend = QLabel(f'<span style="color:{_ALERT}; font-weight:600">Red</span> = contains,'
                        f' <span style="color:{_FAC}">dashed amber</span> = facility')
        legend.setTextFormat(Qt.RichText)
        legend.setWordWrap(True)
        legend.setMinimumWidth(1)
        legend.setStyleSheet(f'color: {_MUTED}; font-size: 11px;')
        self.bulk_btn = QPushButton('Mark all as facility')
        self.bulk_btn.setFlat(True)
        self.bulk_btn.setCursor(Qt.PointingHandCursor)
        self.bulk_btn.setAutoDefault(False)
        self.bulk_btn.setStyleSheet(f'QPushButton {{ color: {_ROMAINE}; border: 0; padding: 0 2px; }}'
                                    ' QPushButton:hover { text-decoration: underline; }'
                                    ' QPushButton:disabled { color: #a7ad9c; }')
        self.bulk_btn.clicked.connect(self._on_bulk)
        # The legend gets the full width (a wrapping label beside the
        # button squeezes to a word per line); the button sits under it.
        outer.addWidget(legend)
        top.addStretch()
        top.addWidget(self.bulk_btn)
        outer.addLayout(top)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        outer.addLayout(grid)
        # Which diets these allergens rule out, per Configure › Diets.
        self.diet_hint = QLabel('')
        self.diet_hint.setWordWrap(True)
        self.diet_hint.setMinimumWidth(1)
        self.diet_hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        outer.addWidget(self.diet_hint)
        # Id 0 matches no ingredient, so a new one starts with every chip off.
        for i, a in enumerate(db.get_ingredient_allergens(ingredient_id or 0)):
            chip = QPushButton(a['name'])
            chip.setProperty('allergen', a['name'])
            # Never let a chip widen the panel; columns share the width.
            chip.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
            chip.setMinimumWidth(0)
            chip.setAutoDefault(False)
            chip.setCursor(Qt.PointingHandCursor)
            chip.setContextMenuPolicy(Qt.CustomContextMenu)
            chip.clicked.connect(lambda _c=False, aid=a['id']: self._cycle(aid))
            chip.customContextMenuRequested.connect(lambda pos, aid=a['id']: self._menu(aid, pos))
            self._chips[a['id']] = chip
            self._state[a['id']] = CONTAINS if a['checked'] else (FACILITY if a.get('facility') else OFF)
            self._style(a['id'])
            grid.addWidget(chip, i // 3, i % 3)
        self._sync()

    # --- reading / writing ----------------------------------------------

    def checked_ids(self):
        '''Allergens the ingredient contains.'''
        return sorted(a for a, s in self._state.items() if s == CONTAINS)

    def facility_ids(self):
        '''Allergens that are only facility warnings.'''
        return sorted(a for a, s in self._state.items() if s == FACILITY)

    def set_checked(self, ids, facility_ids=()):
        ids, facility_ids = set(ids), set(facility_ids)
        for a in self._state:
            self._state[a] = CONTAINS if a in ids else (FACILITY if a in facility_ids else OFF)
            self._style(a)
        self._sync()

    # --- interaction ------------------------------------------------------

    def _set(self, aid, state):
        if self._state[aid] == state:
            return
        self._state[aid] = state
        self._style(aid)
        self._sync()
        self.changed.emit()

    def _cycle(self, aid):
        self._set(aid, {OFF: CONTAINS, CONTAINS: FACILITY, FACILITY: OFF}[self._state[aid]])

    def _menu(self, aid, pos):
        menu = QMenu(self)
        for state, label in ((CONTAINS, 'Contains'), (FACILITY, 'Facility (made alongside it)'), (OFF, 'None')):
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self._state[aid] == state)
            act.triggered.connect(lambda _c=False, s=state: self._set(aid, s))
        menu.exec(self._chips[aid].mapToGlobal(pos))

    def _on_bulk(self):
        flagged = [a for a, s in self._state.items() if s != OFF]
        to = CONTAINS if flagged and all(self._state[a] == FACILITY for a in flagged) else FACILITY
        for a in flagged:
            self._state[a] = to
            self._style(a)
        self._sync()
        self.changed.emit()

    # --- looks ------------------------------------------------------------

    def _style(self, aid):
        chip, state = self._chips[aid], self._state[aid]
        name = chip.property('allergen')
        if state == CONTAINS:
            css = (f'border: 1px solid {_ALERT}; background: {_ALERT_BG}; color: {_KALE}; font-weight: 600;')
        elif state == FACILITY:
            css = f'border: 1px dashed {_FAC}; background: {_FAC_BG}; color: {_FAC};'
        else:
            css = f'border: 1px solid #d6d3d1; background: #ffffff; color: {_KALE};'
        chip.setStyleSheet(f'QPushButton {{ {css} border-radius: 6px; padding: 4px 8px; text-align: left; }}')
        chip.setToolTip(name + ': ' + {OFF: 'not in this ingredient. Click: contains.',
                                       CONTAINS: 'contains it. Click: facility warning only.',
                                       FACILITY: 'made in a facility that also handles it. Click: off.'}[state])

    def _sync(self):
        flagged = [a for a, s in self._state.items() if s != OFF]
        all_facility = bool(flagged) and all(self._state[a] == FACILITY for a in flagged)
        self.bulk_btn.setText('Mark all as contains' if all_facility else 'Mark all as facility')
        self.bulk_btn.setEnabled(bool(flagged))
        names_by_id = {a: self._chips[a].property('allergen') for a in self._chips}
        contains = [names_by_id[a] for a in self.checked_ids()]
        facility = [names_by_id[a] for a in self.facility_ids()]
        out = diets.excluded_by(contains, self._diets, facility)
        if out:
            listed = out[0] if len(out) == 1 else ', '.join(out[:-1]) + ' or ' + out[-1]
            self.diet_hint.setText(f'Recipes with this don’t fit {listed}.')
        self.diet_hint.setVisible(bool(out))


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


class StatementBox(QWidget):
    '''"Ingredient statement": the ingredients list from the
    manufacturer's label, printed under this ingredient on recipe pages.'''

    def __init__(self, text='', parent=None):
        super().__init__(parent)
        title = QLabel('INGREDIENT STATEMENT')
        title.setStyleSheet(f'color: {_MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
        self.edit = QPlainTextEdit(text or '')
        self.edit.setPlaceholderText('From the manufacturer’s label')
        self.edit.setFixedHeight(72)
        self.edit.setStyleSheet(f'QPlainTextEdit {{ border: 1px solid {_FIELD_BORDER}; border-radius: 4px;'
                                f' background: #ffffff; color: {_KALE}; padding: 4px 6px; }}'
                                f' QPlainTextEdit:focus {{ border: 2px solid {_ROMAINE}; }}')
        hint = QLabel('Printed in small type on recipe print-out')
        hint.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(self.edit)
        layout.addWidget(hint)

    def text(self):
        return ' '.join(self.edit.toPlainText().split())

    def clear(self):
        self.edit.clear()
