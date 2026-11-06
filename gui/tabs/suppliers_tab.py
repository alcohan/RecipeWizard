'''Configure › Suppliers: the suppliers prices come from.

A list on the left (each with how many ingredients it currently prices),
the chosen supplier on the right: its name and address (saved as you
edit), the names it goes by in purchase files and how many vendor items
it sells, and the ingredients whose current price is from it. A supplier
that any price entry uses can't be deleted. `changed` tells the main
window a name changed.
'''
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QScrollArea,
    QVBoxLayout, QWidget,
)

import db
from gui.widgets import config_kit as kit

_FIELDS = (('address', 'Address', None), ('city', 'City', 200), ('state', 'State', 80), ('zip', 'Zip', 110))
_SHOWN = 12


def _day(iso):
    if not iso:
        return ''
    try:
        import datetime
        d = datetime.date.fromisoformat(str(iso)[:10])
        return f'{d:%b} {d.day}, {d.year}'
    except ValueError:
        return str(iso)


class SuppliersTab(QWidget):
    changed = Signal()
    ingredientRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._loading = False
        self._show_all = False

        new_btn = kit.button('+ New supplier')
        new_btn.clicked.connect(lambda: self.new_supplier())
        head = QHBoxLayout()
        head.addWidget(kit.heading('Suppliers'))
        head.addStretch()
        head.addWidget(new_btn)
        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setWordWrap(True)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.currentRowChanged.connect(lambda _r: self._show_current())
        left = QWidget()
        left.setFixedWidth(300)
        left.setObjectName('SuppliersList')
        left.setStyleSheet(f'QWidget#SuppliersList {{ border-right: 1px solid {kit.BORDER}; }}')
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 20, 16, 16)
        ll.setSpacing(12)
        ll.addLayout(head)
        ll.addWidget(self.list, stretch=1)

        # detail: name and address
        self.name_edit = kit.field(320)
        self.name_edit.editingFinished.connect(self._save)
        self._edits = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.addWidget(kit.eyebrow('Name'), 0, 0, 1, 3)
        grid.addWidget(self.name_edit, 1, 0, 1, 3)
        address = kit.field(420)
        self._edits['address'] = address
        grid.addWidget(kit.eyebrow('Address'), 2, 0, 1, 3)
        grid.addWidget(address, 3, 0, 1, 3)
        for c, (key, label, width) in enumerate(_FIELDS[1:]):
            edit = kit.field(width)
            self._edits[key] = edit
            grid.addWidget(kit.eyebrow(label), 4, c)
            grid.addWidget(edit, 5, c)
        for edit in self._edits.values():
            edit.editingFinished.connect(self._save)
        grid.setColumnStretch(3, 1)

        files_card, fc = kit.card()
        fc.addWidget(kit.subheading('Purchase files'))
        self.files_label = QLabel('')
        self.files_label.setWordWrap(True)
        self.files_label.setStyleSheet(f'color: {kit.KALE};')
        fc.addWidget(self.files_label)

        prices_card, pc = kit.card()
        self.prices_title = kit.subheading('Current prices')
        pc.addWidget(self.prices_title)
        self.prices_grid = QGridLayout()
        self.prices_grid.setHorizontalSpacing(16)
        self.prices_grid.setVerticalSpacing(6)
        self.prices_grid.setColumnStretch(0, 1)
        pc.addLayout(self.prices_grid)
        self.more_link = QLabel('')
        self.more_link.setTextFormat(Qt.RichText)
        self.more_link.linkActivated.connect(self._toggle_all)
        pc.addWidget(self.more_link)

        self.delete_btn = kit.button('Delete supplier…', danger=True)
        self.delete_btn.clicked.connect(lambda: self.delete_current())

        self.detail = QWidget()
        self.detail.setObjectName('SupplierDetail')
        self.detail.setStyleSheet(f'QWidget#SupplierDetail {{ background: {kit.BG}; }}')
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(28, 20, 28, 28)
        dl.setSpacing(20)
        dl.addLayout(grid)
        dl.addWidget(files_card)
        dl.addWidget(prices_card)
        dl.addStretch()
        foot = QHBoxLayout()
        foot.addStretch()
        foot.addWidget(self.delete_btn)
        dl.addLayout(foot)
        self.empty = kit.note('No suppliers yet')
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

    # --- data ---

    def refresh(self, select_id=None):
        current = self.current()
        select_id = select_id or (current['id'] if current else None)
        self._rows = db.get_supplier_overview()
        self.list.blockSignals(True)
        self.list.clear()
        for s in self._rows:
            n = len(s['current'])
            sub = f"{n} ingredient{'s' if n != 1 else ''}" if n else 'No current prices'
            item = QListWidgetItem(f"{s['name'] or 'Unnamed'}\n{sub}")
            item.setData(Qt.UserRole, s['id'])
            # Two lines, whatever the selection border does to the layout.
            item.setSizeHint(QSize(0, self.list.fontMetrics().lineSpacing() * 2 + 32))
            self.list.addItem(item)
        self.list.blockSignals(False)
        row = next((i for i, s in enumerate(self._rows) if s['id'] == select_id), 0 if self._rows else -1)
        self.list.setCurrentRow(row)
        self._show_current()

    def current(self):
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _show_current(self):
        s = self.current()
        self.detail.setEnabled(s is not None)
        if s is None:
            return
        self._loading = True
        self.name_edit.setText(s['name'] or '')
        for key, edit in self._edits.items():
            edit.setText(s.get(key) or '')
        self._loading = False

        names = s['aliases']
        bits = []
        if names:
            bits.append('Also appears as ' + ', '.join(f'“{n}”' for n in names))
        n = s['vendor_items']
        bits.append(f"{n} vendor item{'s' if n != 1 else ''}" if n else 'No vendor items yet')
        if s['last_price']:
            bits.append(f"last price {_day(s['last_price'])}")
        self.files_label.setText(' · '.join(bits))

        self.delete_btn.setEnabled(not s['prices'])
        self.delete_btn.setToolTip(f"Used by {s['prices']} price{'s' if s['prices'] != 1 else ''}"
                                   if s['prices'] else '')
        self._fill_prices(s)

    def _fill_prices(self, s):
        while self.prices_grid.count():
            w = self.prices_grid.takeAt(0).widget()
            if w is not None:
                w.hide()          # deleteLater alone leaves it painted until the next loop
                w.deleteLater()
        rows = s['current']
        self.prices_title.setText(f'Current prices · {len(rows)}' if rows else 'Current prices')
        if not rows:
            self.prices_grid.addWidget(kit.note('None'), 0, 0)
            self.more_link.hide()
            return
        link = f'color: {kit.KALE}'
        shown = rows if self._show_all else rows[:_SHOWN]
        for r, row in enumerate(shown):
            name = QLabel(f'<a href="{row["Id"]}" style="{link}">{_esc(row["Name"])}</a>')
            name.setTextFormat(Qt.RichText)
            name.linkActivated.connect(lambda href: self.ingredientRequested.emit(int(href)))
            price = QLabel(f'${float(row["unit_price"] or 0):.3f} / {_esc(row["Unit"] or "")}')
            price.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            when = QLabel(_day(row['effective_date']))
            when.setStyleSheet(f'color: {kit.MUTED};')
            when.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            for c, w in enumerate((name, price, when)):
                self.prices_grid.addWidget(w, r, c)
        extra = len(rows) - _SHOWN
        self.more_link.setVisible(extra > 0)
        if extra > 0:
            self.more_link.setText(f'<a href="toggle" style="color: {kit.ROMAINE}">'
                                   f'{"Show fewer" if self._show_all else f"{extra} more"}</a>')

    def _toggle_all(self, _href):
        self._show_all = not self._show_all
        s = self.current()
        if s is not None:
            self._fill_prices(s)

    # --- edits ---

    def _save(self):
        s = self.current()
        if s is None or self._loading:
            return
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setText(s['name'] or '')
            return
        taken = {(r['name'] or '').lower() for r in self._rows if r['id'] != s['id']}
        if name.lower() in taken:
            QMessageBox.information(self, 'Supplier name', f'There is already a supplier called “{name}”.')
            self.name_edit.setText(s['name'] or '')
            return
        values = {'name': name, **{k: e.text().strip() for k, e in self._edits.items()}}
        if all((s.get(k) or '') == v for k, v in values.items()):
            return
        db.update_supplier(s['id'], values)
        renamed = name != s['name']
        s.update(values)
        if renamed:
            self.refresh(select_id=s['id'])
            self._emit_timer.start()

    def new_supplier(self, name=None):
        taken = {(r['name'] or '').lower() for r in self._rows}
        if name is None:
            name, n = 'New supplier', 2
            while name.lower() in taken:
                name, n = f'New supplier {n}', n + 1
        new_id = db.create_supplier({'name': name, 'address': '', 'city': '', 'state': '', 'zip': ''})
        self.refresh(select_id=new_id)
        self.name_edit.setFocus()
        self.name_edit.selectAll()
        self._emit_timer.start()
        return new_id

    def delete_current(self, confirm=True):
        s = self.current()
        if s is None or s['prices']:
            return
        if confirm and QMessageBox.question(self, 'Delete supplier', f'Delete “{s["name"]}”?',
                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_supplier(s['id'])
        self.refresh()
        self._emit_timer.start()

    def focus_filter(self):
        self.list.setFocus()


def _esc(text):
    return (text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
