'''Configure › Ingredient categories and Configure › Recipe tags.

One page per tag kind ('ingredient' for categories, 'recipe_tag' for
recipe tags), styled like Allergens: a row per tag with its color, name
and how many ingredients or recipes carry it. Drag to reorder (the order
is the wedge order for categories), double-click or F2 to rename,
Color… or double-click the swatch to pick a color. Categories also
say whether their ingredients need nutrition and a price, which is what
Library health checks. Changes save as you make them; `changed` tells
the main window to refresh.

Formats are recipe tags too ('recipe' kind) but have their own page,
Formats & templates. A tag can't change kind after it's made.
'''
from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QVBoxLayout, QWidget,
)

import db
from gui.widgets import config_kit as kit


_DEFAULT_COLOR = '#64748b'
_SWATCH = 16
# (noun for one, noun for many, what carries it)
_KINDS = {
    'ingredient': ('category', 'New category', 'ingredient'),
    'recipe_tag': ('tag', 'New tag', 'recipe'),
}


def _swatch(color):
    pm = QPixmap(_SWATCH, _SWATCH)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QColor('#7d8771'))
    p.setBrush(QColor(color if QColor(color).isValid() else _DEFAULT_COLOR))
    p.drawEllipse(QRect(1, 1, _SWATCH - 2, _SWATCH - 2))
    p.end()
    return QIcon(pm)


class TagsPage(QWidget):
    changed = Signal()

    def __init__(self, title, kind, note='', parent=None):
        super().__init__(parent)
        self.kind = kind
        self._one, self._new_name, self._carrier = _KINDS[kind]
        self._rows = []

        new_btn = kit.button(f'+ {self._new_name}')
        new_btn.clicked.connect(lambda: self.new_tag())
        head = QHBoxLayout()
        head.addWidget(kit.heading(title))
        head.addStretch()
        head.addWidget(new_btn)

        self.list = QListWidget()
        self.list.setStyleSheet(kit.LIST_STYLE)
        self.list.setMaximumWidth(560)
        self.list.setIconSize(QSize(_SWATCH, _SWATCH))
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setDefaultDropAction(Qt.MoveAction)
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.list.itemChanged.connect(self._on_renamed)
        self.list.model().rowsMoved.connect(self._on_reordered)
        self.list.currentRowChanged.connect(lambda _r: self._sync_buttons())
        self.list.viewport().installEventFilter(self)

        self.color_btn = kit.button('Color…')
        self.color_btn.clicked.connect(lambda: self.pick_color())
        self.delete_btn = kit.button('Delete…', danger=True)
        self.delete_btn.clicked.connect(lambda: self.delete_current())
        foot = QHBoxLayout()
        foot.addWidget(self.color_btn)
        foot.addWidget(self.delete_btn)
        foot.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 28)
        layout.setSpacing(12)
        layout.addLayout(head)
        hint = 'Drag to reorder' + (f'. {note}' if note else '')
        layout.addWidget(kit.note(hint))
        layout.addWidget(self.list, stretch=1)
        layout.addLayout(foot)

        self._emit_timer = QTimer(self)
        self._emit_timer.setSingleShot(True)
        self._emit_timer.setInterval(300)
        self._emit_timer.timeout.connect(self.changed.emit)
        self.refresh()

    # --- data ---

    def refresh(self, select_id=None):
        current = self.current()
        select_id = select_id or (current['id'] if current else None)
        self._rows = db.get_tag_usage(self.kind)
        self.list.blockSignals(True)
        self.list.clear()
        for r in self._rows:
            item = QListWidgetItem(_swatch(r.get('color') or _DEFAULT_COLOR), r['name'] or '')
            item.setFlags(item.flags() | Qt.ItemIsEditable)
            item.setData(Qt.UserRole, r['id'])
            n = r['used']
            item.setData(Qt.UserRole + 1, f"{n} {self._carrier}{'s' if n != 1 else ''}")
            self.list.addItem(item)
        self.list.blockSignals(False)
        for i, r in enumerate(self._rows):
            self.list.setItemWidget(self.list.item(i), self._row_widget(r))
        row = next((i for i, r in enumerate(self._rows) if r['id'] == select_id), 0 if self._rows else -1)
        self.list.setCurrentRow(row)
        self._sync_buttons()

    def _row_widget(self, r):
        '''The right side of a row: the usage count and, for categories,
        the Nutrition and Price checkboxes. Clicks elsewhere in the row
        fall through to the list (select, drag, rename).'''
        row = QWidget()
        row.setAttribute(Qt.WA_TranslucentBackground)
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 12, 0)
        lay.setSpacing(16)
        lay.addStretch()
        if self.kind == 'ingredient':
            for col, text in (('needs_nutrition', 'Nutrition'), ('needs_price', 'Price')):
                box = QCheckBox(text)
                box.setObjectName(col)
                box.setCursor(Qt.PointingHandCursor)
                box.setStyleSheet(
                    f'QCheckBox {{ color: {kit.KALE}; background: transparent; spacing: 6px; }}'
                    f' QCheckBox::indicator {{ width: 14px; height: 14px; border: 1.5px solid {kit.FIELD_BORDER};'
                    ' border-radius: 3px; background: #ffffff; }'
                    f' QCheckBox::indicator:hover {{ border-color: {kit.ROMAINE}; }}'
                    f' QCheckBox::indicator:checked {{ background: {kit.ROMAINE}; border-color: {kit.ROMAINE}; }}')
                box.setChecked(bool(r.get(col, 1)))
                box.toggled.connect(lambda on, tid=r['id'], c=col: self.set_needs(tid, c, on))
                lay.addWidget(box)
        count = QLabel(f"{r['used']} {self._carrier}{'s' if r['used'] != 1 else ''}")
        count.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px; background: transparent;')
        count.setAttribute(Qt.WA_TransparentForMouseEvents)
        count.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        count.setMinimumWidth(count.fontMetrics().horizontalAdvance(f'000 {self._carrier}s'))
        lay.addWidget(count)
        return row

    def set_needs(self, tag_id, column, on):
        '''A category's Nutrition or Price checkbox.'''
        db.update_tag(tag_id, **{column: on})
        for r in self._rows:
            if r['id'] == tag_id:
                r[column] = 1 if on else 0
        self._emit_timer.start()

    def current(self):
        row = self.list.currentRow()
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _sync_buttons(self):
        has = self.current() is not None
        self.color_btn.setEnabled(has)
        self.delete_btn.setEnabled(has)

    # --- edits ---

    def eventFilter(self, obj, event):
        # Double-click on the swatch picks a color instead of renaming.
        if obj is self.list.viewport() and event.type() == event.Type.MouseButtonDblClick:
            item = self.list.itemAt(event.position().toPoint())
            if item is not None:
                rect = self.list.visualItemRect(item)
                if event.position().x() < rect.left() + 12 + _SWATCH + 8:
                    self.list.setCurrentItem(item)
                    self.pick_color()
                    return True
        return super().eventFilter(obj, event)

    def _on_renamed(self, item):
        tid = item.data(Qt.UserRole)
        row = next(r for r in self._rows if r['id'] == tid)
        name = item.text().strip()
        taken = {(r['name'] or '').lower() for r in self._rows if r['id'] != tid}
        if not name or name.lower() in taken:
            self.list.blockSignals(True)
            item.setText(row['name'] or '')
            self.list.blockSignals(False)
            if name:
                QMessageBox.information(self, f'Rename {self._one}', f'There is already a {self._one} called “{name}”.')
            return
        if name != row['name']:
            db.update_tag(tid, name=name)
            row['name'] = name
            self._emit_timer.start()

    def _on_reordered(self, *_args):
        ids = [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]
        db.reorder_tags(ids)
        by_id = {r['id']: r for r in self._rows}
        self._rows = [by_id[i] for i in ids]
        self._emit_timer.start()

    def pick_color(self, color=None):
        r = self.current()
        if r is None:
            return
        if color is None:
            picked = QColorDialog.getColor(QColor(r.get('color') or _DEFAULT_COLOR), self, f'{r["name"]} color')
            if not picked.isValid():
                return
            color = picked.name()
        db.update_tag(r['id'], color=color)
        self.refresh(select_id=r['id'])
        self._emit_timer.start()

    def new_tag(self, name=None):
        taken = {(r['name'] or '').lower() for r in self._rows}
        if name is None:
            base = self._new_name
            name, n = base, 2
            while name.lower() in taken:
                name, n = f'{base} {n}', n + 1
        new_id = db.create_tag(name, kind=self.kind, color=_DEFAULT_COLOR)
        db.reorder_tags([r['id'] for r in self._rows] + [new_id])
        self.refresh(select_id=new_id)
        self.list.editItem(self.list.currentItem())
        self._emit_timer.start()
        return new_id

    def delete_current(self, confirm=True):
        r = self.current()
        if r is None:
            return
        msg = f'Delete “{r["name"]}”?'
        if r['used']:
            msg += f" It comes off {r['used']} {self._carrier}{'s' if r['used'] != 1 else ''}."
        if confirm and QMessageBox.question(self, f'Delete {self._one}', msg, QMessageBox.Yes | QMessageBox.No,
                                            QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_tag(r['id'])
        self.refresh()
        self._emit_timer.start()
