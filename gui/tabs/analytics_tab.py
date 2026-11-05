'''Analytics: the compare tray, expanded (Framework canvas board 4).

Left, the compare set: the tray's recipes (wedge, name, ×; drag to
reorder), an "Add recipe…" box, and saved comparisons (click to open;
right-click to update, rename or delete). Right, the metric switch
(Cost, Calories, Protein, Fat, Carbs, Sodium, Weight), Per (serving,
100 g, $1 of menu price) and Values ($ amount or % of total); a stacked
bar per recipe by ingredient category with a sentence on what stands
out; and the side-by-side table (the metric by category, total, menu
price · food cost, nutrition, allergens), which Export CSV writes.

The numbers come from utilities.compare over one whole-library query,
so switching metric or basis is a re-pivot, not a database trip. The
tray itself is session-scoped; Save comparison keeps a named copy in
the library.
'''
import csv
import os

from PySide6.QtCore import QMimeData, QPoint, QSettings, QStandardPaths, Qt, Signal
from PySide6.QtGui import QColor, QDrag, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCompleter, QFileDialog, QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
    QLineEdit, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QTableWidget, QTableWidgetItem,
    QToolButton, QVBoxLayout, QWidget,
)

import db
from gui.services import food_cost
from gui.services.compare_tray import CompareTray
from gui.widgets import config_kit as kit
from gui.widgets.compare_chart import CompareChart
from gui.widgets.elided_label import ElidedLabel
from gui.widgets.flow_layout import FlowLayout
from gui.widgets.toolbar_controls import SegmentedSwitch, ToolbarCombo
from gui.widgets.wedge_view import WedgeView
from utilities import compare


_ROW_LINE = '#f3ece0'
_WARN_BG = '#fff0dc'
_MIME = 'application/x-recipewizard-tray-id'


class AnalyticsTab(QWidget):
    recipeActivated = Signal(int)
    dockRequested = Signal()

    def __init__(self, recipes_model, compare_tray=None, library_ids=None, parent=None):
        '''library_ids() returns the ids the Library is showing, for the
        empty state's "compare the Library view".'''
        super().__init__(parent)
        self._model = recipes_model
        self._tray = compare_tray if compare_tray is not None else CompareTray(self)
        self._library_ids = library_ids
        self._details = []
        self._categories = []
        self._colors = {}
        self._thumbs = {}
        self._active_saved = None
        self._stale = True
        self.data = None
        settings = QSettings()
        self._settings = {k: settings.value(f'analytics/{k}', v, type=str)
                          for k, v in compare.DEFAULT_SETTINGS.items()}

        self.setStyleSheet(f'AnalyticsTab {{ background: {kit.BG}; }}')
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Title bar.
        self.subtitle = QLabel('')
        self.subtitle.setStyleSheet(f'color: {kit.MUTED};')
        self.export_btn = kit.button('Export CSV')
        self.export_btn.setToolTip('Save the side-by-side table as a CSV file')
        self.export_btn.clicked.connect(lambda: self.export_csv())
        dock_btn = kit.button('Dock to bottom')
        dock_btn.setToolTip('Back to Recipes with the compare tray docked (Ctrl+Shift+C)')
        dock_btn.clicked.connect(self.dockRequested.emit)
        self.save_btn = kit.button('Save comparison', primary=True)
        self.save_btn.clicked.connect(lambda: self.save_comparison())
        bar = QFrame()
        bar.setObjectName('AnalyticsBar')
        bar.setStyleSheet(f'QFrame#AnalyticsBar {{ background: #ffffff; border-bottom: 1px solid {kit.BORDER}; }}')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(16)
        bl.addWidget(kit.heading('Analytics'))
        bl.addWidget(self.subtitle)
        bl.addStretch()
        bl.addWidget(self.export_btn)
        bl.addWidget(dock_btn)
        bl.addWidget(self.save_btn)

        # Compare set (left).
        self.tray_heading = kit.eyebrow('Compare tray')
        self.tray_list = _TrayList(self._tray)
        self.tray_list.activated.connect(self.recipeActivated.emit)
        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText('+  Add recipe…')
        self.add_edit.setStyleSheet(f'QLineEdit {{ min-height: 32px; padding: 0 10px; border: 1px dashed'
                                    f' {kit.FIELD_BORDER}; border-radius: 8px; background: transparent;'
                                    f' color: {kit.KALE}; }} QLineEdit:focus {{ border-style: solid; }}')
        self.add_edit.returnPressed.connect(lambda: self.add_by_name(self.add_edit.text()))
        self._completer = QCompleter([], self)
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.activated.connect(self.add_by_name)
        self.add_edit.setCompleter(self._completer)
        self.saved_box = QVBoxLayout()
        self.saved_box.setSpacing(2)
        self.saved_empty = kit.note('None yet. Save comparison keeps this set and its settings.')

        aside = QWidget()
        aside.setFixedWidth(250)
        al = QVBoxLayout(aside)
        al.setContentsMargins(16, 20, 16, 20)
        al.setSpacing(6)
        al.addWidget(self.tray_heading)
        al.addWidget(self.tray_list)
        al.addWidget(self.add_edit)
        al.addSpacing(16)
        al.addWidget(kit.eyebrow('Saved comparisons'))
        al.addLayout(self.saved_box)
        al.addWidget(self.saved_empty)
        al.addStretch()
        aside_scroll = QScrollArea()
        aside_scroll.setWidget(aside)
        aside_scroll.setWidgetResizable(True)
        aside_scroll.setFixedWidth(252)
        aside_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        aside_scroll.setFrameShape(QFrame.NoFrame)
        aside_scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; border-right: 1px solid {kit.BORDER}; }}'
                                   ' QScrollArea > QWidget > QWidget { background: transparent; }')

        # Controls.
        self.metric_switch = SegmentedSwitch([(k, label) for k, label, _u, _d in compare.METRICS])
        self.metric_switch.changed.connect(lambda k: self.set_setting('metric', k))
        self.basis_combo = ToolbarCombo()
        for key, label in compare.BASES:
            self.basis_combo.addItem(label, key)
        self.basis_combo.currentIndexChanged.connect(
            lambda _i: self.set_setting('basis', self.basis_combo.currentData()))
        self.values_switch = SegmentedSwitch([(k, label) for k, label in compare.VALUES])
        self.values_switch.changed.connect(lambda k: self.set_setting('values', k))
        per = QLabel('Per')
        per.setStyleSheet(f'color: {kit.MUTED};')
        controls = QHBoxLayout()
        controls.setSpacing(12)
        controls.addWidget(self.metric_switch)
        controls.addSpacing(12)
        controls.addWidget(per)
        controls.addWidget(self.basis_combo)
        controls.addSpacing(12)
        controls.addWidget(self.values_switch)
        controls.addStretch()

        # Chart card.
        self.chart_title = QLabel('')
        self.chart_title.setStyleSheet(f'color: {kit.KALE}; font-size: 17px; font-weight: 600;')
        self.legend_host = QWidget()
        self.legend = FlowLayout(self.legend_host, spacing=12)
        self.chart = CompareChart(self._thumb)
        self.chart.recipeActivated.connect(self.recipeActivated.emit)
        self.insight = QLabel('')
        self.insight.setWordWrap(True)
        self.insight.setStyleSheet(f'color: {kit.MUTED}; font-size: 13px;')
        self.chart_card, ccl = kit.card()
        ccl.setContentsMargins(24, 20, 24, 20)
        ccl.setSpacing(14)
        head = QHBoxLayout()
        head.setSpacing(16)
        head.addWidget(self.chart_title)
        head.addWidget(self.legend_host, stretch=1)
        ccl.addLayout(head)
        ccl.addWidget(self.chart)
        ccl.addWidget(self.insight)

        # Side-by-side table.
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setWordWrap(False)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().sectionDoubleClicked.connect(self._on_header_double_clicked)
        self.table.setStyleSheet(f'''
            QTableWidget {{ background: #ffffff; color: {kit.KALE}; border: 0; }}
            QTableWidget::item {{ padding: 0 16px; border-top: 1px solid {_ROW_LINE}; }}
            QHeaderView::section {{ background: #ffffff; color: {kit.KALE}; font-weight: 600; border: 0;
                border-bottom: 1px solid {kit.BORDER}; padding: 10px 16px; }}
        ''')
        self.table_card, tcl = kit.card()
        tcl.setContentsMargins(0, 0, 0, 0)
        tcl.addWidget(self.table)

        # Empty state.
        self.empty_card, ecl = kit.card()
        ecl.setContentsMargins(24, 20, 24, 24)
        ecl.addWidget(kit.subheading('Nothing to compare yet'))
        ecl.addWidget(kit.note('Add recipes with the box on the left, press Space on a recipe in the Library,'
                               ' or open a saved comparison.'))
        self.library_btn = kit.button('Compare the Library view')
        self.library_btn.clicked.connect(self.compare_library_view)
        row = QHBoxLayout()
        row.addWidget(self.library_btn)
        row.addStretch()
        ecl.addLayout(row)

        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(28, 20, 28, 28)
        ml.setSpacing(20)
        ml.addLayout(controls)
        ml.addWidget(self.empty_card)
        ml.addWidget(self.chart_card)
        ml.addWidget(self.table_card)
        ml.addStretch()
        self.main_scroll = QScrollArea()
        self.main_scroll.setWidget(main)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setFrameShape(QFrame.NoFrame)
        self.main_scroll.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; }}'
                                       ' QScrollArea > QWidget > QWidget { background: transparent; }')

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(aside_scroll)
        body.addWidget(self.main_scroll, stretch=1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addLayout(body, stretch=1)

        self._apply_controls()
        self._tray.changed.connect(self._on_tray_changed)
        recipes_model.modelReset.connect(self._on_model_reset)

    # --- lifecycle ---------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if self._stale:
            self.refresh()

    def _on_model_reset(self):
        self._stale = True
        self._thumbs.clear()
        if self.isVisible():
            self.refresh()

    def refresh(self):
        '''Re-read the library (details, categories, saved comparisons).'''
        self._stale = False
        self._details = db.get_recipe_category_details()
        tags = db.get_tags('ingredient')
        self._categories = compare.category_order(tags)
        self._colors = {t['name']: t.get('color') or '#888888' for t in tags}
        self._completer.model().setStringList(sorted((r['Name'] for r in self._model.rows()), key=str.lower))
        self._rebuild_saved()
        self._rebuild()

    def _on_tray_changed(self):
        if self.isVisible() and not self._stale:
            self._rebuild()

    # --- settings ----------------------------------------------------

    def settings(self):
        return dict(self._settings)

    def set_setting(self, key, value):
        if value is None or self._settings.get(key) == value:
            return
        self._settings[key] = value
        QSettings().setValue(f'analytics/{key}', value)
        self._apply_controls()
        self._rebuild()

    def apply_settings(self, settings):
        for key, default in compare.DEFAULT_SETTINGS.items():
            self._settings[key] = settings.get(key, default)
            QSettings().setValue(f'analytics/{key}', self._settings[key])
        self._apply_controls()

    def _apply_controls(self):
        s = self._settings
        if s['metric'] not in dict((m[0], 1) for m in compare.METRICS):
            s['metric'] = 'cost'
        # Weight per 100 g is always 100 g.
        if s['metric'] == 'weight' and s['basis'] == '100g':
            s['basis'] = 'serving'
        self.metric_switch.set_current(s['metric'])
        self.metric_switch.buttons['weight'].setEnabled(s['basis'] != '100g')
        self.metric_switch.buttons['weight'].setToolTip(
            'Not available per 100 g' if s['basis'] == '100g' else '')
        self.basis_combo.blockSignals(True)
        self.basis_combo.setCurrentIndex(max(0, self.basis_combo.findData(s['basis'])))
        self.basis_combo.blockSignals(False)
        self.values_switch.set_current(s['values'])
        self.values_switch.buttons['amount'].setText('$ amount' if s['metric'] == 'cost' else 'Amount')

    # --- tray --------------------------------------------------------

    def _known_ids(self):
        return {r['Id'] for r in self._model.rows()}

    def recipe_ids(self):
        '''The tray's recipes that still exist, in tray order.'''
        known = self._known_ids()
        return [rid for rid in self._tray.ids() if rid in known]

    def add_by_name(self, name):
        name = (name or '').strip().lower()
        row = next((r for r in self._model.rows() if r['Name'].lower() == name), None)
        if row is None and name:
            row = next((r for r in self._model.rows() if name in r['Name'].lower()), None)
        if row is not None:
            self._tray.add(row['Id'])
            self.add_edit.clear()
        return row['Id'] if row else None

    def compare_library_view(self):
        ids = list(self._library_ids()) if self._library_ids else []
        if ids:
            self._tray.set_ids(ids)

    def focus_filter(self):
        '''Ctrl+F on this place: the Add recipe box.'''
        self.add_edit.setFocus()
        self.add_edit.selectAll()

    # --- saved comparisons -------------------------------------------

    def saved(self):
        return db.get_saved_comparisons()

    def _rebuild_saved(self):
        while self.saved_box.count():
            item = self.saved_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        rows = self.saved()
        if self._active_saved not in {r['id'] for r in rows}:
            self._active_saved = None
        active = self.active_saved()
        for r in rows:
            link = _SavedLink(r, active is not None and r['id'] == active)
            link.clicked.connect(lambda _c=False, cid=r['id']: self.load_comparison(cid))
            link.menuRequested.connect(self._saved_menu)
            self.saved_box.addWidget(link)
        self.saved_empty.setVisible(not rows)

    def active_saved(self):
        '''The saved comparison on screen, if the tray and settings still match it.'''
        if self._active_saved is None:
            return None
        row = next((r for r in self.saved() if r['id'] == self._active_saved), None)
        if row is None:
            return None
        same_ids = [i for i in row['recipe_ids'] if i in self._known_ids()] == self.recipe_ids()
        same_settings = all(row['settings'].get(k, v) == self._settings[k]
                            for k, v in compare.DEFAULT_SETTINGS.items())
        return row['id'] if same_ids and same_settings else None

    def load_comparison(self, comparison_id):
        row = next((r for r in self.saved() if r['id'] == comparison_id), None)
        if row is None:
            return
        self._active_saved = comparison_id
        self.apply_settings(row['settings'])
        known = self._known_ids()
        if not self._tray.set_ids([i for i in row['recipe_ids'] if i in known]):
            self._rebuild()

    def save_comparison(self, name=None):
        ids = self.recipe_ids()
        if not ids:
            return None
        rows = self.saved()
        if name is None:
            current = next((r['name'] for r in rows if r['id'] == self._active_saved), None)
            default = current or f'Comparison {len(rows) + 1}'
            name, ok = QInputDialog.getText(self, 'Save comparison', 'Name:', text=default)
            if not ok:
                return None
        name = name.strip()
        if not name:
            return None
        same = next((r for r in rows if r['name'].lower() == name.lower()), None)
        if same is not None:
            if same['id'] != self._active_saved and QMessageBox.question(
                    self, 'Save comparison', f'Replace the saved comparison “{same["name"]}”?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return None
            db.update_saved_comparison(same['id'], recipe_ids=ids, settings=self.settings())
            cid = same['id']
        else:
            cid = db.create_saved_comparison(name, ids, self.settings())
        self._active_saved = cid
        self._rebuild_saved()
        return cid

    def update_comparison(self, comparison_id):
        ids = self.recipe_ids()
        if not ids:
            return
        db.update_saved_comparison(comparison_id, recipe_ids=ids, settings=self.settings())
        self._active_saved = comparison_id
        self._rebuild_saved()

    def rename_comparison(self, comparison_id, name=None):
        row = next((r for r in self.saved() if r['id'] == comparison_id), None)
        if row is None:
            return
        if name is None:
            name, ok = QInputDialog.getText(self, 'Rename comparison', 'Name:', text=row['name'])
            if not ok:
                return
        name = name.strip()
        if name and name != row['name']:
            db.update_saved_comparison(comparison_id, name=name)
            self._rebuild_saved()

    def delete_comparison(self, comparison_id, confirm=True):
        row = next((r for r in self.saved() if r['id'] == comparison_id), None)
        if row is None:
            return
        if confirm and QMessageBox.question(
                self, 'Delete comparison', f'Delete the saved comparison “{row["name"]}”? The recipes stay.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_saved_comparison(comparison_id)
        self._rebuild_saved()

    def _saved_menu(self, comparison_id, pos):
        menu = QMenu(self)
        update = menu.addAction('Update with this comparison')
        update.setEnabled(bool(self.recipe_ids()))
        update.triggered.connect(lambda: self.update_comparison(comparison_id))
        menu.addAction('Rename…').triggered.connect(lambda: self.rename_comparison(comparison_id))
        menu.addAction('Delete…').triggered.connect(lambda: self.delete_comparison(comparison_id))
        menu.exec(pos)

    # --- rendering ---------------------------------------------------

    def _thumb(self, recipe_id, size):
        '''A wedge thumbnail; rendered once per refresh and reused.'''
        pix = self._thumbs.get((recipe_id, size))
        if pix is not None:
            label = QLabel()
            label.setFixedSize(size, size)
            label.setPixmap(pix)
            return label
        view = WedgeView(recipe_id, size=size, defer=True)
        view.renderComplete.connect(lambda v=view: self._thumbs.__setitem__((recipe_id, size), v.pixmap()))
        view.render_async()
        return view

    def _rebuild(self):
        ids = self.recipe_ids()
        n = len(ids)
        self.tray_heading.setText(f'COMPARE TRAY · {n}')
        by_id = {r['Id']: r for r in self._model.rows()}
        self.tray_list.set_recipes([by_id[i] for i in ids], self._thumb)
        self.subtitle.setText(f"The compare tray, expanded · {n} recipe{'s' if n != 1 else ''}")
        has = n > 0
        self.export_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        self.empty_card.setVisible(not has)
        self.chart_card.setVisible(has)
        self.table_card.setVisible(has)
        lib_n = len(list(self._library_ids())) if self._library_ids else 0
        self.library_btn.setVisible(lib_n > 0)
        self.library_btn.setText(f"Compare the {lib_n} recipe{'s' if lib_n != 1 else ''} in the Library view")
        s = self._settings
        self.data = compare.build(self._details, self._model.rows(), ids, self._categories, self._colors,
                                  metric=s['metric'], basis=s['basis'], values=s['values'])
        self.data['target'] = food_cost.target_percent()
        for link in self._saved_links():
            link.set_active(link.comparison_id == self.active_saved())
        if not has:
            return
        label = compare.metric_info(s['metric'])[1]
        what = 'share of ' + label.lower() if s['values'] == 'pct' else label
        self.chart_title.setText(f"{what[0].upper() + what[1:]} {compare.basis_label(s['basis']).lower()},"
                                 ' by category')
        self._rebuild_legend()
        self.chart.set_data(self.data)
        self.insight.setText(compare.insight(self.data))
        self.insight.setVisible(bool(self.insight.text()))
        self._rebuild_table()

    def _saved_links(self):
        return [self.saved_box.itemAt(i).widget() for i in range(self.saved_box.count())
                if isinstance(self.saved_box.itemAt(i).widget(), _SavedLink)]

    def _rebuild_legend(self):
        while self.legend.count():
            item = self.legend.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for name, color in self.data['categories']:
            chip = QLabel(f'<span style="color: {color}; font-size: 14px;">■</span> {name}')
            chip.setStyleSheet(f'color: {kit.MUTED}; font-size: 12px;')
            self.legend.addWidget(chip)

    def _rebuild_table(self):
        recipes = self.data['recipes']
        rows = compare.matrix(self.data)
        t = self.table
        t.clearSpans()
        t.clear()
        t.setColumnCount(1 + len(recipes))
        t.setRowCount(len(rows))
        head = QTableWidgetItem(compare.basis_label(self.data['basis']).upper())
        head.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        head.setForeground(QColor(kit.MUTED))
        t.setHorizontalHeaderItem(0, head)
        for c, r in enumerate(recipes, start=1):
            item = QTableWidgetItem(r['name'])
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item.setToolTip(f"{r['name']} · double-click to open")
            t.setHorizontalHeaderItem(c, item)
        bold = t.font()
        bold.setBold(True)
        for i, row in enumerate(rows):
            kind = row['kind']
            if kind == 'section':
                item = QTableWidgetItem(row['label'].upper())
                item.setForeground(QColor(kit.MUTED))
                f = t.font()
                f.setPixelSize(11)
                f.setBold(True)
                item.setFont(f)
                t.setItem(i, 0, item)
                t.setSpan(i, 0, 1, t.columnCount())
                t.setRowHeight(i, 36)
                continue
            label = QTableWidgetItem(row['label'])
            if kind == 'category':
                label.setIcon(_swatch(row['color']))
            if kind in ('total',):
                label.setFont(bold)
            t.setItem(i, 0, label)
            highest = None
            nums = [v for v in row['values'] if v is not None]
            if kind in ('category', 'nutrient') and len(nums) >= 2 and max(nums) > min(nums):
                highest = max(nums)
            for c, text in enumerate(row['text'], start=1):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                value = row['values'][c - 1]
                if text == '—' or (kind == 'price' and value is None):
                    item.setForeground(QColor(kit.MUTED))
                if kind == 'total' or (highest is not None and value == highest):
                    item.setFont(bold)
                if kind == 'price' and row['warn'][c - 1]:
                    item.setText('▲ ' + text)
                    item.setForeground(QColor(kit.WARN))
                    item.setBackground(QColor(_WARN_BG))
                    item.setFont(bold)
                    item.setToolTip(f'Food cost over the {food_cost.target_percent():.0f}% target')
                if kind == 'category' and value is not None:
                    item.setToolTip(self._cell_tip(recipes[c - 1], row['label']))
                if kind in ('total', 'price'):
                    item.setBackground(item.background() if kind == 'price' and row['warn'][c - 1]
                                       else QColor(kit.BG))
                t.setItem(i, c, item)
            if kind in ('total', 'price'):
                label.setBackground(QColor(kit.BG))
            t.setRowHeight(i, 34 if kind == 'total' else 30)
        hh = t.horizontalHeader()
        hh.setMinimumSectionSize(90)
        if len(recipes) <= 6:
            hh.setSectionResizeMode(QHeaderView.Stretch)
        else:
            hh.setSectionResizeMode(QHeaderView.Interactive)
            t.resizeColumnsToContents()
        height = hh.sizeHint().height() + sum(t.rowHeight(i) for i in range(t.rowCount())) + 4
        if t.horizontalScrollBar().maximum() > 0 or len(recipes) > 6:
            height += t.horizontalScrollBar().sizeHint().height()
        t.setFixedHeight(height)

    def _cell_tip(self, recipe, category):
        lines = [f"{recipe['name']} · {category}"]
        for name, value in recipe['items'].get(category, []):
            if value is not None:
                lines.append(f"  {name}: {compare.fmt_metric(value, self.data['metric'])}")
        return '\n'.join(lines)

    def _on_header_double_clicked(self, section):
        if section >= 1 and self.data and section - 1 < len(self.data['recipes']):
            self.recipeActivated.emit(self.data['recipes'][section - 1]['id'])

    # --- export ------------------------------------------------------

    def export_csv(self, path=None):
        if not self.data or not self.data['recipes']:
            return None
        if path is None:
            start = QSettings().value('analytics/exportDir', '', type=str) or QStandardPaths.writableLocation(
                QStandardPaths.DocumentsLocation)
            name = next((r['name'] for r in self.saved() if r['id'] == self.active_saved()), 'Comparison')
            path, _ = QFileDialog.getSaveFileName(self, 'Export comparison', os.path.join(start, f'{name}.csv'),
                                                  'CSV files (*.csv)')
            if not path:
                return None
            QSettings().setValue('analytics/exportDir', os.path.dirname(path))
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerows(compare.csv_rows(self.data))
        return path


def _swatch(color):
    pix = QPixmap(4, 16)
    pix.fill(QColor(color))
    return QIcon(pix)


class _TrayList(QWidget):
    '''The tray's recipes as rows (wedge, name, ×). Drag a row to reorder;
    double-click opens the recipe.'''

    activated = Signal(int)

    def __init__(self, tray, parent=None):
        super().__init__(parent)
        self._tray = tray
        self.setAcceptDrops(True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self.rows = []

    def set_recipes(self, recipes, thumb):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.rows = []
        for r in recipes:
            row = _TrayRow(r, thumb(r['Id'], 36))
            row.removeClicked.connect(self._tray.remove)
            row.activated.connect(self.activated.emit)
            self._layout.addWidget(row)
            self.rows.append(row)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event):
        rid = int(bytes(event.mimeData().data(_MIME)).decode())
        y = event.position().y()
        index = sum(1 for row in self.rows if row.recipe_id != rid and row.geometry().center().y() < y)
        self._tray.move(rid, index)
        event.acceptProposedAction()


class _TrayRow(QFrame):
    removeClicked = Signal(int)
    activated = Signal(int)

    def __init__(self, recipe, thumb, parent=None):
        super().__init__(parent)
        self.recipe_id = recipe['Id']
        self._press = None
        self.setObjectName('TrayRow')
        self.setStyleSheet(f'QFrame#TrayRow {{ background: #ffffff; border: 1px solid {kit.BORDER};'
                           ' border-radius: 8px; }')
        self.setToolTip('Double-click to open · drag to reorder')
        archived = recipe.get('Archived')
        name = ElidedLabel(recipe['Name'] + (' · archived' if archived else ''))
        name.setStyleSheet(f'color: {kit.MUTED if archived else kit.KALE}; border: 0;')
        remove = QToolButton()
        remove.setText('×')
        remove.setAutoRaise(True)
        remove.setCursor(Qt.PointingHandCursor)
        remove.setToolTip(f"Remove {recipe['Name']}")
        remove.setStyleSheet(f'QToolButton {{ border: 0; color: {kit.MUTED}; font-size: 16px; }}')
        remove.clicked.connect(lambda: self.removeClicked.emit(self.recipe_id))
        self.remove_btn = remove
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)
        layout.addWidget(thumb)
        layout.addWidget(name, stretch=1)
        layout.addWidget(remove)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and (event.position().toPoint() - self._press).manhattanLength() > 8:
            self._press = None
            mime = QMimeData()
            mime.setData(_MIME, str(self.recipe_id).encode())
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.setPixmap(self.grab())
            drag.setHotSpot(QPoint(20, self.height() // 2))
            drag.exec(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.activated.emit(self.recipe_id)
        super().mouseDoubleClickEvent(event)


class _SavedLink(QPushButton):
    menuRequested = Signal(int, QPoint)

    def __init__(self, row, active, parent=None):
        super().__init__(row['name'], parent)
        self.comparison_id = row['id']
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        n = len(row['recipe_ids'])
        self.setToolTip(f"{n} recipe{'s' if n != 1 else ''} · right-click to update, rename or delete")
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menuRequested.emit(self.comparison_id, self.mapToGlobal(pos)))
        self.set_active(active)

    def set_active(self, active):
        self.active = active
        weight = 600 if active else 400
        bg = kit.SELECTED if active else 'transparent'
        self.setStyleSheet(f'QPushButton {{ text-align: left; border: 0; border-radius: 6px; padding: 5px 8px;'
                           f' color: {kit.KALE}; font-weight: {weight}; background: {bg}; }}'
                           f' QPushButton:hover {{ color: {kit.ROMAINE_HOVER}; text-decoration: underline; }}')
