'''Cross-recipe analytics tab.

Spreadsheet layout: one row per recipe, one column per ingredient
category, cells filled with the currently-selected metric (cost,
calories, fat, etc.). Tooltips on each cell list the ingredients that
contribute to that recipe-category bucket, with per-ingredient values.
Double-click a recipe name to open its edit dialog.

The data source is a single per-(recipe, ingredient) SQL query that
Python pivots on demand for each metric, so switching metrics is
instant and doesn't require another database roundtrip.
'''
from collections import defaultdict

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QLineEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

import db


# (key, label, format_fn). format_fn returns the cell text for a numeric value.
_METRICS = [
    ('cost',     'Cost',     lambda v: f'${v:.2f}'),
    ('calories', 'Calories', lambda v: f'{v:.0f}'),
    ('fat',      'Fat (g)',  lambda v: f'{v:.1f}'),
    ('carbs',    'Carbs (g)', lambda v: f'{v:.1f}'),
    ('protein',  'Protein (g)', lambda v: f'{v:.1f}'),
    ('fiber',    'Fiber (g)', lambda v: f'{v:.1f}'),
    ('sodium',   'Sodium (mg)', lambda v: f'{v:.0f}'),
    ('sat_fat',  'Sat Fat (g)', lambda v: f'{v:.1f}'),
    ('sugar',    'Sugar (g)',   lambda v: f'{v:.1f}'),
    ('cholesterol', 'Cholesterol (mg)', lambda v: f'{v:.0f}'),
    ('weight',   'Weight (g)',  lambda v: f'{v:.0f}'),
]


class AnalyticsTab(QWidget):
    '''Multi-recipe spreadsheet of cost + nutrition by ingredient category.'''

    recipeActivated = Signal(int)  # recipe_id, emitted on double-click

    def __init__(self, recipes_model, parent=None):
        super().__init__(parent)
        self._recipes_model = recipes_model

        # Cached data. _all_rows is the raw per-(recipe, ingredient) result
        # from the SQL query; pivots are computed on demand from this so
        # switching the displayed metric doesn't re-hit the DB.
        self._all_rows = []
        self._recipe_order = []   # [(recipe_id, recipe_name, recipe_unit)]
        self._categories = []     # [(category_name, color_hex)]

        # Lazy build, same pattern as the ingredients gallery: don't
        # query/render until the tab is actually shown, and rebuild on
        # model reset only if currently visible.
        self._stale = True

        self.metric_combo = QComboBox()
        for key, label, _fmt in _METRICS:
            self.metric_combo.addItem(label, key)
        self.metric_combo.currentIndexChanged.connect(self._rebuild_table)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText('\U0001F50D  Filter recipes…')
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._rebuild_table)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._on_row_activated)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel('Metric:'))
        top_row.addWidget(self.metric_combo)
        top_row.addSpacing(20)
        top_row.addWidget(self.filter_edit, stretch=1)

        layout = QVBoxLayout(self)
        layout.addLayout(top_row)
        layout.addWidget(self.table, stretch=1)

        recipes_model.modelReset.connect(self._on_model_reset)

    # --- lifecycle / lazy build ---

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()
            self._stale = False

    def _on_model_reset(self):
        self._stale = True
        if self.isVisible():
            self.refresh()
            self._stale = False

    def refresh(self):
        '''Re-fetch the raw per-ingredient data and rebuild the table.'''
        self._all_rows = db.get_recipe_category_details()

        # Recipe order: alphabetical by name. Stable across rebuilds so
        # the user's filter doesn't reshuffle row order.
        recipe_map = {}
        for r in self._all_rows:
            recipe_map[r['recipe_id']] = (r['recipe_name'], r['recipe_unit'])
        self._recipe_order = sorted(
            [(rid, name, unit) for rid, (name, unit) in recipe_map.items()],
            key=lambda x: (x[1] or '').lower(),
        )

        # Category columns: union across all recipes. Alphabetical,
        # with '(uncategorized)' sunk to the end.
        cat_map = {}
        for r in self._all_rows:
            cat_map[r['category']] = r['color']
        self._categories = sorted(
            cat_map.items(),
            key=lambda x: (x[0] == '(uncategorized)', (x[0] or '').lower()),
        )

        self._rebuild_table()

    # --- rendering ---

    def _rebuild_table(self):
        '''Pivot the cached rows for the currently-selected metric and
        repaint the table. Cheap: pure-Python pass over a few hundred
        rows at most, so it's fine to do on every keystroke / metric flip.'''
        metric_key = self.metric_combo.currentData()
        if metric_key is None or not self._categories:
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        fmt = next((f for k, _, f in _METRICS if k == metric_key), str)

        needle = self.filter_edit.text().strip().lower()
        visible_recipes = [
            (rid, name, unit) for rid, name, unit in self._recipe_order
            if not needle or needle in (name or '').lower()
        ]

        # Pivot for current metric: pivot[recipe_id][category] = {'total', 'items'}.
        # Items are kept per-ingredient so we can render the tooltip.
        pivot = defaultdict(lambda: defaultdict(lambda: {'total': 0.0, 'items': []}))
        for r in self._all_rows:
            cell = pivot[r['recipe_id']][r['category']]
            value = float(r.get(metric_key) or 0)
            cell['total'] += value
            cell['items'].append((r['ingredient_name'], value))

        n_rows = len(visible_recipes)
        n_cats = len(self._categories)
        n_cols = 1 + n_cats + 1  # Recipe | <category columns> | Total

        # setSortingEnabled toggle is the standard guard so setItem calls
        # during rebuild don't trigger spurious sort comparisons.
        self.table.setSortingEnabled(False)
        self.table.clear()
        self.table.setRowCount(n_rows)
        self.table.setColumnCount(n_cols)

        # Headers
        headers = ['Recipe'] + [cat for cat, _ in self._categories] + ['Total']
        self.table.setHorizontalHeaderLabels(headers)
        # Paint each category-column header with the category's tag color
        # so the eye can follow a category vertically through cells.
        for i, (_cat, color) in enumerate(self._categories):
            hdr_item = self.table.horizontalHeaderItem(i + 1)
            if hdr_item is None:
                continue
            qcolor = QColor(color)
            hdr_item.setBackground(qcolor)
            # Pick white or black text based on perceived luminance.
            hdr_item.setForeground(QColor('white' if _is_dark(qcolor) else '#111'))

        # Body
        for r_idx, (rid, name, unit) in enumerate(visible_recipes):
            recipe_pivot = pivot[rid]
            row_total = sum(recipe_pivot[cat]['total'] for cat, _ in self._categories)

            name_item = QTableWidgetItem(name or '')
            name_item.setData(Qt.UserRole, rid)
            name_item.setToolTip(f'Double-click to open {name!r}'
                                 + (f' (per {unit})' if unit else ''))
            self.table.setItem(r_idx, 0, name_item)

            for c_idx, (cat, _color) in enumerate(self._categories):
                cell = recipe_pivot[cat]
                value = cell['total']
                if value <= 0:
                    item = QTableWidgetItem('—')
                    item.setForeground(QColor('#bbb'))
                else:
                    item = QTableWidgetItem(fmt(value))
                    # Tooltip: contributing ingredients, highest first.
                    item.setToolTip(_format_tooltip(name, cat, cell['items'], fmt))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r_idx, 1 + c_idx, item)

            total_item = QTableWidgetItem(fmt(row_total) if row_total > 0 else '—')
            total_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            font = total_item.font()
            font.setBold(True)
            total_item.setFont(font)
            if row_total <= 0:
                total_item.setForeground(QColor('#bbb'))
            self.table.setItem(r_idx, 1 + n_cats, total_item)

        self.table.resizeColumnsToContents()

    # --- handlers ---

    def _on_row_activated(self, index):
        if not index.isValid():
            return
        name_item = self.table.item(index.row(), 0)
        if name_item is None:
            return
        rid = name_item.data(Qt.UserRole)
        if rid is not None:
            self.recipeActivated.emit(int(rid))

    def focus_filter(self):
        '''Called by main_window's Ctrl+F shortcut when this tab is active.'''
        self.filter_edit.setFocus()
        self.filter_edit.selectAll()


def _format_tooltip(recipe_name, category, items, fmt):
    '''Multi-line tooltip listing the ingredients that contribute to a
    (recipe, category) bucket, sorted by contribution descending.'''
    items_sorted = sorted(items, key=lambda x: -x[1])
    lines = [f'{recipe_name} — {category}']
    for nm, value in items_sorted:
        lines.append(f'  {nm}: {fmt(value)}')
    return '\n'.join(lines)


def _is_dark(qcolor):
    '''Standard luminance test so we can pick a legible header-text color
    against the tag's background.'''
    r, g, b = qcolor.red(), qcolor.green(), qcolor.blue()
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140
