'''Configure › Portion tools: the scoops, bottles and tongs that
ingredients' Portion text names, and a review of that text.

Tools: name, family, size (fl oz, blank for tongs and the like), dot
color and pattern (striped for slotted). A printed recipe works a sized
tool out again from the calculated amount, but only within its family,
so a slotted Red never prints as a plain Red. An ingredient uses a tool
when its Portion text is the tool's name; renaming a tool renames the
text with it.

Review: Portion text that names no tool (with a suggested tool where
one fits, e.g. "2 x grey" → Grey), and text whose tool doesn't fit its
unit (a "red" ingredient whose unit is 3 fl oz). Linking sets those
ingredients' Portion text to the tool's name.
'''
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QColorDialog, QComboBox, QHBoxLayout, QHeaderView, QMessageBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import db
from gui.widgets import config_kit as kit

_TABLE_STYLE = f'''
    QTableWidget {{ border: 1px solid {kit.BORDER}; border-radius: 8px; background: #ffffff;
        gridline-color: {kit.BORDER}; color: {kit.KALE}; }}
    QHeaderView::section {{ background: #ffffff; color: {kit.MUTED}; border: 0;
        border-bottom: 1px solid {kit.BORDER}; padding: 6px 8px; font-weight: 600; }}
'''
_PATTERNS = (('solid', 'Solid'), ('striped', 'Striped (slotted)'))
_COLS = ('Name', 'Family', 'Size (fl oz)', 'Color', 'Pattern', 'Used by')


def _size_text(size):
    return '' if size is None else f'{float(size):g}'


class PortionToolsPage(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tools = []
        self._review = []
        self._filling = False

        new_btn = kit.button('+ New tool')
        new_btn.clicked.connect(self.new_tool)
        self.delete_btn = kit.button('Delete…', danger=True)
        self.delete_btn.clicked.connect(self.delete_current)
        head = QHBoxLayout()
        head.addWidget(kit.heading('Portion tools'))
        head.addStretch()
        head.addWidget(new_btn)

        self.table = QTableWidget(0, len(_COLS))
        self.table.setHorizontalHeaderLabels(_COLS)
        self.table.setStyleSheet(_TABLE_STYLE)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(_COLS)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self._on_item_changed)
        self.table.cellDoubleClicked.connect(self._on_double_clicked)
        self.table.itemSelectionChanged.connect(self._sync_buttons)

        foot = QHBoxLayout()
        foot.addWidget(self.delete_btn)
        foot.addStretch()

        self.apply_all_btn = kit.button('Link all suggestions', primary=True)
        self.apply_all_btn.clicked.connect(self.apply_all_suggestions)
        review_head = QHBoxLayout()
        review_head.addWidget(kit.subheading('Portion text to review'))
        review_head.addStretch()
        review_head.addWidget(self.apply_all_btn)

        self.review = QTableWidget(0, 5)
        self.review.setHorizontalHeaderLabels(('Portion text', 'Unit', 'Ingredients', 'Issue', 'Link to'))
        self.review.setStyleSheet(_TABLE_STYLE)
        self.review.verticalHeader().hide()
        self.review.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.review.setSelectionMode(QAbstractItemView.NoSelection)
        rh = self.review.horizontalHeader()
        for c in (0, 1, 2, 4):
            rh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        rh.setSectionResizeMode(3, QHeaderView.Stretch)

        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(12)
        layout.addLayout(head)
        layout.addWidget(kit.note(
            'Printed recipe pages name the tool for each ingredient. A sized tool is worked out again from the'
            ' calculated amount, within its family only: half of an 8 fl oz unit on Grey prints “1 Grey”, and a'
            ' slotted Red never becomes a plain Red. Tools with no size (tongs, bottle) print by name. An'
            ' ingredient uses a tool when its Portion text is the tool’s name. Double-click to edit;'
            ' double-click a color to pick one.'))
        layout.addWidget(self.table)
        layout.addLayout(foot)
        layout.addSpacing(8)
        layout.addLayout(review_head)
        layout.addWidget(kit.note(
            'Portion text that names no tool, or whose tool doesn’t fit the unit. Linking sets those'
            ' ingredients’ Portion text to the tool’s name. Text left unlinked prints only when the recipe'
            ' uses exactly one unit.'))
        layout.addWidget(self.review)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()   # ingredients may have changed elsewhere

    # --- tools -----------------------------------------------------------

    def refresh(self, select_id=None):
        current = self.current()
        select_id = select_id or (current['id'] if current else None)
        self._tools = db.get_portion_tools()
        self._filling = True
        self.table.setRowCount(len(self._tools))
        for row, t in enumerate(self._tools):
            values = (t['name'], t['family'] or '', _size_text(t['size_floz']), t['color'] or '', None,
                      f"{t['used']} ingredient{'s' if t['used'] != 1 else ''}")
            for col, value in enumerate(values):
                if col == 4:
                    combo = QComboBox()
                    for key, label in _PATTERNS:
                        combo.addItem(label, key)
                    combo.setCurrentIndex(max(0, combo.findData(t['pattern'] or 'solid')))
                    combo.currentIndexChanged.connect(
                        lambda _i, tid=t['id'], c=combo: self._save(tid, pattern=c.currentData()))
                    self.table.setCellWidget(row, col, combo)
                    continue
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, t['id'])
                if col in (3, 5):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if col == 3:
                    item.setText(t['color'] or 'none')
                    if t['color']:
                        item.setBackground(QBrush(QColor(t['color'])))
                        light = QColor(t['color']).lightness() > 150
                        item.setForeground(QBrush(QColor(kit.KALE if light else '#ffffff')))
                if col == 5:
                    item.setForeground(QBrush(QColor(kit.MUTED)))
                self.table.setItem(row, col, item)
        self._filling = False
        self.table.setFixedHeight(min(420, 34 + 32 * max(1, len(self._tools))))
        row = next((i for i, t in enumerate(self._tools) if t['id'] == select_id), -1)
        if row >= 0:
            self.table.selectRow(row)
        self._sync_buttons()
        self.refresh_review()

    def current(self):
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows or rows[0].row() >= len(self._tools):
            return None
        return self._tools[rows[0].row()]

    def _sync_buttons(self):
        self.delete_btn.setEnabled(self.current() is not None)

    def _save(self, tool_id, **fields):
        try:
            db.update_portion_tool(tool_id, **fields)
        except Exception as exc:   # e.g. a name already taken
            QMessageBox.information(self, 'Portion tools', f'Couldn’t save that: {exc}')
        self.refresh(select_id=tool_id)
        self.changed.emit()

    def _on_item_changed(self, item):
        if self._filling:
            return
        tool_id = item.data(Qt.UserRole)
        text = item.text().strip()
        col = item.column()
        if col == 0:
            taken = {t['name'].casefold() for t in self._tools if t['id'] != tool_id}
            if not text or text.casefold() in taken:
                if text:
                    QMessageBox.information(self, 'Portion tools', f'There is already a tool called “{text}”.')
                self.refresh(select_id=tool_id)
                return
            self._save(tool_id, name=text)
        elif col == 1:
            self._save(tool_id, family=text)
        elif col == 2:
            if not text:
                self._save(tool_id, size_floz=None)
                return
            try:
                size = float(text)
                if size <= 0:
                    raise ValueError
            except ValueError:
                QMessageBox.information(self, 'Portion tools', 'Size is in fluid ounces, e.g. 2 or 0.5;'
                                        ' leave it blank for tongs and the like.')
                self.refresh(select_id=tool_id)
                return
            self._save(tool_id, size_floz=size)

    def _on_double_clicked(self, row, col):
        if col != 3 or row >= len(self._tools):
            return
        t = self._tools[row]
        color = QColorDialog.getColor(QColor(t['color'] or '#ffffff'), self, f"Color for {t['name']}")
        if color.isValid():
            self._save(t['id'], color=color.name())

    def new_tool(self):
        taken = {t['name'].casefold() for t in self._tools}
        name, n = 'New tool', 2
        while name.casefold() in taken:
            name, n = f'New tool {n}', n + 1
        new_id = db.create_portion_tool(name)
        self.refresh(select_id=new_id)
        row = next(i for i, t in enumerate(self._tools) if t['id'] == new_id)
        self.table.editItem(self.table.item(row, 0))
        self.changed.emit()

    def delete_current(self):
        t = self.current()
        if t is None:
            return
        msg = f'Delete “{t["name"]}”?'
        if t['used']:
            msg += (f" {t['used']} ingredient{'s keep' if t['used'] != 1 else ' keeps'} the text"
                    ' but it won’t link to a tool.')
        if QMessageBox.question(self, 'Delete tool', msg, QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_portion_tool(t['id'])
        self.refresh()
        self.changed.emit()

    # --- review ----------------------------------------------------------

    def refresh_review(self):
        self._review = db.get_portion_text_review()
        tool_names = [t['name'] for t in self._tools]
        self.review.setRowCount(len(self._review))
        for row, r in enumerate(self._review):
            cells = (r['portion'], r['unit'], str(r['count']),
                     r['problem'] or ('Suggested: ' + r['suggestion'] if r['suggestion'] else 'Not a tool'))
            for col, value in enumerate(cells):
                item = QTableWidgetItem(value)
                if col == 2:
                    item.setToolTip(r['names'])
                if col == 3:
                    item.setForeground(QBrush(QColor(kit.WARN if r['problem'] else kit.MUTED)))
                self.review.setItem(row, col, item)
            combo = QComboBox()
            combo.addItem('—', None)
            for name in tool_names:
                combo.addItem(name, name)
            pick = r['suggestion'] or (r['tool'] if r['problem'] else None)
            combo.setCurrentIndex(max(0, combo.findData(pick)) if pick else 0)
            link = kit.button('Link')
            link.clicked.connect(lambda _c=False, rr=r, c=combo: self._link(rr, c.currentData()))
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(6)
            h.addWidget(combo)
            h.addWidget(link)
            self.review.setCellWidget(row, 4, cell)
            self.review.setRowHeight(row, 40)
        self.review.setFixedHeight(min(520, 36 + 40 * max(1, len(self._review))))
        self.apply_all_btn.setEnabled(any(r['suggestion'] for r in self._review))

    def _link(self, review_row, tool_name):
        if not tool_name:
            return
        db.link_portion_text(review_row['portion'], review_row['unit'], tool_name)
        self.refresh()
        self.changed.emit()

    def apply_all_suggestions(self):
        todo = [r for r in self._review if r['suggestion']]
        if not todo:
            return
        lines = '\n'.join(f"“{r['portion']}” ({r['unit'] or 'no unit'}) → {r['suggestion']}"
                          f"  · {r['count']} ingredient{'s' if r['count'] != 1 else ''}" for r in todo)
        if QMessageBox.question(self, 'Link suggestions', f'Link these?\n\n{lines}',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        for r in todo:
            db.link_portion_text(r['portion'], r['unit'], r['suggestion'])
        self.refresh()
        self.changed.emit()
