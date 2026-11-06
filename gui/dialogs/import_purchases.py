'''Import purchases — the wizard from the Framework canvas
(Dialog · Import purchases): File → Locations → Map new items →
Review → Done, over utilities.purchase_import.ImportSession.

    run_import(parent) -> batch id, or None if nothing was imported
'''
import os

from PySide6.QtCore import QPointF, QSettings, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QStackedWidget, QStyledItemDelegate, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

import config
from gui.widgets import config_kit as kit
from gui.widgets.vendor_item_editor import VendorItemEditor
from utilities import purchase_import as pi
from gui.widgets.text_fit import elide

_LAST_DIR = 'imports/lastDir'
_RED = '#a3261b'
_RED_BG = '#fde8e4'
_UP_BG = '#fff0dc'
_DOWN = '#1d4f91'
_DOWN_BG = '#e4eefb'
_GREEN = '#285900'
_GREEN_BG = '#eef5e0'
_TABLE_STYLE = f'''
    QTableWidget {{ background: #ffffff; border: 1px solid {kit.BORDER}; border-radius: 8px; color: {kit.KALE};
        gridline-color: #f3ece0; selection-background-color: {kit.SELECTED}; selection-color: {kit.KALE}; }}
    QHeaderView::section {{ background: #fffaf2; color: {kit.MUTED}; border: 0;
        border-bottom: 1px solid {kit.BORDER}; padding: 6px 8px; font-size: 11px; font-weight: 600; }}
'''


def pick_file(parent):
    start = QSettings().value(_LAST_DIR, os.path.expanduser('~/Downloads'), type=str)
    path, _ = QFileDialog.getOpenFileName(parent, 'Import purchases', start, 'Purchase history (*.csv);;All files (*)')
    if path:
        QSettings().setValue(_LAST_DIR, os.path.dirname(path))
    return path


def open_session(parent, path):
    try:
        return pi.ImportSession.open(path)
    except Exception as exc:  # unreadable file, wrong encoding, not a CSV
        QMessageBox.warning(parent, 'Import purchases', f'Couldn’t read {os.path.basename(path)}:\n{exc}')
        return None


def run_import(parent, path=None):
    path = path or pick_file(parent)
    if not path:
        return None
    session = open_session(parent, path)
    if session is None:
        return None
    dlg = ImportPurchasesDialog(session, parent)
    dlg.exec()
    return dlg.batch_id


# --- small pieces ---------------------------------------------------------

def _chip(text, fg, bg):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {fg}; background: {bg}; border-radius: 9px; padding: 1px 8px;'
                      ' font-size: 12px; font-weight: 600;')
    return lbl


def _pct(change):
    if change is None:
        return '—'
    if abs(change) < 0.0005:
        return '0%'
    return f'{"+" if change > 0 else "−"}{abs(change) * 100:.1f}%'


def _item_label(item):
    return ' · '.join(filter(None, (item.get('description'), item.get('pack_size'))))


class SparklineDelegate(QStyledItemDelegate):
    '''The new weekly prices (floats in Qt.UserRole) as a small line, with
    the current price (Qt.UserRole + 1, or None) as a dashed line on the
    same scale, so a drop below today's price reads as one.'''

    def paint(self, painter, option, index):
        super().paint(painter, option, index)
        values = index.data(Qt.UserRole) or []
        if len(values) < 1:
            return
        current = index.data(Qt.UserRole + 1)
        r = option.rect.adjusted(8, 10, -8, -10)
        scale = list(values) + ([current] if current else [])
        lo, hi = min(scale), max(scale)
        span = (hi - lo) or 1.0

        def y_of(v):
            return r.center().y() if hi == lo else r.bottom() - (v - lo) / span * r.height()

        n = len(values)
        pts = [QPointF(r.left() + (r.width() * i / (n - 1) if n > 1 else r.width() / 2), y_of(v))
               for i, v in enumerate(values)]
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        if current:
            pen = QPen(QColor('#a7ad9c'), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(QPointF(r.left(), y_of(current)), QPointF(r.right(), y_of(current)))
        color = QColor(kit.KALE)
        painter.setPen(QPen(color, 2))
        if len(pts) > 1:
            painter.drawPolyline(QPolygonF(pts))
        painter.setBrush(QBrush(color))
        painter.drawEllipse(pts[-1], 2.5, 2.5)
        painter.restore()


class QueueCardDelegate(QStyledItemDelegate):
    '''A new vendor item in the Map step: name, then pack · case price ·
    cases bought, and a mark once it's handled. Fixed height, elided, so
    cards never change size.'''

    HEIGHT = 58

    def sizeHint(self, option, index):
        from PySide6.QtCore import QSize
        return QSize(option.rect.width(), self.HEIGHT)

    def paint(self, painter, option, index):
        from PySide6.QtWidgets import QStyle
        d = index.data(Qt.UserRole) or {}
        rect = option.rect.adjusted(0, 3, -2, -3)
        selected = bool(option.state & QStyle.State_Selected)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor(kit.ROMAINE if selected else kit.BORDER), 2 if selected else 1))
        painter.setBrush(QColor(kit.SELECTED if selected else '#ffffff'))
        painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 8, 8)
        inner = rect.adjusted(12, 7, -12, -7)
        mark = d.get('mark') or ''
        fm = painter.fontMetrics()
        mark_w = fm.horizontalAdvance(mark) + 10 if mark else 0
        font = painter.font()
        bold = painter.font()
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(kit.MUTED if d.get('done') else kit.KALE))
        name = elide(painter.font(), d.get('name', ''), inner.width() - mark_w)
        painter.drawText(inner.adjusted(0, 0, -mark_w, 0), Qt.AlignLeft | Qt.AlignTop, name)
        painter.setFont(font)
        painter.setPen(QColor(kit.MUTED))
        detail = elide(painter.font(), d.get('detail', ''), inner.width())
        painter.drawText(inner, Qt.AlignLeft | Qt.AlignBottom, detail)
        if mark:
            painter.setPen(QColor(_GREEN if d.get('mark_kind') == 'mapped' else kit.MUTED))
            painter.drawText(inner, Qt.AlignRight | Qt.AlignTop, mark)
        painter.restore()


class FormatDialog(QDialog):
    '''Make an import format from a file's headers (the column mapper
    from Configure › Import formats, as a dialog).'''

    def __init__(self, headers, rows, parent=None):
        super().__init__(parent)
        from gui.tabs.import_formats_page import FormatEditor
        self.setWindowTitle(f'{config.APPNAME} | New import format')
        self.editor = FormatEditor(show_delete=False)
        settings = pi.default_settings()
        settings['columns'] = pi.guess_columns(headers)
        settings['headers'] = headers
        settings['sample'] = dict(rows[0]) if rows else {}
        self.editor.load({'id': None, 'name': 'New format', 'settings': settings}, headers)
        self.editor.saved.connect(self.accept)
        self.format_id = None
        layout = QVBoxLayout(self)
        layout.addWidget(self.editor)
        self.resize(900, 760)

    def accept(self):
        self.format_id = self.editor.format_id
        super().accept()


class EditSourcesDialog(QDialog):
    '''Fix the case yield of the vendor items behind one review row.'''

    def __init__(self, session, row, parent=None):
        super().__init__(parent)
        self.session = session
        self.items = row['sources']
        self.setWindowTitle(f'{config.APPNAME} | {row["ingredient"]["Name"]} vendor items')
        self.picker = QComboBox()
        for item in self.items:
            self.picker.addItem(f'{item.get("vendor_name")} · {_item_label(item)}', item['vendor_key'])
        self.picker.currentIndexChanged.connect(self._show)
        self.editor = VendorItemEditor()
        self.editor.set_ingredients(session.ingredients)
        self.editor.changed.connect(self._remember)
        flags ='\n'.join(f'{t}: {d}' for t, d in row['flags'])
        note = kit.note(flags or 'Change a case yield and the review recalculates.')
        if flags:
            note.setStyleSheet(f'color: {_RED}; font-size: 12px;')
        save = kit.button('Save', primary=True)
        save.clicked.connect(self._save)
        cancel = kit.button('Cancel')
        cancel.clicked.connect(self.reject)
        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout = QVBoxLayout(self)
        layout.addWidget(note)
        layout.addWidget(kit.eyebrow('Vendor item'))
        layout.addWidget(self.picker)
        layout.addWidget(self.editor)
        layout.addLayout(buttons)
        self.resize(720, 420)
        self._edits = {}
        self._show()

    def _current(self):
        key = self.picker.currentData()
        return next(i for i in self.items if i['vendor_key'] == key)

    def _show(self, *_):
        item = self._current()
        avg = self._avg_case(item['vendor_key'])
        self.editor.set_item(self._edits.get(item['vendor_key'], item), avg)

    def _remember(self):
        item = dict(self._current())
        item.update(self.editor.item_values())
        self._edits[item['vendor_key']] = item

    def _avg_case(self, key):
        q = a = 0.0
        for line in self.session.included_lines():
            if line.key == key:
                q += line.quantity
                a += line.amount
        return a / q if q else None

    def _save(self):
        self._remember()
        for item in self._edits.values():
            item['status'] = 'mapped' if item.get('ingredient_id') else 'new'
            self.session.set_item(item)
        self.accept()


# --- the wizard -----------------------------------------------------------

STEPS = ('File', 'Locations', 'Map new items', 'Review', 'Done')


class ImportPurchasesDialog(QDialog):
    imported = Signal(int)

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self.session = session
        self.batch_id = None
        self.step = 0
        self.reached = 0
        self._queue = []
        self._queue_index = 0
        self._unchecked = set()
        self._review_rows = []
        self._review_filter = 'changed'
        self.setWindowTitle(f'{config.APPNAME} | Import purchases')
        self.setStyleSheet(f'QDialog {{ background: #ffffff; }} QLabel {{ color: {kit.KALE}; }}')

        # header
        self.title = QLabel('Import purchases')
        self.title.setStyleSheet(f'font-size: 20px; font-weight: 650; color: {kit.KALE};')
        self.subtitle = QLabel('')
        self.subtitle.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
        head_text = QVBoxLayout()
        head_text.setSpacing(2)
        head_text.addWidget(self.title)
        head_text.addWidget(self.subtitle)
        self.step_buttons = []
        steps_row = QHBoxLayout()
        steps_row.setSpacing(4)
        for i, label in enumerate(STEPS):
            btn = QPushButton(f'{i + 1}  {label}')
            btn.setCursor(Qt.PointingHandCursor)
            btn.setAutoDefault(False)
            btn.clicked.connect(lambda _=False, n=i: self._go(n))
            self.step_buttons.append(btn)
            steps_row.addWidget(btn)
        header = QHBoxLayout()
        header.setContentsMargins(20, 14, 20, 14)
        header.addLayout(head_text)
        header.addStretch()
        header.addLayout(steps_row)
        header_frame = QFrame()
        header_frame.setObjectName('ImpHead')
        header_frame.setStyleSheet(f'QFrame#ImpHead {{ border-bottom: 1px solid {kit.BORDER}; }}')
        header_frame.setLayout(header)

        # pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._scroll(self._build_file_page()))
        self.pages.addWidget(self._build_locations_page())
        self.pages.addWidget(self._build_map_page())
        self.pages.addWidget(self._build_review_page())
        self.pages.addWidget(self._build_done_page())

        # footer
        self.footer_note = kit.note('')
        self.back_btn = kit.button('Back')
        self.back_btn.clicked.connect(lambda: self._go(self.step - 1))
        self.next_btn = kit.button('Next', primary=True)
        self.next_btn.clicked.connect(self._next)
        footer = QHBoxLayout()
        footer.setContentsMargins(20, 10, 20, 10)
        footer.addWidget(self.footer_note, stretch=1)
        footer.addWidget(self.back_btn)
        footer.addWidget(self.next_btn)
        footer_frame = QFrame()
        footer_frame.setObjectName('ImpFoot')
        footer_frame.setStyleSheet(f'QFrame#ImpFoot {{ background: {kit.BG}; border-top: 1px solid {kit.BORDER}; }}')
        footer_frame.setLayout(footer)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(header_frame)
        layout.addWidget(self.pages, stretch=1)
        layout.addWidget(footer_frame)
        self.resize(1240, 860)

        self._load_file_page()
        self._go(0)

    @staticmethod
    def _scroll(widget):
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setWidget(widget)
        return area

    # --- navigation ----------------------------------------------------

    def _go(self, n):
        if n < 0 or n > self.reached or (self.batch_id is not None and n < 4) or \
                (self.batch_id is None and n == 4):
            return
        self.step = n
        if n == 1:
            self._load_locations_page()
        elif n == 2:
            self._load_map_page()
        elif n == 3:
            self._load_review_page()
        self.pages.setCurrentIndex(n)
        self._sync_chrome()

    def _next(self):
        if self.step == 4:
            self.accept()
            return
        if self.step == 3:
            self._apply()
            return
        if self.step == 0 and not self._file_ready():
            return
        self.reached = max(self.reached, self.step + 1)
        self._go(self.step + 1)

    def _sync_chrome(self):
        for i, btn in enumerate(self.step_buttons):
            current, past = i == self.step, i < self.step or (self.batch_id is not None and i < 4)
            mark = '✓' if past and not current else str(i + 1)
            btn.setText(f'{mark}  {STEPS[i]}')
            btn.setEnabled(i <= self.reached and (self.batch_id is None) == (i < 4))
            btn.setStyleSheet(
                'QPushButton { height: 30px; padding: 0 10px; border: 0; border-radius: 8px;'
                + (f' background: {kit.SELECTED}; color: {kit.KALE}; font-weight: 600; }}' if current
                   else f' background: transparent; color: {kit.MUTED}; }}')
                + ' QPushButton:disabled { color: #b7bcae; }')
        self.back_btn.setVisible(0 < self.step < 4)
        start, end = self.session.date_range
        dates = f' · {start:%b} {start.day} – {end:%b} {end.day}, {end.year}' if start else ''
        self.subtitle.setText(f'{self.session.file_name}{dates}')
        labels = {0: 'Next: Locations', 1: 'Next: Map new items', 2: 'Next: Review prices', 4: 'Close'}
        if self.step == 3:
            n = len(self._apply_ids())
            self.next_btn.setText(f'Apply {n} price{"s" if n != 1 else ""}')
            self.next_btn.setEnabled(n > 0)
        else:
            self.next_btn.setText(labels[self.step])
            self.next_btn.setEnabled(self.step != 0 or self.session.fmt is not None)
        self.footer_note.setText(self._footer_text())

    def _footer_text(self):
        s = self.session
        if self.step == 0:
            if s.fmt is None:
                return 'Pick an import format, or make one from this file.'
            c = s.counts()
            return f'{c["total"]} vendor items in this file. {c["new"]} are new and need mapping.'
        if self.step == 1:
            n = len(s.locations()) - len(s.excluded_locations)
            return f'{n} of {len(s.locations())} locations blended into each price.'
        if self.step == 2:
            left = sum(1 for q in self._queue if q['vendor_key'] not in s.pending)
            return (f'{left} new item{"s" if left != 1 else ""} left. Items you skip are left out this time and'
                    ' asked about again next import.')
        if self.step == 3:
            return (f'{len(self._apply_ids())} ingredients get prices. Flagged rows start unchecked;'
                    ' double-click a row to fix a vendor item’s yield.')
        return f'Import saved as #{self.batch_id}.'

    # --- 1 · file ------------------------------------------------------

    def _build_file_page(self):
        page = QWidget()
        # Scoped to the page: an unscoped rule reaches the radio buttons
        # and Qt then draws them without their checked indicator.
        page.setObjectName('ImpFilePage')
        page.setStyleSheet('QWidget#ImpFilePage { background: #ffffff; }')
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(16)

        top = QHBoxLayout()
        top.setSpacing(16)
        file_card, fc = kit.card()
        fc.addWidget(kit.subheading('File'))
        row = QHBoxLayout()
        self.file_name = QLabel('')
        self.file_name.setStyleSheet('font-weight: 600;')
        self.file_info = kit.note('')
        names = QVBoxLayout()
        names.addWidget(self.file_name)
        names.addWidget(self.file_info)
        another = kit.button('Choose another…')
        another.clicked.connect(self._choose_another)
        row.addLayout(names, stretch=1)
        row.addWidget(another)
        fc.addLayout(row)
        fc.addWidget(kit.eyebrow('Import format'))
        self.format_combo = QComboBox()
        self.format_combo.setMinimumHeight(32)
        self.format_combo.activated.connect(self._on_format_chosen)
        fc.addWidget(self.format_combo)
        self.format_note = QLabel('')
        self.format_note.setWordWrap(True)
        fc.addWidget(self.format_note)
        fc.addStretch()

        stats_card, sc = kit.card()
        sc.addWidget(kit.subheading('What’s in the file'))
        self.stats_grid = QGridLayout()
        self.stats_grid.setHorizontalSpacing(24)
        self.stats_grid.setVerticalSpacing(10)
        sc.addLayout(self.stats_grid)
        self.overlap_note = QLabel('')
        self.overlap_note.setWordWrap(True)
        self.overlap_note.setStyleSheet(f'color: {kit.WARN}; background: {_UP_BG}; border-radius: 6px; padding: 6px 10px;')
        sc.addWidget(self.overlap_note)
        sc.addStretch()
        top.addWidget(file_card, 1)
        top.addWidget(stats_card, 1)
        layout.addLayout(top)

        basis_card, bc = kit.card()
        bc.addWidget(kit.subheading('Price basis'))
        self.basis_weekly = QRadioButton('Weekly weighted average')
        self.basis_latest = QRadioButton('Latest purchase')
        group = QButtonGroup(self)
        group.addButton(self.basis_weekly)
        group.addButton(self.basis_latest)
        self.basis_weekly.toggled.connect(self._on_basis)
        self.basis_weekly_note = kit.note('')
        bc.addWidget(self.basis_weekly)
        bc.addWidget(self.basis_weekly_note)
        bc.addWidget(self.basis_latest)
        bc.addWidget(kit.note('Each item’s most recent purchase'))
        layout.addWidget(basis_card)

        layout.addStretch()
        return page

    def _load_file_page(self):
        s = self.session
        self.file_name.setText(s.file_name)
        size = os.path.getsize(s.path) if os.path.exists(s.path) else 0
        self.file_info.setText(f'{len(s.rows):,} lines · {size / 1_000_000:.1f} MB')
        self.format_combo.clear()
        formats = pi.get_formats()
        for fmt in formats:
            self.format_combo.addItem(fmt['name'], fmt['id'])
        self.format_combo.addItem('New format from this file…', 'new')
        if s.fmt:
            self.format_combo.setCurrentIndex(max(self.format_combo.findData(s.fmt['id']), 0))
            self.format_note.setText('Recognized by its column headers.')
            self.format_note.setStyleSheet(f'color: {_GREEN}; font-size: 12px;')
        else:
            self.format_combo.setCurrentIndex(-1)
            self.format_note.setText('No saved format matches these columns. Make one from this file.')
            self.format_note.setStyleSheet(f'color: {kit.WARN}; font-size: 12px;')
        self._load_file_details()

    def _load_file_details(self):
        s = self.session
        while self.stats_grid.count():
            w = self.stats_grid.takeAt(0).widget()
            if w:
                w.deleteLater()
        if s.fmt is None:
            self.overlap_note.hide()
            self._sync_chrome() if hasattr(self, 'next_btn') else None
            return
        c = s.counts()
        vendors = s.vendors()
        cells = [
            ('Vendors', str(len(vendors)), ', '.join(v.split(' ')[0] for v in vendors[:4])),
            ('Locations', str(len(s.locations())), 'blended into one price'),
            ('Vendor items', str(c['total']), f'{c["mapped"]} mapped · {c["ignored"]} ignored · {c["new"]} new'),
            ('Lines skipped', str(s.stats.get('credits', 0) + s.stats.get('unreadable', 0)),
             f'{s.stats.get("credits", 0)} credits · {s.stats.get("unreadable", 0)} unreadable'),
        ]
        for i, (label, value, note) in enumerate(cells):
            box = QWidget()
            bl = QVBoxLayout(box)
            bl.setContentsMargins(0, 0, 0, 0)
            bl.setSpacing(0)
            bl.addWidget(kit.note(label))
            v = QLabel(value)
            v.setStyleSheet('font-size: 20px; font-weight: 650;')
            bl.addWidget(v)
            bl.addWidget(kit.note(note))
            self.stats_grid.addWidget(box, i // 2, i % 2)
        overlap = s.overlapping_batches()
        if overlap:
            ids = ', '.join(f'#{b["id"]}' for b in overlap)
            self.overlap_note.setText(f'Overlaps import {ids}. This import’s prices replace those weeks.')
            self.overlap_note.show()
        else:
            self.overlap_note.hide()
        weeks = sorted({pi.week_start(l.date) for l in s.lines})
        week_text = ', '.join(f'{w:%b} {w.day}' for w in weeks)
        self.basis_weekly_note.setText(f"{len(weeks)} week{'s' if len(weeks) != 1 else ''}: {week_text}")
        (self.basis_latest if s.basis == 'latest' else self.basis_weekly).setChecked(True)
        if hasattr(self, 'next_btn'):
            self._sync_chrome()

    def _file_ready(self):
        if self.session.fmt is None:
            QMessageBox.information(self, 'Import purchases', 'Pick an import format first.')
            return False
        if not self.session.lines:
            QMessageBox.information(self, 'Import purchases', 'No purchase lines could be read with this format.'
                                    ' Check its columns and date format.')
            return False
        return True

    def _choose_another(self):
        path = pick_file(self)
        if not path:
            return
        session = open_session(self, path)
        if session is None:
            return
        self.session = session
        self.reached = 0
        self._queue = []
        self._unchecked = set()
        self._load_file_page()
        self._go(0)

    def _on_format_chosen(self, index):
        data = self.format_combo.itemData(index)
        if data == 'new':
            dlg = FormatDialog(self.session.headers, self.session.rows, self)
            if dlg.exec() != QDialog.Accepted or not dlg.format_id:
                self._load_file_page()
                return
            data = dlg.format_id
        fmt = next((f for f in pi.get_formats() if f['id'] == data), None)
        if fmt is None:
            return
        missing = pi.missing_columns(fmt['settings'], self.session.headers)
        if missing:
            QMessageBox.warning(self, 'Import purchases', f'“{fmt["name"]}” needs columns this file doesn’t have: '
                                + ', '.join(pi.FIELD_LABELS.get(m, m) for m in missing) + '.')
        self.session.use_format(fmt)
        self.reached = 0
        self._queue = []
        self._load_file_page()

    def _on_basis(self, *_):
        self.session.basis = 'weekly' if self.basis_weekly.isChecked() else 'latest'

    # --- 2 · locations -------------------------------------------------

    def _build_locations_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(20)

        left, ll = kit.card()
        head = QHBoxLayout()
        head.addWidget(kit.subheading('Locations'))
        self.loc_count = kit.note('')
        head.addWidget(self.loc_count, stretch=1)
        select_all = kit.button('Select all')
        select_all.clicked.connect(self._select_all_locations)
        head.addWidget(select_all)
        ll.addLayout(head)
        self.loc_list = QListWidget()
        self.loc_list.setStyleSheet('QListWidget { border: 0; } QListWidget::item { padding: 5px 2px; }')
        self.loc_list.itemChanged.connect(self._on_location_toggled)
        ll.addWidget(self.loc_list, stretch=1)
        ll.addWidget(kit.note('Prices blend the checked locations'))
        left.setMaximumWidth(420)

        right, rl = kit.card()
        self.swing_title = kit.subheading('')
        self.swing_hint = kit.note('')
        rl.addWidget(self.swing_title)
        rl.addWidget(self.swing_hint)
        self.swing_table = QTableWidget(0, 6)
        self.swing_table.setHorizontalHeaderLabels(['Ingredient', 'Vendor item', 'Low – high case', 'All', 'Checked', 'Swing'])
        self._style_table(self.swing_table)
        self.swing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        rl.addWidget(self.swing_table, stretch=1)
        self.swing_empty = QLabel('')
        self.swing_empty.setWordWrap(True)
        self.swing_empty.setAlignment(Qt.AlignCenter)
        self.swing_empty.setStyleSheet(f'color: {kit.MUTED}; font-size: 13px; padding: 40px 20px;')
        rl.addWidget(self.swing_empty, stretch=1)
        self.swing_note = kit.note('')
        rl.addWidget(self.swing_note)

        layout.addWidget(left, 2)
        layout.addWidget(right, 3)
        return page

    def _style_table(self, table):
        table.setStyleSheet(_TABLE_STYLE)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)

    def _load_locations_page(self):
        s = self.session
        self.loc_list.blockSignals(True)
        self.loc_list.clear()
        for name, n in s.locations():
            item = QListWidgetItem(f'{name}    {n:,} lines')
            item.setData(Qt.UserRole, name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked if name in s.excluded_locations else Qt.Checked)
            self.loc_list.addItem(item)
        self.loc_list.blockSignals(False)
        self._refresh_swings()

    def _on_location_toggled(self, item):
        name = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.session.excluded_locations.discard(name)
        else:
            self.session.excluded_locations.add(name)
        self._refresh_swings()
        self._sync_chrome()

    def _select_all_locations(self):
        self.session.excluded_locations.clear()
        self._load_locations_page()
        self._sync_chrome()

    def _refresh_swings(self):
        s = self.session
        total = len(s.locations())
        ex = set(s.excluded_locations)
        self.loc_count.setText(f'{total - len(ex)} of {total} included')
        rows = s.location_swings(ex)
        cutoff = f'{pi.SWING_MIN * 100:.0f}%'
        self.swing_title.setText(f'Items that move {cutoff} or more')
        self.swing_hint.setText(f'Compared with all {total} locations')
        if not ex:
            self.swing_empty.setText('Uncheck a location to see what it changes')
        elif not rows:
            self.swing_empty.setText(f'No item moves {cutoff} or more')
        self.swing_table.setVisible(bool(rows))
        self.swing_empty.setVisible(not rows)
        self.swing_table.setHorizontalHeaderLabels(
            ['Ingredient', 'Vendor item', 'Low – high case', f'All {total}', 'Checked', 'Swing'])
        self.swing_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            rng = pi.money(row['low']) if abs(row['high'] - row['low']) < 0.005 else \
                f'{pi.money(row["low"])} – {pi.money(row["high"])}'
            vals = [row['ingredient'], row['item'], rng, pi.money(row['all']),
                    'not bought' if row['selected'] is None else pi.money(row['selected']), _pct(row['change'])]
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if c >= 2:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 5 and row['change'] is not None and abs(row['change']) >= 0.03:
                    cell.setForeground(QColor(kit.WARN if row['change'] > 0 else _DOWN))
                    cell.setBackground(QColor(_UP_BG if row['change'] > 0 else _DOWN_BG))
                if c == 0 and not row['mapped']:
                    cell.setForeground(QColor(kit.MUTED))
                self.swing_table.setItem(r, c, cell)
        self.swing_table.resizeColumnsToContents()
        self.swing_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.swing_note.setText('')

    # --- 3 · map new items ---------------------------------------------

    def _build_map_page(self):
        page = QWidget()
        outer = QHBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = QFrame()
        left.setObjectName('MapQueue')
        left.setStyleSheet(f'QFrame#MapQueue {{ background: {kit.BG}; border-right: 1px solid {kit.BORDER}; }}')
        left.setFixedWidth(360)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(16, 16, 16, 16)
        head = QHBoxLayout()
        head.addWidget(kit.subheading('New vendor items'))
        self.queue_count = kit.note('')
        head.addWidget(self.queue_count, stretch=1)
        ll.addLayout(head)
        ll.addWidget(kit.note('New items only. Each is mapped once.'))
        self.queue_list = QListWidget()
        self.queue_list.setStyleSheet('QListWidget { border: 0; background: transparent; outline: 0; }')
        self.queue_list.setItemDelegate(QueueCardDelegate(self.queue_list))
        self.queue_list.setUniformItemSizes(True)
        self.queue_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.queue_list.currentRowChanged.connect(self._show_queue_item)
        ll.addWidget(self.queue_list, stretch=1)
        ignore_rest = kit.button('Ignore all left…')
        ignore_rest.clicked.connect(self._ignore_rest)
        ll.addWidget(ignore_rest)

        right = QWidget()
        right.setObjectName('MapRight')
        right.setStyleSheet('QWidget#MapRight { background: #ffffff; }')
        rl = QVBoxLayout(right)
        rl.setContentsMargins(24, 18, 24, 18)
        rl.setSpacing(12)
        self.map_empty = kit.note('Nothing new: every vendor item in this file is mapped or ignored.')
        rl.addWidget(self.map_empty)
        self.map_detail = QWidget()
        dl = QVBoxLayout(self.map_detail)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(12)
        top = QHBoxLayout()
        names = QVBoxLayout()
        names.setSpacing(2)
        self.map_vendor = kit.note('')
        self.map_desc = QLabel('')
        self.map_desc.setWordWrap(True)
        self.map_desc.setStyleSheet('font-size: 19px; font-weight: 650;')
        self.map_meta = kit.note('')
        names.addWidget(self.map_vendor)
        names.addWidget(self.map_desc)
        names.addWidget(self.map_meta)
        top.addLayout(names, stretch=1)
        self.map_price = QLabel('')
        self.map_price.setStyleSheet('font-size: 13px;')
        self.map_price.setAlignment(Qt.AlignRight | Qt.AlignTop)
        top.addWidget(self.map_price)
        dl.addLayout(top)
        self.map_why = QLabel('')
        self.map_why.setWordWrap(True)
        self.map_why.setStyleSheet(f'color: {_GREEN}; background: {_GREEN_BG}; border-radius: 8px; padding: 8px 12px;')
        dl.addWidget(self.map_why)
        card, cl = kit.card()
        self.map_editor = VendorItemEditor()
        self.map_editor.changed.connect(self._refresh_siblings)
        cl.addWidget(self.map_editor)
        dl.addWidget(card)
        self.sib_title = kit.subheading('')
        dl.addWidget(self.sib_title)
        self.sib_table = QTableWidget(0, 4)
        self.sib_table.setHorizontalHeaderLabels(['Vendor item', 'Pack', 'Case yields', 'Per portion'])
        self._style_table(self.sib_table)
        self.sib_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.sib_table.setMaximumHeight(150)
        dl.addWidget(self.sib_table)
        dl.addStretch()
        buttons = QHBoxLayout()
        ignore = kit.button('Ignore this item')
        ignore.clicked.connect(lambda: self._resolve('ignored'))
        skip = kit.button('Skip for now')
        skip.clicked.connect(lambda: self._resolve('new'))
        save = kit.button('Save mapping && next', primary=True)
        save.clicked.connect(lambda: self._resolve('mapped'))
        buttons.addWidget(ignore)
        buttons.addWidget(skip)
        buttons.addStretch()
        buttons.addWidget(save)
        dl.addLayout(buttons)
        rl.addWidget(self.map_detail, stretch=1)

        outer.addWidget(left)
        outer.addWidget(self._scroll(right), stretch=1)
        return page

    def _load_map_page(self):
        s = self.session
        if not self._queue:
            self._queue = s.new_items()
        self.map_editor.set_ingredients(s.ingredients)
        self.queue_list.blockSignals(True)
        self.queue_list.clear()
        for item in self._queue:
            li = QListWidgetItem()
            li.setData(Qt.UserRole, self._queue_card(item))
            li.setToolTip(f'{item.get("vendor_name")} · {item.get("description")}')
            self.queue_list.addItem(li)
        self.queue_list.blockSignals(False)
        has = bool(self._queue)
        self.map_empty.setVisible(not has)
        self.map_detail.setVisible(has)
        if has:
            self.queue_list.setCurrentRow(min(self._queue_index, len(self._queue) - 1))
            self._show_queue_item(self.queue_list.currentRow())
        self._update_queue_count()

    def _queue_card(self, item):
        '''What a queue card shows: name; pack · avg case price · cases bought;
        a mark once handled in this import.'''
        p = self.session.pending.get(item['vendor_key'])
        mark, kind = '', ''
        if p and p.get('status') == 'mapped':
            mark, kind = '✓', 'mapped'
        elif p and p.get('status') == 'ignored':
            mark, kind = 'Ignored', 'ignored'
        elif p:
            mark, kind = 'Skipped', 'skipped'
        qty = item.get('_qty') or 0
        detail = ' · '.join(filter(None, (item.get('pack_size'), f'{pi.money(item.get("_avg_case"))} a case',
                                          f'{qty:,.4g} bought')))
        return {'name': item.get('description') or '', 'detail': detail, 'mark': mark, 'mark_kind': kind,
                'done': bool(p)}

    def _queue_text(self, item):
        p = self.session.pending.get(item['vendor_key'])
        if p and p.get('status') == 'mapped':
            name = self.session.ingredients_by_id.get(p.get('ingredient_id'), {}).get('Name', '?')
            state = f'mapped → {name}'
        elif p and p.get('status') == 'ignored':
            state = 'ignored'
        elif p:
            state = 'skipped'
        else:
            sg = self.session.suggestion(item)
            state = (f'new → {self.session.ingredients_by_id[sg["ingredient_id"]]["Name"]}?' if sg
                     else 'new · no match')
        return (f'{item.get("vendor_name")}  ·  {state}\n{item.get("description")}\n'
                f'{item.get("pack_size") or "no pack size"} · {pi.money(item.get("_amount"))} spent')

    def _update_queue_count(self):
        done = sum(1 for q in self._queue if q['vendor_key'] in self.session.pending)
        self.queue_count.setText(f'{done} of {len(self._queue)} done')

    def _show_queue_item(self, row):
        if row < 0 or row >= len(self._queue):
            return
        self._queue_index = row
        item = self._queue[row]
        s = self.session
        pending = s.pending.get(item['vendor_key'])
        shown = dict(item)
        why = ''
        if pending:
            shown.update(pending)
        else:
            sg = s.suggestion(item)
            if sg:
                why = sg.get('reason', '')
                shown.update({k: v for k, v in sg.items() if k != 'reason' and v is not None})
        code = item.get('item_code') or 'no item code'
        self.map_vendor.setText(f'{item.get("vendor_name")} · {code}')
        self.map_desc.setText(item.get('description') or '')
        self.map_meta.setText(f'Pack {item.get("pack_size") or "—"} · inventory item “{item.get("inventory_item") or "—"}”')
        self.map_price.setText(f'Avg case <b>{pi.money(item.get("_avg_case"))}</b><br>'
                               f'Bought {item.get("_qty", 0):g} · {item.get("_locations", 0)} locations')
        self.map_why.setText(why)
        self.map_why.setVisible(bool(why))
        self.map_editor.set_item(shown, item.get('_avg_case'))
        self._refresh_siblings()

    def _refresh_siblings(self):
        s = self.session
        ing_id = self.map_editor.ingredient_id()
        cur_key = self._queue[self._queue_index]['vendor_key'] if self._queue else None
        rows = []
        if ing_id:
            ing = s.ingredients_by_id.get(ing_id, {})
            avg = s.avg_case_prices()
            items = dict(s.known)
            items.update(s.pending)
            for key, v in items.items():
                if key == cur_key or v.get('status') != 'mapped' or v.get('ingredient_id') != ing_id:
                    continue
                ppc, _ = pi.portions_per_case(v, ing.get('Weight'))
                price = avg.get(key) or v.get('last_case_price')
                rows.append((_item_label(v), v.get('pack_size') or '', pi.yield_short(v),
                             pi.money(price / ppc, 3) if ppc and price else '—'))
        name = s.ingredients_by_id.get(ing_id, {}).get('Name') if ing_id else None
        self.sib_title.setText(f'Already mapped to {name}' if rows else '')
        self.sib_title.setVisible(bool(rows))
        self.sib_table.setVisible(bool(rows))
        cost = self.map_editor.per_portion_cost()
        if rows:
            rows.append(('This item', self._queue[self._queue_index].get('pack_size') or '',
                         pi.yield_short(self.map_editor.item_values()), pi.money(cost, 3)))
        self.sib_table.setRowCount(len(rows))
        for r, vals in enumerate(rows):
            for c, v in enumerate(vals):
                cell = QTableWidgetItem(v)
                if c == 3:
                    cell.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if r == len(rows) - 1:
                    cell.setBackground(QColor(kit.SELECTED))
                self.sib_table.setItem(r, c, cell)

    def _resolve(self, status):
        if not self._queue:
            return
        item = dict(self._queue[self._queue_index])
        if status == 'mapped':
            values = self.map_editor.item_values()
            if not values['ingredient_id']:
                QMessageBox.information(self, 'Import purchases', 'Pick the ingredient this item is.')
                return
            ing = self.session.ingredients_by_id.get(values['ingredient_id'], {})
            ppc, why = pi.portions_per_case(values, ing.get('Weight'))
            if ppc is None:
                QMessageBox.information(self, 'Import purchases', f'Can’t work out portions per case: {why}.')
                return
            item.update(values)
        item['status'] = status
        self.session.set_item(item)
        self.queue_list.item(self._queue_index).setData(Qt.UserRole, self._queue_card(item))
        self._update_queue_count()
        nxt = next((i for i in list(range(self._queue_index + 1, len(self._queue))) + list(range(self._queue_index))
                    if self._queue[i]['vendor_key'] not in self.session.pending), None)
        if nxt is not None:
            self.queue_list.setCurrentRow(nxt)
        self._sync_chrome()

    def _ignore_rest(self):
        left = [q for q in self._queue if q['vendor_key'] not in self.session.pending]
        if not left:
            return
        if QMessageBox.question(self, 'Import purchases',
                                f'Ignore {len(left)} unmapped items? You can map them later in Vendor items.') != QMessageBox.Yes:
            return
        for q in left:
            item = dict(q, status='ignored')
            self.session.set_item(item)
        self._load_map_page()
        self._sync_chrome()

    # --- 4 · review ----------------------------------------------------

    def _build_review_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 18, 28, 18)
        layout.setSpacing(12)
        bar = QHBoxLayout()
        self.filter_buttons = {}
        group = QButtonGroup(self)
        for key, label in (('all', 'All'), ('changed', 'Changed'), ('flagged', 'Flagged'), ('first', 'No current price')):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                f'QPushButton {{ height: 28px; padding: 0 12px; border-radius: 14px; border: 1px solid {kit.BORDER};'
                f' background: #ffffff; color: {kit.KALE}; }}'
                f' QPushButton:checked {{ background: {kit.ROMAINE}; border-color: {kit.ROMAINE}; color: #ffffff;'
                ' font-weight: 600; }')
            btn.clicked.connect(lambda _=False, k=key: self._set_review_filter(k))
            group.addButton(btn)
            self.filter_buttons[key] = btn
            bar.addWidget(btn)
        bar.addStretch()
        self.review_help = kit.note('Only checked ingredients are updated')
        self.review_summary = QLabel('')
        self.review_summary.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
        bar.addWidget(self.review_summary)
        layout.addLayout(bar)
        layout.addWidget(self.review_help)
        self.review_table = QTableWidget(0, 8)
        self.review_table.setHorizontalHeaderLabels(
            ['Apply', 'Ingredient', 'From', 'Current', 'New, by week', 'Latest week', 'vs current', 'Check'])
        tips = {0: 'Checked: the new prices are written when you apply. Unchecked: the ingredient keeps its'
                   ' current price.',
                4: 'Solid line: the new weekly prices. Dashed line: the current price.',
                6: 'Latest week against the current price.'}
        for col, tip in tips.items():
            self.review_table.horizontalHeaderItem(col).setToolTip(tip)
        self._style_table(self.review_table)
        self.review_table.setItemDelegateForColumn(4, SparklineDelegate(self.review_table))
        self.review_table.itemChanged.connect(self._on_review_check)
        self.review_table.cellDoubleClicked.connect(self._edit_review_row)
        header = self.review_table.horizontalHeader()
        header.setSectionResizeMode(7, QHeaderView.Stretch)
        layout.addWidget(self.review_table, stretch=1)
        self.unpriced_note = QLabel('')
        self.unpriced_note.setWordWrap(True)
        self.unpriced_note.setStyleSheet(f'color: {kit.WARN}; font-size: 12px;')
        layout.addWidget(self.unpriced_note)
        return page

    def _load_review_page(self, keep_checks=False):
        rows = self.session.review()
        if not keep_checks:
            self._unchecked = {r['ingredient']['Id'] for r in rows if r['flags']}
        else:
            for r in rows:
                if r['flags'] and r['ingredient']['Id'] not in {x['ingredient']['Id'] for x in self._review_rows}:
                    self._unchecked.add(r['ingredient']['Id'])
        self._review_rows = rows
        if not any(self._matches(r, self._review_filter) for r in rows):
            self._review_filter = 'all'
        self.filter_buttons[self._review_filter].setChecked(True)
        for key, btn in self.filter_buttons.items():
            n = sum(1 for r in rows if self._matches(r, key))
            btn.setText({'all': 'All', 'changed': 'Changed', 'flagged': 'Flagged', 'first': 'No current price'}[key]
                        + f'  {n}')
        unpriced = self.session.unpriced()
        if unpriced:
            names = '; '.join(f'{_item_label(i)} ({why})' for i, why in unpriced[:6])
            more = f' and {len(unpriced) - 6} more' if len(unpriced) > 6 else ''
            self.unpriced_note.setText(f'{len(unpriced)} mapped item{"s" if len(unpriced) != 1 else ""} can’t be'
                                       f' priced yet: {names}{more}.')
        else:
            self.unpriced_note.setText('')
        self._fill_review_table()

    @staticmethod
    def _matches(row, key):
        if key == 'all':
            return True
        if key == 'flagged':
            return bool(row['flags'])
        if key == 'first':
            return row['first']
        return not row['first'] and row['change'] is not None and abs(row['change']) >= pi.UNCHANGED_BELOW

    def _set_review_filter(self, key):
        self._review_filter = key
        self._fill_review_table()

    def _fill_review_table(self):
        rows = [r for r in self._review_rows if self._matches(r, self._review_filter)]
        self._shown_rows = rows
        t = self.review_table
        t.blockSignals(True)
        t.setRowCount(len(rows))
        basis = self.session.basis
        self.review_table.horizontalHeaderItem(4).setText('New, by week' if basis == 'weekly' else 'New')
        self.review_table.horizontalHeaderItem(5).setText('Latest week' if basis == 'weekly' else 'New price')
        for r, row in enumerate(rows):
            ing = row['ingredient']
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            check.setCheckState(Qt.Unchecked if ing['Id'] in self._unchecked else Qt.Checked)
            check.setData(Qt.UserRole, ing['Id'])
            t.setItem(r, 0, check)
            unit = (ing.get('Unit') or '').strip()
            grams = ing.get('Weight')
            t.setItem(r, 1, QTableWidgetItem(f'{ing["Name"]}\n{unit}{f" · {grams:g} g" if grams else ""}'))
            src = row['sources']
            src_text = (f'{src[0].get("vendor_name", "").split(" ")[0]} · {_item_label(src[0])}' if len(src) == 1
                        else f'{len(src)} vendor items')
            t.setItem(r, 2, QTableWidgetItem(src_text))
            cur = QTableWidgetItem('—' if row['first'] else pi.money(row['current'], 3))
            cur.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(r, 3, cur)
            spark = QTableWidgetItem('')
            spark.setData(Qt.UserRole, [p['per_portion'] for p in row['points']])
            spark.setData(Qt.UserRole + 1, None if row['first'] else row['current'])
            spark.setToolTip('\n'.join(f'{p["label"]}: {pi.money(p["per_portion"], 3)}' for p in row['points']))
            t.setItem(r, 4, spark)
            latest = QTableWidgetItem(pi.money(row['latest'], 3))
            latest.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            f = latest.font()
            f.setBold(True)
            latest.setFont(f)
            t.setItem(r, 5, latest)
            if row['first']:
                change = QTableWidgetItem('new')
                change.setToolTip('First price')
                change.setForeground(QColor(kit.MUTED))
            else:
                c = row['change'] or 0
                arrow = '▲' if c > 0 else ('▼' if c < 0 else '')
                change = QTableWidgetItem(f'{arrow} {abs(c) * 100:.1f}%'.strip() if abs(c) >= 0.0005 else '0%')
                change.setForeground(QColor(kit.KALE if abs(c) >= pi.UNCHANGED_BELOW else kit.MUTED))
            change.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            t.setItem(r, 6, change)
            flag = QTableWidgetItem('\n'.join(f'{a}: {b}' for a, b in row['flags']))
            if row['flags']:
                flag.setBackground(QColor(_UP_BG))
            flag.setToolTip(flag.text())
            flag.setForeground(QColor(kit.WARN))
            t.setItem(r, 7, flag)
        t.blockSignals(False)
        t.resizeColumnsToContents()
        t.setColumnWidth(4, 120)
        t.setColumnWidth(2, min(t.columnWidth(2), 260))
        t.horizontalHeader().setSectionResizeMode(7, QHeaderView.Stretch)
        t.resizeRowsToContents()
        n_hidden = len(self._review_rows) - len(rows)
        self.review_summary.setText(
            f'{"Weekly weighted average" if basis == "weekly" else "Latest purchase"} · '
            f'{len(self.session.locations()) - len(self.session.excluded_locations)} locations'
            + (f' · {n_hidden} more not shown by this filter' if n_hidden else ''))
        self._sync_chrome()

    def _on_review_check(self, item):
        if item.column() != 0:
            return
        ing_id = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self._unchecked.discard(ing_id)
        else:
            self._unchecked.add(ing_id)
        self._sync_chrome()

    def _edit_review_row(self, r, _c):
        if r >= len(self._shown_rows):
            return
        row = self._shown_rows[r]
        if EditSourcesDialog(self.session, row, self).exec() == QDialog.Accepted:
            ing_id = row['ingredient']['Id']
            self._load_review_page(keep_checks=True)
            still = next((x for x in self._review_rows if x['ingredient']['Id'] == ing_id), None)
            if still is not None and not still['flags']:
                self._unchecked.discard(ing_id)
                self._fill_review_table()

    def _apply_ids(self):
        return [r['ingredient']['Id'] for r in self._review_rows if r['ingredient']['Id'] not in self._unchecked]

    def _apply(self):
        ids = self._apply_ids()
        try:
            self.batch_id = self.session.apply(ids)
        except Exception as exc:
            QMessageBox.critical(self, 'Import purchases', f'The import didn’t finish; nothing was changed.\n\n{exc}')
            return
        self._applied = ids
        self._held = [r['ingredient']['Name'] for r in self._review_rows if r['ingredient']['Id'] in self._unchecked]
        self.reached = 4
        self._load_done_page()
        self._go(4)
        self.imported.emit(self.batch_id)

    # --- 5 · done ------------------------------------------------------

    def _build_done_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 60, 28, 28)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.done_title = QLabel('Prices updated')
        self.done_title.setStyleSheet('font-size: 22px; font-weight: 650;')
        self.done_title.setAlignment(Qt.AlignCenter)
        self.done_body = QLabel('')
        self.done_body.setWordWrap(True)
        self.done_body.setAlignment(Qt.AlignCenter)
        self.done_body.setStyleSheet(f'color: {kit.MUTED}; font-size: 13px;')
        self.done_hint = QLabel('Undo it anytime in Import formats & history')
        self.done_hint.setWordWrap(True)
        self.done_hint.setAlignment(Qt.AlignCenter)
        self.done_hint.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
        undo = kit.button('Undo this import')
        undo.clicked.connect(self._undo)
        self.undo_btn = undo
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(undo)
        row.addStretch()
        column = QWidget()
        column.setMaximumWidth(640)
        cl = QVBoxLayout(column)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(14)
        cl.addWidget(self.done_title)
        cl.addWidget(self.done_body)
        centre = QHBoxLayout()
        centre.addStretch()
        centre.addWidget(column, stretch=1)
        centre.addStretch()
        layout.addLayout(centre)
        cl.addLayout(row)
        cl.addWidget(self.done_hint)
        return page

    def _load_done_page(self):
        n = len(self._applied)
        pts = sum(len(r['points']) for r in self._review_rows if r['ingredient']['Id'] in set(self._applied))
        held = self._held
        text = f'{n} ingredient{"s" if n != 1 else ""} got {pts} price{"s" if pts != 1 else ""}.'
        if held:
            text += (f' {len(held)} left as they were: {", ".join(held[:8])}{"…" if len(held) > 8 else ""}.'
                     ' Fix their vendor items in Configure › Vendor items, then re-price this import.')
        text += ' Recipes using them now cost differently; the Library marks them.'
        self.done_title.setText('Prices updated')
        self.done_body.setText(text)
        self.undo_btn.setEnabled(True)

    def _undo(self):
        if self.batch_id is None:
            return
        if QMessageBox.question(self, 'Import purchases', f'Undo import #{self.batch_id}? Its prices are'
                                ' removed; mappings stay.') != QMessageBox.Yes:
            return
        pi.undo_batch(self.batch_id)
        self.imported.emit(self.batch_id)
        self.done_title.setText('Import undone')
        self.done_body.setText('Prices removed; mappings kept')
        self.undo_btn.setEnabled(False)
