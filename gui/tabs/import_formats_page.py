'''Configure › Import formats & history, per the Framework canvas.

Left: the saved import formats. Right: the selected format's column
mapper, reading rules and vendor names (FormatEditor, also used by the
Import purchases dialog to make a format from a new file), then the
history of imports with Re-price and Undo.
'''
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QListWidget, QListWidgetItem, QMessageBox, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from gui.widgets import config_kit as kit
from utilities import purchase_import as pi

_NOT_IN_FILE = '(not in file)'
_TABLE_STYLE = f'''
    QTableWidget {{ background: #ffffff; border: 0; color: {kit.KALE}; gridline-color: #f3ece0;
        selection-background-color: {kit.SELECTED}; selection-color: {kit.KALE}; }}
    QHeaderView::section {{ background: #ffffff; color: {kit.MUTED}; border: 0;
        border-bottom: 1px solid {kit.BORDER}; padding: 6px 8px; font-size: 11px; font-weight: 600; }}
'''


def _style_table(table):
    table.setStyleSheet(_TABLE_STYLE)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setShowGrid(False)
    table.setFocusPolicy(Qt.NoFocus)
    table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)


class FormatEditor(QWidget):
    '''One import format: name, which column is which, reading rules,
    vendor name → supplier, and what imports remembered.'''

    saved = Signal()
    deleted = Signal()

    def __init__(self, show_delete=True, parent=None):
        super().__init__(parent)
        self.format_id = None
        self._settings = pi.default_settings()
        self._headers = []

        self.name = kit.field()
        self.name.setMaximumWidth(420)

        cols_card, cc = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading('Columns'))
        self.cols_note = kit.note('')
        head.addWidget(self.cols_note, stretch=1)
        cc.addLayout(head)
        self.cols = QTableWidget(len(pi.FIELDS), 3)
        self.cols.setHorizontalHeaderLabels(['Field', 'Column in file', 'Sample'])
        _style_table(self.cols)
        self.cols.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.col_combos = {}
        for r, (key, label, required, help_text) in enumerate(pi.FIELDS):
            text = QLabel(f'<b>{label}</b>' if required else label)
            text.setToolTip(help_text)
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(8, 2, 8, 2)
            bl.setSpacing(0)
            bl.addWidget(text)
            hl = kit.note(help_text)
            hl.setStyleSheet(f'color: {kit.MUTED}; font-size: 11px;')
            bl.addWidget(hl)
            self.cols.setCellWidget(r, 0, box)
            combo = QComboBox()
            combo.setMinimumWidth(200)
            combo.currentIndexChanged.connect(lambda _=0, k=key: self._show_sample(k))
            self.col_combos[key] = combo
            self.cols.setCellWidget(r, 1, combo)
            self.cols.setItem(r, 2, QTableWidgetItem(''))
            self.cols.setRowHeight(r, 44)
        self.cols.setColumnWidth(0, 260)
        self.cols.setColumnWidth(1, 230)
        self.cols.setMinimumHeight(44 * len(pi.FIELDS) + 34)
        cc.addWidget(self.cols)

        rules_card, rc = kit.card()
        rc.addWidget(kit.subheading('Reading rules'))
        grid = QGridLayout()
        grid.addWidget(QLabel('Date format'), 0, 0)
        self.date_format = QComboBox()
        self.date_format.addItems(list(pi.DATE_FORMATS))
        grid.addWidget(self.date_format, 0, 1)
        grid.addWidget(QLabel('Price per line comes from'), 1, 0)
        self.price_from = QComboBox()
        self.price_from.addItem('Amount ÷ Quantity', 'amount')
        self.price_from.addItem('Unit price column', 'unit_price')
        grid.addWidget(self.price_from, 1, 1)
        grid.setColumnStretch(2, 1)
        rc.addLayout(grid)
        self.skip_credits = QCheckBox('Skip credits (negative quantity or amount)')
        self.catch_weight = QCheckBox('Pack size “LB WEIGHT” means catch weight: quantity is pounds')
        rc.addWidget(self.skip_credits)
        rc.addWidget(self.catch_weight)
        rc.addWidget(kit.note('When the item code is blank, items are told apart by description + pack size.'))

        vendors_card, vc = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading('Vendor names'))
        head.addWidget(kit.note('Name in file → supplier'), stretch=1)
        vc.addLayout(head)
        self.vendor_grid = QGridLayout()
        self.vendor_grid.setColumnStretch(0, 1)
        vc.addLayout(self.vendor_grid)
        self.vendor_empty = kit.note('Filled in by the first import with this format.')
        vc.addWidget(self.vendor_empty)
        self.remembered = kit.note('')
        vc.addWidget(self.remembered)
        self.clear_remembered = kit.button('Include all locations next time')
        self.clear_remembered.clicked.connect(self._clear_remembered)
        vc.addWidget(self.clear_remembered, alignment=Qt.AlignLeft)

        side = QHBoxLayout()
        side.setSpacing(16)
        side.addWidget(rules_card, 1)
        side.addWidget(vendors_card, 1)

        self.delete_btn = kit.button('Delete format', danger=True)
        self.delete_btn.clicked.connect(self._delete)
        self.delete_btn.setVisible(show_delete)
        save = kit.button('Save format', primary=True)
        save.clicked.connect(self._save)
        buttons = QHBoxLayout()
        buttons.addWidget(self.delete_btn)
        buttons.addStretch()
        buttons.addWidget(save)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)
        layout.addWidget(kit.eyebrow('Name'))
        layout.addWidget(self.name)
        layout.addWidget(cols_card)
        layout.addLayout(side)
        layout.addLayout(buttons)

    def load(self, fmt, headers=None):
        self.format_id = fmt.get('id')
        self._settings = dict(fmt['settings'])
        cols = self._settings.get('columns', {})
        self._headers = list(headers or self._settings.get('headers') or [c for c in cols.values() if c])
        self.name.setText(fmt.get('name') or '')
        for key, combo in self.col_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(_NOT_IN_FILE, None)
            for h in self._headers:
                combo.addItem(h, h)
            col = cols.get(key)
            idx = combo.findData(col) if col else 0
            if col and idx < 0:
                combo.addItem(col, col)
                idx = combo.count() - 1
            combo.setCurrentIndex(max(idx, 0))
            combo.blockSignals(False)
            self._show_sample(key)
        sample = self._settings.get('sample')
        self.cols_note.setText('Sample values from the last file imported with this format. Bold fields are required.'
                               if sample else 'Bold fields are required.')
        self.date_format.setCurrentText(self._settings.get('date_format') or 'MM/DD/YYYY')
        self.price_from.setCurrentIndex(max(self.price_from.findData(self._settings.get('price_from', 'amount')), 0))
        self.skip_credits.setChecked(bool(self._settings.get('skip_credits', True)))
        self.catch_weight.setChecked(bool(self._settings.get('catch_weight', True)))
        self._load_vendors()
        self._load_remembered()

    def _show_sample(self, key):
        r = [k for k, *_ in pi.FIELDS].index(key)
        col = self.col_combos[key].currentData()
        value = (self._settings.get('sample') or {}).get(col, '') if col else ''
        item = self.cols.item(r, 2)
        if item is not None:
            item.setText(str(value)[:60])
            item.setForeground(Qt.darkGray)

    def _load_vendors(self):
        while self.vendor_grid.count():
            w = self.vendor_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.vendor_combos = {}
        aliases = self._settings.get('vendor_suppliers') or {}
        suppliers = pi.get_suppliers()
        for r, (name, sid) in enumerate(sorted(aliases.items(), key=lambda kv: kv[0].casefold())):
            self.vendor_grid.addWidget(QLabel(name), r, 0)
            combo = QComboBox()
            for s in suppliers:
                combo.addItem(s['name'], s['id'])
            combo.setCurrentIndex(max(combo.findData(sid), 0))
            self.vendor_grid.addWidget(combo, r, 1)
            self.vendor_combos[name] = combo
        self.vendor_empty.setVisible(not aliases)

    def _load_remembered(self):
        locs = self._settings.get('excluded_locations') or []
        self.remembered.setText(f'Locations left out of imports: {", ".join(locs)}.' if locs else
                                'Every location is included.')
        self.clear_remembered.setVisible(bool(locs))

    def _clear_remembered(self):
        self._settings['excluded_locations'] = []
        self._load_remembered()

    def settings(self):
        s = dict(self._settings)
        s['columns'] = {k: c.currentData() for k, c in self.col_combos.items() if c.currentData()}
        s['date_format'] = self.date_format.currentText()
        s['price_from'] = self.price_from.currentData()
        s['skip_credits'] = self.skip_credits.isChecked()
        s['catch_weight'] = self.catch_weight.isChecked()
        s['vendor_suppliers'] = {n: c.currentData() for n, c in getattr(self, 'vendor_combos', {}).items()}
        return s

    def _save(self):
        name = self.name.text().strip()
        if not name:
            QMessageBox.information(self, 'Import format', 'Give the format a name.')
            return
        settings = self.settings()
        missing = [pi.FIELD_LABELS[k] for k in pi.REQUIRED_FIELDS if not settings['columns'].get(k)]
        if not (settings['columns'].get('amount') or settings['columns'].get('unit_price')):
            missing.append('Amount or Unit price')
        if missing:
            QMessageBox.information(self, 'Import format', 'Pick a column for: ' + ', '.join(missing) + '.')
            return
        self.format_id = pi.save_format(name, settings, self.format_id)
        self.saved.emit()

    def _delete(self):
        if not self.format_id:
            return
        if QMessageBox.question(self, 'Import format', f'Delete the format “{self.name.text()}”? Past imports'
                                ' stay.') != QMessageBox.Yes:
            return
        pi.delete_format(self.format_id)
        self.format_id = None
        self.deleted.emit()


class ImportFormatsPage(QWidget):
    changed = Signal()            # prices changed (undo / re-price)
    importRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        left = QFrame()
        left.setObjectName('FmtList')
        left.setStyleSheet(f'QFrame#FmtList {{ border-right: 1px solid {kit.BORDER}; }}')
        left.setFixedWidth(300)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 20, 16, 20)
        ll.setSpacing(12)
        ll.addWidget(kit.heading('Import formats'))
        new_btn = kit.button('+ New format from a file…')
        new_btn.clicked.connect(self._new_from_file)
        ll.addWidget(new_btn)
        ll.addWidget(kit.note('A format tells the importer which column is which. Files are matched to a format by'
                              ' their headers.'))
        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setWordWrap(True)
        self.list.currentRowChanged.connect(self._show_format)
        ll.addWidget(self.list, stretch=1)
        import_btn = kit.button('Import purchases…', primary=True)
        import_btn.clicked.connect(self.importRequested.emit)
        ll.addWidget(import_btn)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(28, 20, 28, 28)
        bl.setSpacing(20)
        self.editor = FormatEditor()
        self.editor.saved.connect(self.refresh)
        self.editor.deleted.connect(self.refresh)
        bl.addWidget(self.editor)

        hist_card, hc = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading('Import history'))
        head.addWidget(kit.note('Undo removes every price an import wrote. Re-price applies today’s vendor item'
                                ' yields to it.'), stretch=1)
        hc.addLayout(head)
        self.history = QTableWidget(0, 7)
        self.history.setHorizontalHeaderLabels(['#', 'Imported', 'Purchases', 'File', 'Ingredients', 'Prices', ''])
        _style_table(self.history)
        self.history.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        hc.addWidget(self.history)
        self.history_empty = kit.note('No imports yet.')
        hc.addWidget(self.history_empty)
        bl.addWidget(hist_card)
        bl.addStretch()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(body)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(left)
        layout.addWidget(scroll, stretch=1)
        self._formats = []
        self.refresh()

    def refresh(self):
        keep = self.editor.format_id
        self._formats = pi.get_formats()
        self.list.blockSignals(True)
        self.list.clear()
        for fmt in self._formats:
            n = len([c for c in fmt['settings'].get('columns', {}).values() if c])
            uses = fmt['uses']
            item = QListWidgetItem(f'{fmt["name"]}\nCSV · {n} columns · '
                                   + (f'used {uses} time{"s" if uses != 1 else ""}' if uses else 'never used'))
            self.list.addItem(item)
        self.list.blockSignals(False)
        row = next((i for i, f in enumerate(self._formats) if f['id'] == keep), 0)
        if self._formats:
            self.list.setCurrentRow(row)
            self._show_format(row)
        self.editor.setVisible(bool(self._formats))
        self._load_history()

    def _show_format(self, row):
        if 0 <= row < len(self._formats):
            self.editor.load(self._formats[row])

    def _new_from_file(self):
        from gui.dialogs.import_purchases import FormatDialog, pick_file
        path = pick_file(self)
        if not path:
            return
        try:
            headers, rows = pi.read_csv(path)
        except Exception as exc:
            QMessageBox.warning(self, 'Import formats', f'Couldn’t read {os.path.basename(path)}:\n{exc}')
            return
        dlg = FormatDialog(headers, rows, self)
        if dlg.exec() and dlg.format_id:
            self.editor.format_id = dlg.format_id
            self.refresh()

    def _load_history(self):
        batches = pi.get_batches()
        t = self.history
        t.setRowCount(len(batches))
        for r, b in enumerate(batches):
            when = (b['imported_at'] or '')[:16]
            dates = f'{_short(b["date_from"])} – {_short(b["date_to"])}'
            vals = [str(b['id']), when, dates, b['file_name'] or '', str(b['ingredient_count']), str(b['price_count'])]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c in (4, 5):
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                t.setItem(r, c, item)
            box = QWidget()
            bl = QHBoxLayout(box)
            bl.setContentsMargins(4, 2, 4, 2)
            bl.setSpacing(6)
            if b['changed_since']:
                chip = QLabel(f'{b["changed_since"]} yield{"s" if b["changed_since"] != 1 else ""} changed since')
                chip.setStyleSheet(f'color: {kit.WARN}; background: #fff0dc; border-radius: 9px; padding: 1px 8px;'
                                   ' font-size: 12px; font-weight: 600;')
                bl.addWidget(chip)
            rep = kit.button('Re-price')
            rep.clicked.connect(lambda _=False, i=b['id']: self._reprice(i))
            undo = kit.button('Undo')
            undo.clicked.connect(lambda _=False, i=b['id']: self._undo(i))
            bl.addWidget(rep)
            bl.addWidget(undo)
            t.setCellWidget(r, 6, box)
            t.setRowHeight(r, 40)
        t.resizeColumnsToContents()
        t.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        t.setMinimumHeight(min(40 * len(batches) + 34, 400))
        t.setVisible(bool(batches))
        self.history_empty.setVisible(not batches)

    def _reprice(self, batch_id):
        written, skipped = pi.reprice_batch(batch_id)
        msg = f'Import #{batch_id} re-priced: {len(written)} ingredients.'
        if skipped:
            msg += ('\n\nLeft as they were because they’re still flagged:\n'
                    + '\n'.join(f'• {name}: {why}' for name, why in skipped[:15]))
        QMessageBox.information(self, 'Re-price import', msg)
        self._load_history()
        self.changed.emit()

    def _undo(self, batch_id):
        if QMessageBox.question(self, 'Undo import', f'Undo import #{batch_id}? Every price it wrote is removed;'
                                ' weeks it had replaced in earlier imports come back. Vendor item mappings stay.'
                                ) != QMessageBox.Yes:
            return
        pi.undo_batch(batch_id)
        self.refresh()
        self.changed.emit()


def _short(iso):
    import datetime
    try:
        d = datetime.date.fromisoformat(iso)
    except (TypeError, ValueError):
        return iso or '—'
    return f'{d:%b} {d.day}'
