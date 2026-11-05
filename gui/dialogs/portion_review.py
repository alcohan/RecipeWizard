'''Check recipes against portion rules (utilities/portions.py).

Lists every recipe row that's sized by hand in a category its format has
a rule for — after the upgrade from portion multipliers, those are the
recipes whose quantities differed from the format's standard. Each
recipe/category is one line showing its quantities now and what the rule
would make them, with the cost change. Tick the ones to bring onto the
rules; the rest stay sized by hand. Bringing them across can be undone
until the dialog closes.

Opened from Configure › Formats & templates, and once by itself after
the upgrade (see maybe_show_after_upgrade).'''
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
)

import config
import db
from gui.widgets import config_kit as kit

_SEEN_KEY = 'portion_review_shown'


def maybe_show_after_upgrade(parent=None):
    '''Open the review once, the first time there's something in it.
    Returns True if it brought any recipe onto the rules.'''
    if db.query('SELECT 1 FROM app_meta WHERE key = ?;', (_SEEN_KEY,), one=True):
        return False
    groups = db.portion_review()
    if not any(g['rows'] for g in groups):
        return False
    db.query('INSERT OR REPLACE INTO app_meta (key, value) VALUES (?, ?);', (_SEEN_KEY, '1'))
    dlg = PortionReviewDialog(parent=parent, first_run=True)
    dlg.exec()
    return dlg.changed


def _qty(value):
    return '' if value is None else f'{float(value):.3f}'.rstrip('0').rstrip('.')


def _money(value):
    sign = '+' if value > 0.0049 else ('−' if value < -0.0049 else '±')
    return f'{sign}${abs(value):.2f}'


class PortionReviewDialog(QDialog):
    def __init__(self, parent=None, first_run=False):
        super().__init__(parent)
        self.setWindowTitle(f'{config.APPNAME} | Check recipes against portion rules')
        self.resize(900, 640)
        self.setStyleSheet(f'QDialog {{ background: {kit.BG}; }}')
        self.changed = False          # True once anything was brought across
        self._undo = None             # {recipe_id: snapshot} of the last apply
        self._groups = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(12)
        layout.addWidget(kit.heading('Check recipes against portion rules'))
        intro = ('Portion multipliers are now portion rules. These recipes have ingredients sized by hand'
                 ' that differ from their format’s rule; nothing has changed yet.') if first_run else \
                ('These recipes have ingredients sized by hand in a category their format has a rule for.')
        layout.addWidget(kit.note(intro + ' Tick the ones to bring onto the rules; the rest stay as they'
                                  ' are. A base keeps its current split.'))

        self.banner = QFrame()
        self.banner.setObjectName('ReviewBanner')
        self.banner.setStyleSheet(f'QFrame#ReviewBanner {{ background: {kit.SELECTED}; border: 1px solid #f0d9b5;'
                                  ' border-radius: 8px; }')
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(14, 8, 8, 8)
        self.banner_text = QLabel('')
        self.banner_text.setStyleSheet(f'color: {kit.KALE};')
        undo = kit.button('Undo')
        undo.clicked.connect(self._on_undo)
        bl.addWidget(self.banner_text, stretch=1)
        bl.addWidget(undo)
        self.banner.hide()
        layout.addWidget(self.banner)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(['Recipe', 'Category', 'Now', 'With the rule', 'Cost change'])
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet(f'''
            QTreeWidget {{ background: #ffffff; border: 1px solid {kit.BORDER}; border-radius: 8px;
                color: {kit.KALE}; }}
            QTreeWidget::item {{ min-height: 28px; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.MUTED}; border: 0;
                border-bottom: 1px solid {kit.BORDER}; padding: 8px; font-size: 11px; font-weight: 600; }}''')
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col, width in ((1, 130), (2, 90), (3, 110), (4, 100)):
            header.setSectionResizeMode(col, QHeaderView.Fixed)
            self.tree.setColumnWidth(col, width)
        self.tree.itemChanged.connect(lambda *_: self._sync_footer())
        layout.addWidget(self.tree, stretch=1)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        select_all = kit.button('Select all')
        select_all.clicked.connect(lambda: self._set_all(True))
        select_none = kit.button('Select none')
        select_none.clicked.connect(lambda: self._set_all(False))
        self.summary = kit.note('')
        self.apply_btn = kit.button('Bring onto rules', primary=True)
        self.apply_btn.setStyleSheet(self.apply_btn.styleSheet()
                                     + ' QPushButton:disabled { background: #c9cfbf; color: #ffffff; }')
        self.apply_btn.clicked.connect(self._on_apply)
        close = kit.button('Close')
        close.clicked.connect(self.accept)
        for w in (select_all, select_none):
            foot.addWidget(w)
        foot.addWidget(self.summary, stretch=1)
        foot.addWidget(self.apply_btn)
        foot.addWidget(close)
        layout.addLayout(foot)

        self._load()

    # --- list ----------------------------------------------------------

    def _load(self):
        self._groups = db.portion_review()
        self.tree.blockSignals(True)
        try:
            self.tree.clear()
            fmt_item = None
            for i, g in enumerate(self._groups):
                if fmt_item is None or fmt_item.text(0) != g['format']:
                    fmt_item = QTreeWidgetItem([g['format']])
                    fmt_item.setFlags(Qt.ItemIsEnabled)
                    font = fmt_item.font(0)
                    font.setBold(True)
                    fmt_item.setFont(0, font)
                    self.tree.addTopLevelItem(fmt_item)
                    fmt_item.setExpanded(True)
                name = g['recipe'] + ('  (archived)' if g['status'] == 'archived' else '')
                item = QTreeWidgetItem([name, g['category']])
                item.setData(0, Qt.UserRole, i)
                item.setToolTip(0, g['rule'])
                item.setToolTip(1, g['rule'])
                if g['rows']:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
                    item.setCheckState(0, Qt.Unchecked)
                    item.setText(4, _money(g['cost_change']))
                    item.setTextAlignment(4, Qt.AlignRight | Qt.AlignVCenter)
                    if g['at_standard']:
                        item.setText(3, 'already there')
                else:
                    item.setFlags(Qt.ItemIsEnabled)
                fmt_item.addChild(item)
                for row in g['rows']:
                    child = QTreeWidgetItem([f'    {row["name"]}', row['unit'] or '',
                                             _qty(row['current']), _qty(row['standard'])])
                    child.setFlags(Qt.ItemIsEnabled)
                    for col in (2, 3):
                        child.setTextAlignment(col, Qt.AlignRight | Qt.AlignVCenter)
                    child.setForeground(1, QColor(kit.MUTED))
                    item.addChild(child)
                for u in g['unsizable']:
                    child = QTreeWidgetItem([f'    {u["name"]}', u['unit'] or '', '', 'can’t size'])
                    child.setFlags(Qt.ItemIsEnabled)
                    child.setToolTip(3, 'Its unit isn’t a volume, so the rule can’t size it. Give it a unit'
                                        ' like “3 cups” or move it to another category.')
                    for col in range(4):
                        child.setForeground(col, QColor(kit.WARN))
                    item.addChild(child)
                item.setExpanded(True)
        finally:
            self.tree.blockSignals(False)
        if not self._groups:
            empty = QTreeWidgetItem(['Every recipe follows its format’s portion rules.'])
            empty.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(empty)
        self._sync_footer()

    def _group_items(self):
        for i in range(self.tree.topLevelItemCount()):
            fmt_item = self.tree.topLevelItem(i)
            for j in range(fmt_item.childCount()):
                item = fmt_item.child(j)
                if item.flags() & Qt.ItemIsUserCheckable:
                    yield item

    def _checked(self):
        return [self._groups[item.data(0, Qt.UserRole)] for item in self._group_items()
                if item.checkState(0) == Qt.Checked]

    def _set_all(self, on):
        self.tree.blockSignals(True)
        for item in self._group_items():
            item.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._sync_footer()

    def _sync_footer(self):
        checked = self._checked()
        recipes = {g['recipe_id'] for g in checked}
        self.apply_btn.setEnabled(bool(checked))
        if not checked:
            total = len(list(self._group_items()))
            self.summary.setText(f'{total} to review.' if total else '')
            return
        change = sum(g['cost_change'] for g in checked)
        n = len(recipes)
        self.summary.setText(f'{n} recipe{"" if n == 1 else "s"} selected · cost change {_money(change)}'
                             ' in total')

    # --- apply / undo ---------------------------------------------------

    def _on_apply(self):
        checked = self._checked()
        if not checked:
            return
        self._undo = db.follow_portion_groups(checked)
        self.changed = True
        n = len(self._undo)
        self.banner_text.setText(f'Brought {n} recipe{"" if n == 1 else "s"} onto the portion rules.')
        self.banner.show()
        self._load()

    def _on_undo(self):
        for rid, rows in (self._undo or {}).items():
            db.restore_recipe_connections(rid, rows)
        self._undo = None
        self.banner.hide()
        self._load()

    def apply_groups(self, predicate):
        '''Tick the groups `predicate(group)` accepts and bring them onto
        the rules (for tests and scripted use).'''
        self.tree.blockSignals(True)
        for item in self._group_items():
            g = self._groups[item.data(0, Qt.UserRole)]
            item.setCheckState(0, Qt.Checked if predicate(g) else Qt.Unchecked)
        self.tree.blockSignals(False)
        self._on_apply()
