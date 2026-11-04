'''Configure › Vendor items, per the Framework canvas: every vendor item
the imports have seen, what ingredient it is and what a case yields.

A filterable table on the left; the selected item's editor on the
right. Saving a changed yield re-prices the imports that bought it.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QFrame, QHBoxLayout, QHeaderView, QLabel, QMessageBox,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gui.widgets import config_kit as kit
from gui.widgets.vendor_item_editor import VendorItemEditor
from utilities import purchase_import as pi

_RED = '#a3261b'
_RED_BG = '#fde8e4'
_CHIP = (f'QPushButton {{ height: 28px; padding: 0 12px; border-radius: 14px; border: 1px solid {kit.BORDER};'
         f' background: #ffffff; color: {kit.KALE}; }}'
         f' QPushButton:checked {{ background: {kit.ROMAINE}; border-color: {kit.ROMAINE}; color: #ffffff;'
         ' font-weight: 600; }')


def _state(v, flags):
    if v['status'] == 'ignored':
        return 'ignored'
    if v['status'] == 'mapped' and v.get('ingredient_id'):
        return 'flagged' if v['id'] in flags else 'mapped'
    return 'unmapped'


class VendorItemsPage(QWidget):
    changed = Signal()            # prices changed
    importRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._flags = {}
        self._filter = 'all'
        self._selected_id = None

        title = kit.heading('Vendor items')
        sub = kit.note('What each case on an invoice yields, in portions of an ingredient. Many vendor items can'
                       ' feed one ingredient.')
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(title)
        head_text.addWidget(sub)
        import_btn = kit.button('Import purchases…', primary=True)
        import_btn.clicked.connect(self.importRequested.emit)
        head = QHBoxLayout()
        head.addLayout(head_text, stretch=1)
        head.addWidget(import_btn, alignment=Qt.AlignTop)

        self.search = kit.field(280)
        self.search.setPlaceholderText('Search description, code or ingredient')
        self.search.textChanged.connect(self._fill)
        self.chips = {}
        group = QButtonGroup(self)
        filters = QHBoxLayout()
        filters.setSpacing(6)
        filters.addWidget(self.search)
        for key, label in (('all', 'All'), ('mapped', 'Mapped'), ('flagged', 'Flagged'),
                           ('unmapped', 'Not mapped'), ('ignored', 'Ignored')):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(_CHIP)
            btn.clicked.connect(lambda _=False, k=key: self._set_filter(k))
            group.addButton(btn)
            self.chips[key] = btn
            filters.addWidget(btn)
        filters.addStretch()
        self.vendor = QComboBox()
        self.vendor.currentIndexChanged.connect(self._fill)
        filters.addWidget(self.vendor)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Vendor item', 'Pack', 'Ingredient', 'Case yields', 'Case',
                                              'Per portion', 'Last bought'])
        self.table.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; border: 1px solid {kit.BORDER}; border-radius: 8px; color: {kit.KALE};
                selection-background-color: {kit.SELECTED}; selection-color: {kit.KALE}; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.MUTED}; border: 0;
                border-bottom: 1px solid {kit.BORDER}; padding: 6px 8px; font-size: 11px; font-weight: 600; }}''')
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.itemSelectionChanged.connect(self._on_select)

        # detail panel
        panel = QFrame()
        panel.setObjectName('VIPanel')
        panel.setStyleSheet(f'QFrame#VIPanel {{ background: #ffffff; border: 1px solid {kit.BORDER};'
                            ' border-radius: 8px; }')
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 14, 16, 16)
        pl.setSpacing(12)
        self.d_meta = kit.note('')
        self.d_title = QLabel('')
        self.d_title.setWordWrap(True)
        self.d_title.setStyleSheet(f'color: {kit.KALE}; font-size: 16px; font-weight: 650;')
        self.d_inv = kit.note('')
        self.d_flag = QLabel('')
        self.d_flag.setWordWrap(True)
        self.d_flag.setStyleSheet(f'color: {_RED}; background: {_RED_BG}; border-radius: 8px; padding: 8px 10px;'
                                  ' font-size: 12px;')
        status_row = QHBoxLayout()
        self.status_group = QButtonGroup(self)
        self.status_btns = {}
        for key, label in (('mapped', 'Mapped'), ('ignored', 'Ignored')):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_CHIP.replace('border-radius: 14px', 'border-radius: 8px'))
            btn.clicked.connect(self._on_status)
            self.status_group.addButton(btn)
            self.status_btns[key] = btn
            status_row.addWidget(btn)
        self.editor = VendorItemEditor()
        self.editor.changed.connect(self._on_dirty)
        self.feeds_title = kit.eyebrow('')
        self.feeds = kit.note('')
        self.reprice_note = kit.note('')
        self.revert_btn = kit.button('Revert')
        self.revert_btn.clicked.connect(self._on_select)
        self.save_btn = kit.button('Save && re-price', primary=True)
        self.save_btn.clicked.connect(self._save)
        btns = QHBoxLayout()
        btns.addWidget(self.revert_btn)
        btns.addStretch()
        btns.addWidget(self.save_btn)
        for w in (self.d_meta, self.d_title, self.d_inv, self.d_flag):
            pl.addWidget(w)
        pl.addLayout(status_row)
        pl.addWidget(self.editor)
        pl.addWidget(self.feeds_title)
        pl.addWidget(self.feeds)
        pl.addStretch()
        pl.addWidget(self.reprice_note)
        pl.addLayout(btns)
        self.panel = panel
        self.empty = kit.note('No vendor items yet. Import a purchase history file to start.')
        panel_scroll = QScrollArea()
        panel_scroll.setWidgetResizable(True)
        panel_scroll.setFrameShape(QFrame.NoFrame)
        panel_scroll.setWidget(panel)
        panel_scroll.setFixedWidth(440)
        self.panel_scroll = panel_scroll

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self.table, stretch=1)
        body.addWidget(panel_scroll)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 24)
        layout.setSpacing(14)
        layout.addLayout(head)
        layout.addLayout(filters)
        layout.addWidget(self.empty)
        layout.addLayout(body, stretch=1)
        self.chips['all'].setChecked(True)
        self.refresh()

    # --- data ----------------------------------------------------------

    def refresh(self):
        self._items = pi.get_vendor_items()
        self._flags = pi.vendor_item_flags(self._items)
        self._ingredients = pi.get_ingredients()
        self.editor.set_ingredients(self._ingredients)
        vendors = sorted({v['vendor_name'] or '' for v in self._items}, key=str.casefold)
        current = self.vendor.currentData()
        self.vendor.blockSignals(True)
        self.vendor.clear()
        self.vendor.addItem('All vendors', None)
        for name in vendors:
            self.vendor.addItem(name, name)
        self.vendor.setCurrentIndex(max(self.vendor.findData(current), 0) if current else 0)
        self.vendor.blockSignals(False)
        counts = {k: 0 for k in self.chips}
        for v in self._items:
            counts['all'] += 1
            st = _state(v, self._flags)
            counts[st] += 1
            if st == 'flagged':
                counts['mapped'] += 1
        for key, btn in self.chips.items():
            label = {'all': 'All', 'mapped': 'Mapped', 'flagged': 'Flagged', 'unmapped': 'Not mapped',
                     'ignored': 'Ignored'}[key]
            btn.setText(f'{label}  {counts[key]}')
        self.empty.setVisible(not self._items)
        self._fill()

    def flagged_count(self):
        return len(self._flags)

    def _set_filter(self, key):
        self._filter = key
        self._fill()

    def _visible(self):
        text = self.search.text().strip().casefold()
        vendor = self.vendor.currentData()
        out = []
        for v in self._items:
            st = _state(v, self._flags)
            if self._filter == 'mapped' and st not in ('mapped', 'flagged'):
                continue
            if self._filter not in ('all', 'mapped') and st != self._filter:
                continue
            if vendor and v['vendor_name'] != vendor:
                continue
            if text and text not in ' '.join(str(v.get(k) or '') for k in (
                    'description', 'item_code', 'ingredient_name', 'inventory_item', 'pack_size')).casefold():
                continue
            out.append(v)
        return out

    def _fill(self, *_):
        rows = self._visible()
        self._rows = rows
        t = self.table
        t.blockSignals(True)
        t.setRowCount(len(rows))
        select_row = -1
        for r, v in enumerate(rows):
            st = _state(v, self._flags)
            ppc, _ = pi.portions_per_case(v, v.get('portion_grams')) if st in ('mapped', 'flagged') else (None, None)
            price = v.get('last_case_price')
            per = pi.money(price / ppc, 3) if ppc and price else '—'
            code = v.get('item_code') or 'no item code'
            vals = [f'{v["description"]}   ·   {v["vendor_name"]} · {code}', v.get('pack_size') or '',
                    v.get('ingredient_name') or ('ignored' if st == 'ignored' else 'not mapped'),
                    pi.yield_short(v) if st in ('mapped', 'flagged') else '—', pi.money(price), per,
                    v.get('last_seen') or '']
            for c, val in enumerate(vals):
                item = QTableWidgetItem(val)
                if c in (4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 2 and st in ('ignored', 'unmapped'):
                    item.setForeground(QColor(kit.MUTED))
                    f = item.font()
                    f.setItalic(True)
                    item.setFont(f)
                if c == 5 and st == 'flagged':
                    item.setForeground(QColor(_RED))
                    item.setBackground(QColor(_RED_BG))
                if c == 0:
                    item.setData(Qt.UserRole, v['id'])
                    item.setToolTip(f'{v.get("inventory_item") or ""}')
                t.setItem(r, c, item)
            if v['id'] == self._selected_id:
                select_row = r
        t.blockSignals(False)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        if rows:
            t.selectRow(select_row if select_row >= 0 else 0)
            self._on_select()
        self.panel_scroll.setVisible(bool(rows))

    # --- detail --------------------------------------------------------

    def _current(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(getattr(self, '_rows', [])):
            return None
        return self._rows[row]

    def _on_select(self):
        v = self._current()
        if v is None:
            return
        self._selected_id = v['id']
        code = v.get('item_code') or 'no item code'
        self.d_meta.setText(f'{v["vendor_name"]} · {code} · GL {v.get("gl_code") or "—"}')
        self.d_title.setText(f'{v["description"]}  ·  {v.get("pack_size") or ""}')
        self.d_inv.setText(f'Inventory item “{v.get("inventory_item") or "—"}” · last bought {v.get("last_seen") or "—"}'
                           f' at {pi.money(v.get("last_case_price"))} a case')
        flag = self._flags.get(v['id'])
        self.d_flag.setText(f'<b>{flag[0]}</b><br>{flag[1]}' if flag else '')
        self.d_flag.setVisible(bool(flag))
        status = 'ignored' if v['status'] == 'ignored' else 'mapped'
        self.status_btns[status].setChecked(True)
        self.editor.set_item(v, v.get('last_case_price'))
        self.editor.setEnabled(status == 'mapped')
        self._refresh_feeds()
        batches = pi.batches_with_item(v['id'])
        self.reprice_note.setText(f'Saving re-prices the {len(batches)} import{"s" if len(batches) != 1 else ""}'
                                  ' that bought this item.' if batches else 'No imports have priced this item yet.')
        self.save_btn.setText('Save && re-price' if batches else 'Save')
        self._dirty(False)

    def _refresh_feeds(self):
        v = self._current()
        ing_id = self.editor.ingredient_id()
        if v is None or not ing_id:
            self.feeds_title.setText('')
            self.feeds.setText('')
            return
        name = next((i['Name'] for i in self._ingredients if i['Id'] == ing_id), '')
        lines = []
        for o in self._items:
            if o['id'] == v['id'] or o['status'] != 'mapped' or o.get('ingredient_id') != ing_id:
                continue
            ppc, _ = pi.portions_per_case(o, o.get('portion_grams'))
            price = o.get('last_case_price')
            lines.append(f'{o["description"]} {o.get("pack_size") or ""}: '
                         f'{pi.money(price / ppc, 3) if ppc and price else "—"} a portion')
        self.feeds_title.setText(f'ALSO FEEDING {name.upper()}' if lines else '')
        self.feeds.setText('\n'.join(lines))

    def _on_status(self):
        mapped = self.status_btns['mapped'].isChecked()
        self.editor.setEnabled(mapped)
        self._dirty(True)

    def _on_dirty(self):
        self._refresh_feeds()
        self._dirty(True)

    def _dirty(self, on):
        self.revert_btn.setEnabled(on)
        self.save_btn.setEnabled(on)

    def _save(self):
        v = self._current()
        if v is None:
            return
        item = {k: v.get(k) for k in ('id', 'vendor_key', 'vendor_name', 'item_code', 'description', 'pack_size',
                                      'inventory_item', 'gl_code', 'last_case_price', 'last_seen', 'ingredient_id',
                                      'case_qty', 'case_unit', 'yield_pct', 'portions_per_each', 'notes')}
        if self.status_btns['ignored'].isChecked():
            item['status'] = 'ignored'
        else:
            item.update(self.editor.item_values())
            if not item['ingredient_id']:
                QMessageBox.information(self, 'Vendor items', 'Pick the ingredient this item is, or mark it Ignored.')
                return
            ing = next((i for i in self._ingredients if i['Id'] == item['ingredient_id']), {})
            ppc, why = pi.portions_per_case(item, ing.get('Weight'))
            if ppc is None:
                QMessageBox.information(self, 'Vendor items', f'Can’t work out portions per case: {why}.')
                return
            item['status'] = 'mapped'
        n = pi.update_vendor_item(item)
        self.refresh()
        if n:
            self.changed.emit()
