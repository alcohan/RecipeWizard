'''Configure › Allergens: the allergen list ingredients are tagged with.

The order here is the order allergens appear everywhere (checkbox
grids, inspector, Free from); drag to reorder. Double-click or F2 to
rename. Each row says how many ingredients and recipes have it and
which diets exclude it. Deleting one clears it from ingredients and
diet rules, after asking. `changed` tells the main window to refresh.
'''
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QListWidget, QListWidgetItem, QMessageBox, QVBoxLayout, QWidget,
)

import db
from gui.widgets import config_kit as kit


class AllergensPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        new_btn = kit.button('+ New allergen')
        new_btn.clicked.connect(lambda: self.new_allergen())
        self.delete_btn = kit.button('Delete…', danger=True)
        self.delete_btn.clicked.connect(lambda: self.delete_current())
        head = QHBoxLayout()
        head.addWidget(kit.heading('Allergens'))
        head.addStretch()
        head.addWidget(new_btn)

        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setMaximumWidth(560)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.list.itemChanged.connect(self._on_renamed)
        self.list.model().rowsMoved.connect(self._on_reordered)
        self.list.currentRowChanged.connect(lambda _r: self._sync_buttons())

        foot = QHBoxLayout()
        foot.addWidget(self.delete_btn)
        foot.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(kit.note('The order here is the order allergens appear everywhere. Drag to reorder;'
                                  ' double-click to rename. Diets use them in Configure › Diets.'))
        layout.addWidget(self.list, stretch=1)
        layout.addLayout(foot)

        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(300)
        self._emit_timer.timeout.connect(self.changed.emit)
        self.refresh()

    def refresh(self, select_id=None):
        current = self.current()
        select_id = select_id or (current['id'] if current else None)
        self._rows = db.get_allergen_usage()
        excluded_by = {}
        for d in db.get_diets():
            for aid in d['allergen_ids']:
                excluded_by.setdefault(aid, []).append(d['name'])
        self.list.blockSignals(True)
        self.list.clear()
        for r in self._rows:
            item = QListWidgetItem(r['name'])
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(Qt.UserRole, r['id'])
            bits = [f"{r['Ingredients']} ingredient{'s' if r['Ingredients'] != 1 else ''}",
                    f"{r['Recipes']} recipe{'s' if r['Recipes'] != 1 else ''}"]
            tip = ' · '.join(bits)
            if excluded_by.get(r['id']):
                tip += '\nExcluded from ' + ', '.join(excluded_by[r['id']])
            item.setToolTip(tip)
            item.setData(Qt.UserRole + 1, ' · '.join(bits))
            self.list.addItem(item)
            item.setText(f"{r['name']}")
        self.list.blockSignals(False)
        self._decorate()
        row = next((i for i, r in enumerate(self._rows) if r['id'] == select_id), 0 if self._rows else -1)
        self.list.setCurrentRow(row)
        self._sync_buttons()

    def _decorate(self):
        '''Show the usage line under each name (kept out of the editable text).'''
        for i in range(self.list.count()):
            item = self.list.item(i)
            label = kit.note(item.data(Qt.UserRole + 1))
            label.setAttribute(Qt.WA_TransparentForMouseEvents)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setStyleSheet(label.styleSheet() + ' padding-right: 12px;')
            self.list.setItemWidget(item, label)

    def current(self):
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _sync_buttons(self):
        self.delete_btn.setEnabled(self.current() is not None)

    def _on_renamed(self, item):
        aid = item.data(Qt.UserRole)
        row = next(r for r in self._rows if r['id'] == aid)
        name = item.text().strip()
        taken = {r['name'].lower() for r in self._rows if r['id'] != aid}
        if not name or name.lower() in taken:
            self.list.blockSignals(True)
            item.setText(row['name'])
            self.list.blockSignals(False)
            if name:
                QMessageBox.information(self, 'Allergen name', f'There is already an allergen called “{name}”.')
            return
        if name != row['name']:
            db.rename_allergen(aid, name)
            row['name'] = name
            self._emit_timer.start()

    def _on_reordered(self, *_args):
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        db.reorder_allergens(ids)
        by_id = {r['id']: r for r in self._rows}
        self._rows = [by_id[i] for i in ids]
        self._emit_timer.start()

    def new_allergen(self, name=None):
        taken = {r['name'].lower() for r in self._rows}
        if name is None:
            name, n = 'New allergen', 2
            while name.lower() in taken:
                name, n = f'New allergen {n}', n + 1
        new_id = db.create_allergen(name)
        self.refresh(select_id=new_id)
        self.list.editItem(self.list.currentItem())
        self._emit_timer.start()
        return new_id

    def delete_current(self, confirm=True):
        r = self.current()
        if r is None:
            return
        used = []
        if r['Ingredients']:
            used.append(f"{r['Ingredients']} ingredient{'s' if r['Ingredients'] != 1 else ''}")
        diet_names = [d['name'] for d in db.get_diets() if r['id'] in d['allergen_ids']]
        if diet_names:
            used.append('the ' + ', '.join(diet_names) + ' diet rule' + ('s' if len(diet_names) > 1 else ''))
        msg = f'Delete “{r["name"]}”?'
        if used:
            msg += ' It will be removed from ' + ' and '.join(used) + '.'
        if confirm and QMessageBox.question(self, 'Delete allergen', msg, QMessageBox.Yes | QMessageBox.No,
                                            QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_allergen(r['id'])
        self.refresh()
        self._emit_timer.start()
