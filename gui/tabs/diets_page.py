'''Configure › Diets: the rules behind the Library's diet chips, Diets
filter and Group by Diets.

A diet excludes recipes containing any of its allergens and/or needs a
nutrient per serving at least (or at most) some amount. The list shows
each rule in words and how many recipes on the menu fit; drag to
reorder (the order chips and groups use). Changes save as you make
them; `changed` tells the main window to recompute the Library.
'''
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QScrollArea, QVBoxLayout, QWidget,
)

import db
from gui.widgets import config_kit as kit
from gui.widgets.toolbar_controls import ToolbarCombo
from utilities import diets


class DietsPage(QWidget):
    changed = Signal()

    def __init__(self, recipes_model, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._diets = []
        self._loading = False

        # list column
        new_btn = kit.button('+ New diet')
        new_btn.clicked.connect(self.new_diet)
        head = QHBoxLayout()
        head.addWidget(kit.heading('Diets'))
        head.addStretch()
        head.addWidget(new_btn)
        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.currentRowChanged.connect(self._show_current)
        self.list.model().rowsMoved.connect(self._on_reordered)
        left = QWidget()
        left.setFixedWidth(300)
        left.setObjectName('DietsList')
        left.setStyleSheet(f'QWidget#DietsList {{ border-right: 1px solid {kit.BORDER}; }}')
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 20, 16, 16)
        ll.setSpacing(12)
        ll.addLayout(head)
        ll.addWidget(self.list, stretch=1)

        # detail
        self.name_edit = kit.field(320)
        self.name_edit.editingFinished.connect(self._on_name)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        name_col.addWidget(kit.eyebrow('Name'))
        name_col.addWidget(self.name_edit)

        allergen_card, al = kit.card()
        al.addWidget(kit.subheading('Excludes allergens'))
        self._allergen_grid = QGridLayout()
        self._allergen_grid.setHorizontalSpacing(16)
        self._allergen_grid.setVerticalSpacing(6)
        al.addLayout(self._allergen_grid)
        self._boxes = {}
        self.strict_box = QCheckBox('Strict: also exclude facility warnings')
        self.strict_box.setStyleSheet(f'QCheckBox {{ color: {kit.KALE}; spacing: 8px; font-weight: 600; }}')
        self.strict_box.toggled.connect(lambda _on: self._on_strict())
        al.addWidget(self.strict_box)

        nutrient_card, nl = kit.card()
        nl.addWidget(kit.subheading('Nutrient rule'))
        nl.addWidget(kit.note('Per serving'))
        self.nutrient_combo = ToolbarCombo()
        self.nutrient_combo.addItem('No nutrient rule', None)
        for key, label, _unit in diets.NUTRIENTS:
            self.nutrient_combo.addItem(label, key)
        self.nutrient_combo.activated.connect(lambda _i: self._on_nutrient())
        self.op_combo = ToolbarCombo()
        self.op_combo.addItem('at least', 'min')
        self.op_combo.addItem('at most', 'max')
        self.op_combo.activated.connect(lambda _i: self._on_nutrient())
        self.amount_edit = kit.field(90)
        self.amount_edit.setAlignment(Qt.AlignRight)
        self.amount_edit.setValidator(QDoubleValidator(0.0, 100000.0, 2))
        self.amount_edit.editingFinished.connect(self._on_nutrient)
        self.unit_label = QLabel('')
        self.unit_label.setStyleSheet(f'color: {kit.MUTED};')
        rule = QHBoxLayout()
        rule.setSpacing(8)
        for w in (self.nutrient_combo, self.op_combo, self.amount_edit, self.unit_label):
            rule.addWidget(w)
        rule.addStretch()
        nl.addLayout(rule)

        self.fit_label = QLabel('')
        self.fit_label.setWordWrap(True)
        self.fit_label.setMinimumWidth(1)
        self.fit_label.setStyleSheet(f'color: {kit.KALE};')
        self.delete_btn = kit.button('Delete diet…', danger=True)
        self.delete_btn.clicked.connect(self.delete_current)

        self.detail = QWidget()
        self.detail.setObjectName('DietDetail')
        self.detail.setStyleSheet(f'QWidget#DietDetail {{ background: {kit.BG}; }}')
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(28, 20, 28, 28)
        dl.setSpacing(20)
        dl.addLayout(name_col)
        dl.addWidget(allergen_card)
        dl.addWidget(nutrient_card)
        dl.addWidget(self.fit_label)
        dl.addStretch()
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(self.delete_btn)
        dl.addLayout(foot)
        self.empty = kit.note('Add a diet to describe what it excludes.')
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(self.detail)
        scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; border: 0; }}')

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(left)
        layout.addWidget(scroll, stretch=1)

        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(300)
        self._emit_timer.timeout.connect(self.changed.emit)
        self.refresh()

    # --- data ------------------------------------------------------------

    def refresh(self, select_id=None):
        current = self.current()
        select_id = select_id or (current['id'] if current else None)
        self._diets = db.get_diets()
        self._build_allergen_boxes()
        self.list.blockSignals(True)
        self.list.clear()
        for d in self._diets:
            item = QListWidgetItem(self._item_text(d))
            item.setData(Qt.UserRole, d['id'])
            item.setToolTip(diets.describe(d))
            self.list.addItem(item)
        self.list.blockSignals(False)
        row = next((i for i, d in enumerate(self._diets) if d['id'] == select_id), 0 if self._diets else -1)
        self.list.setCurrentRow(row)
        self._show_current(row)

    def _build_allergen_boxes(self):
        allergens = db.get_all_allergen_rows()
        if [(a['id'], a['name']) for a in allergens] == [(k, b.text()) for k, b in self._boxes.items()]:
            return
        while self._allergen_grid.count():
            w = self._allergen_grid.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        self._boxes = {}
        for i, a in enumerate(allergens):
            cb = QCheckBox(a['name'])
            cb.setStyleSheet(f'QCheckBox {{ color: {kit.KALE}; spacing: 8px; }}')
            cb.toggled.connect(lambda _on: self._on_allergens())
            self._allergen_grid.addWidget(cb, i // 3, i % 3)
            self._boxes[a['id']] = cb

    def _menu_rows(self):
        return [r for r in self._model.rows() if not r.get('Archived')]

    def _fit_count(self, d):
        return sum(1 for r in self._menu_rows()
                   if diets.fits(d, r['Allergens'], r['PerServing'], r.get('FacilityAllergens')))

    def _item_text(self, d):
        n = self._fit_count(d)
        return f"{d['name']}\n{diets.describe(d)} · {n} recipe{'s' if n != 1 else ''}"

    def current(self):
        row = self.list.currentRow()
        return self._diets[row] if 0 <= row < len(self._diets) else None

    # --- showing -----------------------------------------------------------

    def _show_current(self, _row=None):
        d = self.current()
        self.detail.setEnabled(d is not None)
        if d is None:
            self.name_edit.clear()
            self.fit_label.setText('Add a diet to describe what it excludes.')
            return
        self._loading = True
        self.name_edit.setText(d['name'])
        for aid, cb in self._boxes.items():
            cb.setChecked(aid in d['allergen_ids'])
        self.strict_box.setChecked(d.get('strict', True))
        idx = self.nutrient_combo.findData(d['nutrient'])
        self.nutrient_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.op_combo.setCurrentIndex(self.op_combo.findData(d.get('op') or 'min'))
        self.amount_edit.setText('' if d['amount'] is None else '{:g}'.format(d['amount']))
        self._loading = False
        self._sync_rule_widgets()
        self._sync_fit(d)

    def _sync_rule_widgets(self):
        key = self.nutrient_combo.currentData()
        for w in (self.op_combo, self.amount_edit):
            w.setEnabled(key is not None)
        self.unit_label.setText(f'{diets.NUTRIENT_UNITS.get(key, "")} per serving' if key else '')

    def _sync_fit(self, d):
        rows = self._menu_rows()
        fit = [r['Name'] for r in rows
               if diets.fits(d, r['Allergens'], r['PerServing'], r.get('FacilityAllergens'))]
        sample = ', '.join(sorted(fit, key=str.lower)[:5]) + ('…' if len(fit) > 5 else '')
        self.fit_label.setText(f'<b>Fits {len(fit)} of {len(rows)} recipes on the menu</b>'
                               + (f'<br><span style="color: {kit.MUTED}">{sample}</span>' if fit else ''))
        item = self.list.currentItem()
        if item is not None:
            item.setText(self._item_text(d))
            item.setToolTip(diets.describe(d))

    # --- edits -----------------------------------------------------------

    def _after_edit(self):
        d = self.current()
        fresh = next((x for x in db.get_diets() if x['id'] == d['id']), None)
        if fresh is not None:
            self._diets[self.list.currentRow()] = fresh
            self._sync_fit(fresh)
        self._emit_timer.start()

    def _on_name(self):
        d = self.current()
        name = self.name_edit.text().strip()
        if self._loading or d is None or name == d['name']:
            return
        taken = {x['name'].lower() for x in self._diets if x['id'] != d['id']}
        if not name or name.lower() in taken:
            QMessageBox.information(self, 'Diet name', f'There is already a diet called “{name}”.'
                                    if name else 'A diet needs a name.')
            self.name_edit.setText(d['name'])
            return
        db.update_diet(d['id'], name=name)
        self._after_edit()

    def _on_strict(self):
        d = self.current()
        if self._loading or d is None:
            return
        db.update_diet(d['id'], strict=self.strict_box.isChecked())
        self._after_edit()

    def _on_allergens(self):
        d = self.current()
        if self._loading or d is None:
            return
        db.set_diet_allergens(d['id'], [aid for aid, cb in self._boxes.items() if cb.isChecked()])
        self._after_edit()

    def _on_nutrient(self):
        self._sync_rule_widgets()
        d = self.current()
        if self._loading or d is None:
            return
        key = self.nutrient_combo.currentData()
        try:
            amount = float(self.amount_edit.text()) if key and self.amount_edit.text().strip() else None
        except ValueError:
            amount = None
        db.update_diet(d['id'], nutrient=key, op=self.op_combo.currentData(), amount=amount)
        self._after_edit()

    def new_diet(self, name=None):
        taken = {d['name'].lower() for d in self._diets}
        if name is None:
            name, n = 'New diet', 2
            while name.lower() in taken:
                name, n = f'New diet {n}', n + 1
        new_id = db.create_diet(name)
        self.refresh(select_id=new_id)
        self.name_edit.setFocus()
        self.name_edit.selectAll()
        self._emit_timer.start()
        return new_id

    def delete_current(self, confirm=True):
        d = self.current()
        if d is None:
            return
        if confirm and QMessageBox.question(
                self, 'Delete diet', f'Delete the diet “{d["name"]}”?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_diet(d['id'])
        self.refresh()
        self._emit_timer.start()

    def _on_reordered(self, *_args):
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        db.reorder_diets(ids)
        by_id = {d['id']: d for d in self._diets}
        self._diets = [by_id[i] for i in ids]
        self._emit_timer.start()
