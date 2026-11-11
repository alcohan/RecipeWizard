'''Analytics: recipes side by side, as tables.

Left, the compare set: the tray's recipes (wedge, name, ×; drag to
reorder), an "Add recipe…" box, Template and Tag filters, and saved
comparisons (click to open; right-click to update, rename or delete).
An empty tray means every active recipe; the filters narrow whichever
set is showing, and Clear all resets both.

Right, one of three views of that set: Pricing (ingredients, cost by
category, cost, menu price, food cost %), Nutrition (per serving, with
allergens) and Scenarios. Export CSV writes the view on screen and
Print prints the recipes shown. The tray and filters are remembered
between sessions; Save comparison keeps a named copy in the library.
'''
import csv
import os

from PySide6.QtCore import QMimeData, QPoint, QSettings, QStandardPaths, Qt, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QCompleter, QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

import db
from gui.services.compare_tray import CompareTray
from gui.widgets import config_kit as kit
from gui.widgets.elided_label import ElidedLabel
from gui.widgets.recipe_matrix import RecipeMatrix
from gui.widgets.scenario_matrix import ScenarioMatrix
from gui.widgets.text_fit import literal
from gui.widgets.toolbar_controls import SegmentedSwitch, ToolbarCombo
from gui.widgets.wedge_view import WedgeView
from utilities import compare


_MIME = 'application/x-recipewizard-tray-id'
_NO_TEMPLATE = -1       # the Template filter's "Sub-recipes" (no template)
VIEWS = [('pricing', 'Pricing'), ('nutrition', 'Nutrition'), ('scenarios', 'Scenarios')]


def _scroll(widget):
    area = QScrollArea()
    area.setWidget(widget)
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.NoFrame)
    area.setStyleSheet(f'QScrollArea {{ background: {kit.BG}; }}'
                       ' QScrollArea > QWidget > QWidget { background: transparent; }')
    return area


class AnalyticsTab(QWidget):
    recipeActivated = Signal(int)
    printRequested = Signal(list, bool)     # recipe ids, with portions
    scenarioSetupRequested = Signal()

    def __init__(self, recipes_model, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._tray = CompareTray(self)
        saved_ids = QSettings().value('analytics/trayIds', '', type=str) or ''
        self._tray.set_ids([int(x) for x in saved_ids.split(',') if x.strip().isdigit()])
        self._details = []
        self._categories = []
        self._colors = {}
        self._formats = []
        self._thumbs = {}
        self._active_saved = None
        self._stale = True
        self.data = None
        settings = QSettings()
        self._filters = {'format': settings.value('analytics/format', 0, type=int) or None,
                         'tag': settings.value('analytics/tag', 0, type=int) or None}

        self.setStyleSheet(f'AnalyticsTab {{ background: {kit.BG}; }}')
        self.setAttribute(Qt.WA_StyledBackground, True)

        # Title bar.
        self.subtitle = QLabel('')
        self.subtitle.setStyleSheet(f'color: {kit.MUTED};')
        self.export_btn = kit.button('Export CSV')
        self.export_btn.clicked.connect(lambda: self.export_csv())
        self.print_btn = QToolButton()
        self.print_btn.setText('Print…')
        self.print_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self.print_btn.setCursor(Qt.PointingHandCursor)
        self.print_btn.setStyleSheet(kit.button('').styleSheet().replace('QPushButton', 'QToolButton')
                                     + ' QToolButton { padding-right: 22px; }'
                                       ' QToolButton::menu-button { border: 0; width: 18px; }')
        self.print_btn.clicked.connect(lambda: self.print_shown(portions=True))
        print_menu = QMenu(self.print_btn)
        print_menu.addAction('Print without portions…', lambda: self.print_shown(portions=False))
        self.print_btn.setMenu(print_menu)
        self.save_btn = kit.button('Save comparison', primary=True)
        self.save_btn.clicked.connect(lambda: self.save_comparison())
        self.view_switch = SegmentedSwitch(VIEWS)
        self.view_switch.changed.connect(self.set_view)
        bar = QFrame()
        bar.setObjectName('AnalyticsBar')
        bar.setStyleSheet(f'QFrame#AnalyticsBar {{ background: #ffffff; border-bottom: 1px solid {kit.BORDER}; }}')
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(20, 10, 20, 10)
        bl.setSpacing(16)
        bl.addWidget(kit.heading('Analytics'))
        bl.addWidget(self.view_switch)
        bl.addWidget(self.subtitle)
        bl.addStretch()
        bl.addWidget(self.export_btn)
        bl.addWidget(self.print_btn)
        bl.addWidget(self.save_btn)

        # Compare set (left).
        self.tray_heading = kit.eyebrow('Compare tray')
        self.clear_btn = QToolButton()
        self.clear_btn.setText('Clear all')
        self.clear_btn.setCursor(Qt.PointingHandCursor)
        self.clear_btn.setToolTip('Empty the tray and reset the filters')
        self.clear_btn.setStyleSheet(f'QToolButton {{ border: 0; color: {kit.ROMAINE}; padding: 0; }}'
                                     f' QToolButton:hover {{ color: {kit.ROMAINE_HOVER}; text-decoration: underline; }}')
        self.clear_btn.clicked.connect(self.clear_all)
        tray_head = QHBoxLayout()
        tray_head.setContentsMargins(0, 0, 0, 0)
        tray_head.addWidget(self.tray_heading)
        tray_head.addStretch()
        tray_head.addWidget(self.clear_btn)
        self.tray_note = kit.note('Empty: showing all active recipes')
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
        self.format_combo = ToolbarCombo()
        self.format_combo.activated.connect(lambda _i: self.set_filter('format', self.format_combo.currentData()))
        self.tag_combo = ToolbarCombo()
        self.tag_combo.activated.connect(lambda _i: self.set_filter('tag', self.tag_combo.currentData()))
        self.saved_box = QVBoxLayout()
        self.saved_box.setSpacing(2)
        self.saved_empty = kit.note('None yet')

        aside = QWidget()
        aside.setFixedWidth(250)
        al = QVBoxLayout(aside)
        al.setContentsMargins(16, 20, 16, 20)
        al.setSpacing(6)
        al.addLayout(tray_head)
        al.addWidget(self.tray_note)
        al.addWidget(self.tray_list)
        al.addWidget(self.add_edit)
        al.addSpacing(16)
        al.addWidget(kit.eyebrow('Filter'))
        al.addWidget(self.format_combo)
        al.addWidget(self.tag_combo)
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

        # The views.
        self.pricing = RecipeMatrix('pricing')
        self.nutrition = RecipeMatrix('nutrition')
        self.scenarios = ScenarioMatrix()
        self.scenarios.setupRequested.connect(self.scenarioSetupRequested.emit)
        self.scenarios.refreshed.connect(self._sync_export)
        self._empty_notes = {}
        self.views = QStackedWidget()
        for key, widget in (('pricing', self.pricing), ('nutrition', self.nutrition), ('scenarios', self.scenarios)):
            widget.recipeActivated.connect(self.recipeActivated.emit)
            empty = kit.note('')
            empty.setVisible(False)
            self._empty_notes[key] = empty
            host = QWidget()
            hl = QVBoxLayout(host)
            hl.setContentsMargins(28, 20, 28, 28)
            hl.setSpacing(12)
            hl.addWidget(empty)
            hl.addWidget(widget)
            hl.addStretch()
            self.views.addWidget(_scroll(host))

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(aside_scroll)
        body.addWidget(self.views, stretch=1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(bar)
        layout.addLayout(body, stretch=1)
        self._view = 'pricing'
        self.set_view(QSettings().value('analytics/view', 'pricing', type=str))

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
        self.scenarios.mark_stale()
        if self.isVisible():
            self.refresh()

    def _prune_tray(self):
        '''Drop recipes that no longer exist (deleted, or a restored or
        reset library), quietly: the rebuild that follows shows it.'''
        known = self._known_ids()
        ids = self._tray.ids()
        if any(i not in known for i in ids):
            self._tray.blockSignals(True)
            self._tray.set_ids([i for i in ids if i in known])
            self._tray.blockSignals(False)
            self._save_tray()

    def _save_tray(self):
        QSettings().setValue('analytics/trayIds', ','.join(str(i) for i in self._tray.ids()))

    def refresh(self):
        '''Re-read the library (details, categories, filters, saved comparisons).'''
        self._stale = False
        self._details = db.get_recipe_category_details()
        tags = db.get_tags('ingredient')
        self._categories = compare.category_order(tags)
        self._colors = {t['name']: t.get('color') or '#888888' for t in tags}
        self._colors.setdefault(compare.UNCATEGORIZED, '#888888')
        self._formats = db.get_tags(kind='recipe')
        self._recipe_tags = db.get_tags(kind='recipe_tag')
        self._prune_tray()
        self._fill_filters()
        self._completer.model().setStringList(sorted((r['Name'] for r in self._model.rows()), key=str.lower))
        self._rebuild_saved()
        self._rebuild()

    # --- views ---------------------------------------------------------

    def view(self):
        return self._view

    def set_view(self, key):
        '''"pricing", "nutrition" or "scenarios".'''
        keys = [k for k, _l in VIEWS]
        key = key if key in keys else 'pricing'
        self._view = key
        QSettings().setValue('analytics/view', key)
        self.view_switch.set_current(key)
        self.views.setCurrentIndex(keys.index(key))
        self._sync_export()

    def matrix(self):
        '''The Pricing or Nutrition table on screen (None on Scenarios).'''
        return {'pricing': self.pricing, 'nutrition': self.nutrition}.get(self._view)

    def _sync_export(self):
        if self._view == 'scenarios':
            self.export_btn.setEnabled(self.scenarios.has_scenarios() and bool(self.scenarios.visible_recipes()))
            self.export_btn.setToolTip('Save the scenarios table as a CSV file')
        else:
            self.export_btn.setEnabled(bool(self.data and self.data['recipes']))
            self.export_btn.setToolTip(f'Save the {self._view} table as a CSV file')

    def _on_tray_changed(self):
        self._save_tray()
        if self.isVisible() and not self._stale:
            self._rebuild()
        else:
            # Rebuilt when Analytics is next shown.
            self._stale = True

    # --- filters -----------------------------------------------------

    def _fill_filters(self):
        for combo, first, items, key in (
                (self.format_combo, 'All templates',
                 [(t['id'], t['name']) for t in self._formats] + [(_NO_TEMPLATE, 'Sub-recipes')], 'format'),
                (self.tag_combo, 'Any tag', [(t['id'], t['name']) for t in self._recipe_tags], 'tag')):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem(first, None)
            for tid, name in items:
                combo.addItem(literal(name), tid)
            index = combo.findData(self._filters[key]) if self._filters[key] is not None else 0
            if index < 0:
                self._filters[key] = None
                index = 0
            combo.setCurrentIndex(index)
            combo.blockSignals(False)

    def filters(self):
        return dict(self._filters)

    def set_filter(self, key, value):
        value = value or None
        if self._filters.get(key) == value:
            return
        self._filters[key] = value
        QSettings().setValue(f'analytics/{key}', value or 0)
        combo = self.format_combo if key == 'format' else self.tag_combo
        combo.blockSignals(True)
        combo.setCurrentIndex(max(0, combo.findData(value)) if value is not None else 0)
        combo.blockSignals(False)
        self._rebuild()

    def _passes(self, row):
        fmt, tag = self._filters['format'], self._filters['tag']
        if fmt is not None:
            if fmt == _NO_TEMPLATE:
                if row.get('TagName'):
                    return False
            else:
                name = next((t['name'] for t in self._formats if t['id'] == fmt), None)
                if row.get('TagName') != name:
                    return False
        if tag is not None and tag not in (row.get('TagIds') or set()):
            return False
        return True

    def clear_all(self):
        '''Empty the tray and reset the filters.'''
        self._active_saved = None
        for key in ('format', 'tag'):
            self._filters[key] = None
            QSettings().setValue(f'analytics/{key}', 0)
        self.format_combo.setCurrentIndex(0)
        self.tag_combo.setCurrentIndex(0)
        if not self._tray.clear():
            self._rebuild()

    # --- tray --------------------------------------------------------

    def _known_ids(self):
        return {r['Id'] for r in self._model.rows()}

    def recipe_ids(self):
        '''The tray's recipes that still exist, in tray order.'''
        known = self._known_ids()
        return [rid for rid in self._tray.ids() if rid in known]

    def shown_ids(self):
        '''What the views show: the tray (or, when it's empty, every
        active recipe), after the filters.'''
        by_id = {r['Id']: r for r in self._model.rows()}
        ids = self.recipe_ids() or [r['Id'] for r in self._model.rows() if not r.get('Archived')]
        return [rid for rid in ids if self._passes(by_id[rid])]

    def add_by_name(self, name):
        name = (name or '').strip().lower()
        row = next((r for r in self._model.rows() if r['Name'].lower() == name), None)
        if row is None and name:
            row = next((r for r in self._model.rows() if name in r['Name'].lower()), None)
        if row is not None:
            self._tray.add(row['Id'])
            self.add_edit.clear()
        return row['Id'] if row else None

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

    def _saved_filters(self, row):
        settings = row.get('settings') or {}
        return {k: (settings.get(k) or None) for k in ('format', 'tag')}

    def active_saved(self):
        '''The saved comparison on screen, if the tray and filters still match it.'''
        if self._active_saved is None:
            return None
        row = next((r for r in self.saved() if r['id'] == self._active_saved), None)
        if row is None:
            return None
        same_ids = [i for i in row['recipe_ids'] if i in self._known_ids()] == self.recipe_ids()
        return row['id'] if same_ids and self._saved_filters(row) == self._filters else None

    def _can_save(self):
        return bool(self.recipe_ids()) or any(v is not None for v in self._filters.values())

    def load_comparison(self, comparison_id):
        row = next((r for r in self.saved() if r['id'] == comparison_id), None)
        if row is None:
            return
        self._active_saved = comparison_id
        for key, value in self._saved_filters(row).items():
            self._filters[key] = value
            QSettings().setValue(f'analytics/{key}', value or 0)
        self._fill_filters()
        known = self._known_ids()
        if not self._tray.set_ids([i for i in row['recipe_ids'] if i in known]):
            self._rebuild()

    def save_comparison(self, name=None):
        if not self._can_save():
            return None
        ids = self.recipe_ids()
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
            db.update_saved_comparison(same['id'], recipe_ids=ids, settings=self.filters())
            cid = same['id']
        else:
            cid = db.create_saved_comparison(name, ids, self.filters())
        self._active_saved = cid
        self._rebuild_saved()
        return cid

    def update_comparison(self, comparison_id):
        if not self._can_save():
            return
        db.update_saved_comparison(comparison_id, recipe_ids=self.recipe_ids(), settings=self.filters())
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
        update.setEnabled(self._can_save())
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
        by_id = {r['Id']: r for r in self._model.rows()}
        self.tray_heading.setText(f'COMPARE TRAY · {len(ids)}' if ids else 'COMPARE TRAY')
        self.tray_list.set_recipes([by_id[i] for i in ids], self._thumb)
        self.tray_list.setVisible(bool(ids))
        self.tray_note.setVisible(not ids)
        filtered = any(v is not None for v in self._filters.values())
        self.clear_btn.setVisible(bool(ids) or filtered)
        shown = self.shown_ids()
        n = len(shown)
        self.subtitle.setText(f"{n} recipe{'s' if n != 1 else ''}")
        self.save_btn.setEnabled(self._can_save())
        self.print_btn.setEnabled(bool(n))
        self.print_btn.setToolTip(f"Print the {n} recipe{'s' if n != 1 else ''} shown" if n else '')
        self.data = compare.build(self._details, self._model.rows(), shown, self._categories)
        self.pricing.set_data(self.data, self._colors)
        self.nutrition.set_data(self.data, self._colors)
        self.scenarios.set_recipe_ids(shown)
        if n:
            message = ''
        elif filtered:
            message = 'No recipes match the filters.'
        else:
            message = 'No recipes yet.'
        for key, note in self._empty_notes.items():
            note.setText(message)
            note.setVisible(bool(message))
        self.pricing.setVisible(bool(n))
        self.nutrition.setVisible(bool(n))
        for link in self._saved_links():
            link.set_active(link.comparison_id == self.active_saved())
        self._sync_export()

    def _saved_links(self):
        return [self.saved_box.itemAt(i).widget() for i in range(self.saved_box.count())
                if isinstance(self.saved_box.itemAt(i).widget(), _SavedLink)]

    # --- print -------------------------------------------------------

    def print_shown(self, portions=True):
        '''Print the recipes the view shows (the tray, or every active
        recipe, after the filters).'''
        ids = self.shown_ids()
        if ids:
            self.printRequested.emit(ids, bool(portions))
        return ids

    # --- export ------------------------------------------------------

    def export_csv(self, path=None):
        if self._view == 'scenarios':
            rows = self.scenarios.csv_rows()
            name = 'Scenarios'
        else:
            rows = self.matrix().csv_rows() if self.data and self.data['recipes'] else []
            saved = next((r['name'] for r in self.saved() if r['id'] == self.active_saved()), None)
            name = f"{saved} · {self._view.title()}" if saved else self._view.title()
        if not rows:
            return None
        if path is None:
            start = QSettings().value('analytics/exportDir', '', type=str) or QStandardPaths.writableLocation(
                QStandardPaths.DocumentsLocation)
            path, _ = QFileDialog.getSaveFileName(self, 'Export CSV', os.path.join(start, f'{name}.csv'),
                                                  'CSV files (*.csv)')
            if not path:
                return None
            QSettings().setValue('analytics/exportDir', os.path.dirname(path))
        with open(path, 'w', newline='', encoding='utf-8-sig') as f:
            csv.writer(f).writerows(rows)
        return path


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
        self.setToolTip(f"{n} recipe{'s' if n != 1 else ''}")
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
