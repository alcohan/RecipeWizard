'''Recipe gallery for the Library, per the Framework canvas: cards
grouped by format ("Bowls 4", "Salads 4", … then Sub-recipes), each
with its wedge, name and cost, calories and food cost, and diet chips.

Single click selects (the Library's inspector follows), double-click
opens the recipe in a tab, right-click asks for the context menu. The
compare checkbox on each card adds it to the tray.

The gallery filters with the Library proxy's accepts_row and orders
cards within each group by the Sort menu's key, so it always shows the
same recipes as the table. Cards are kept per recipe across model
refreshes; a refresh updates their text and re-renders the wedge in
the background, keeping the old one until the new one arrives.
'''
from PySide6.QtCore import QPoint, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea,
    QVBoxLayout, QWidget,
)

import db
from gui.models.recipes_model import SORTS
from gui.widgets.wedge_view import WedgeView
from utilities.diets import DIET_NAMES


_KALE = '#082c00'
_ROMAINE = '#347200'
_MUTED = '#55624c'
_BORDER = '#ebe1cd'
_WARN_FG, _WARN_BG = '#8a4a00', '#fff0dc'
FOOD_COST_TARGET = 28.0
_MAX_CHIPS = 3
SUB_RECIPE_GROUP = 'Sub-recipes'


def _prices_drifted(cost_raw, cost_snapshot, min_delta=0.01):
    '''True when the current cost differs from the snapshot by at
    least min_delta. Both NULL (never snapshotted) counts as "no
    drift" — no sense in flagging recipes the user has never opened.'''
    try:
        a = float(cost_raw) if cost_raw is not None else None
        b = float(cost_snapshot) if cost_snapshot is not None else None
    except (TypeError, ValueError):
        return False
    if a is None or b is None:
        return False
    return abs(a - b) >= min_delta


def food_cost_text(row):
    '''("24.5% of $13.95", over_target) or ("No menu price", False).'''
    pct = row.get('FoodCostPct')
    if pct is None:
        return 'No menu price', False
    if pct > FOOD_COST_TARGET:
        return f'{pct:.1f}% · over target', True
    return f'{pct:.1f}% of ${float(row["MenuPrice"]):.2f}', False


def group_title(name):
    '''"Bowls" for Bowl; names that don't take an s (Catering) stay.'''
    if name and not name.endswith(('s', 'ing')) and name != SUB_RECIPE_GROUP:
        name += 's'
    return name


def chip(text, fg=_KALE, bg='#f3ece0'):
    lbl = QLabel(text)
    lbl.setStyleSheet(f'color: {fg}; background: {bg}; border-radius: 9px; padding: 1px 8px;'
                      ' font-size: 11px; font-weight: 600;')
    return lbl


class RecipeCard(QFrame):
    '''One recipe. Children are transparent to the mouse so the frame
    gets every click; the compare checkbox is the exception.'''

    clicked = Signal(int)
    activated = Signal(int)
    contextRequested = Signal(int, QPoint)

    WIDTH, HEIGHT = 216, 240

    def __init__(self, row, compare_tray=None, parent=None):
        super().__init__(parent)
        self.recipe_id = row['Id']
        self._compare_tray = compare_tray
        self._wedge_ready = False
        self.setObjectName('RecipeCard')
        self.setProperty('selected', False)
        self.setStyleSheet(f'''
            QFrame#RecipeCard {{ background: #ffffff; border: 1px solid {_BORDER}; border-radius: 8px; }}
            QFrame#RecipeCard:hover {{ border-color: #7d8771; }}
            QFrame#RecipeCard[selected="true"] {{ border: 2px solid {_ROMAINE}; background: #f6f9ef; }}
            QFrame#RecipeCard QLabel {{ border: 0; background: transparent; }}
        ''')
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(self.WIDTH, self.HEIGHT)

        self.wedge = WedgeView(self.recipe_id, size=128, defer=True)
        self.wedge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.wedge.renderComplete.connect(self._on_wedge_ready)

        self.name_label = QLabel()
        self.name_label.setStyleSheet(f'color: {_KALE}; font-weight: 650; font-size: 14px;')
        self.cost_label = QLabel()
        self.cost_label.setStyleSheet(f'color: {_KALE}; font-weight: 650; font-size: 14px;')
        self.kcal_label = QLabel()
        self.kcal_label.setStyleSheet(f'color: {_MUTED}; font-size: 12px;')
        self.food_label = QLabel()
        self.chips = QHBoxLayout()
        self.chips.setContentsMargins(0, 0, 0, 0)
        self.chips.setSpacing(4)
        for w in (self.name_label, self.cost_label, self.kcal_label, self.food_label):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)

        top = QHBoxLayout()
        top.setSpacing(8)
        top.addWidget(self.name_label, stretch=1)
        top.addWidget(self.cost_label)
        mid = QHBoxLayout()
        mid.setSpacing(8)
        mid.addWidget(self.kcal_label)
        mid.addStretch()
        mid.addWidget(self.food_label)
        chips_wrap = QWidget()
        chips_wrap.setAttribute(Qt.WA_TransparentForMouseEvents)
        chips_wrap.setLayout(self.chips)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self.wedge, alignment=Qt.AlignHCenter)
        layout.addSpacing(4)
        layout.addLayout(top)
        layout.addLayout(mid)
        layout.addWidget(chips_wrap)
        layout.addStretch()

        if self._compare_tray is not None:
            self.tray_check = QCheckBox(self)
            self.tray_check.setToolTip('Add to compare (Space)')
            self.tray_check.setCursor(Qt.PointingHandCursor)
            self.tray_check.setStyleSheet(f'''
                QCheckBox {{ background: transparent; padding: 0; }}
                QCheckBox::indicator {{ width: 16px; height: 16px; border: 1.5px solid {_KALE};
                    border-radius: 3px; background: #ffffff; }}
                QCheckBox::indicator:hover {{ border-color: {_ROMAINE}; }}
                QCheckBox::indicator:checked {{ background: {_ROMAINE}; border-color: {_ROMAINE}; image: none; }}
            ''')
            self.tray_check.setFixedSize(20, 20)
            self.tray_check.move(10, 10)
            self.tray_check.setChecked(self._compare_tray.contains(self.recipe_id))
            self.tray_check.toggled.connect(self._on_tray_toggled)
            self._compare_tray.changed.connect(self._sync_tray_check)

        self.drift_chip = QLabel('Prices changed', self)
        self.drift_chip.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.drift_chip.setStyleSheet(f'background: {_WARN_BG}; color: {_WARN_FG}; font-size: 10px;'
                                      ' font-weight: 600; padding: 2px 6px; border-radius: 4px;')
        self.drift_chip.setToolTip('Costs have changed since this recipe was last saved.')
        self.drift_chip.adjustSize()
        self.drift_chip.move(self.WIDTH - self.drift_chip.width() - 10, 10)
        self.set_row(row)

    def set_row(self, row):
        self.row = row
        name = row['Name'] or ''
        metrics = self.name_label.fontMetrics()
        self.name_label.setText(metrics.elidedText(name, Qt.ElideRight, self.WIDTH - 24 - 64))
        self.name_label.setToolTip(name)
        self.setToolTip(name)
        self.cost_label.setText(f'${float(row.get("CostRaw") or 0):.2f}')
        self.kcal_label.setText(f'{row.get("CaloriesPerServing", 0):.0f} kcal')
        text, over = food_cost_text(row)
        self.food_label.setText(('▲ ' if over else '') + text)
        self.food_label.setStyleSheet(
            f'color: {_WARN_FG}; font-size: 12px; font-weight: 600;' if over
            else f'color: {_MUTED}; font-size: 12px;')
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        diets = row.get('Diets') or []
        for key in diets[:_MAX_CHIPS]:
            self.chips.addWidget(chip(DIET_NAMES[key], fg='#24502A', bg='#E6EFE3'))
        if len(diets) > _MAX_CHIPS:
            more = chip(f'+{len(diets) - _MAX_CHIPS}', fg=_MUTED)
            more.setToolTip(', '.join(DIET_NAMES[k] for k in diets[_MAX_CHIPS:]))
            self.chips.addWidget(more)
        self.chips.addStretch()
        self.drift_chip.setVisible(_prices_drifted(row.get('CostRaw'), row.get('CostSnapshot')))

    def set_selected(self, selected):
        if self.property('selected') != selected:
            self.setProperty('selected', selected)
            self.style().unpolish(self)
            self.style().polish(self)

    def start_render(self, pool):
        self.wedge.render_async(pool)

    def _on_wedge_ready(self):
        if not self._wedge_ready:
            self._wedge_ready = True
            gallery = self.parent()
            while gallery is not None and not isinstance(gallery, RecipeGallery):
                gallery = gallery.parent()
            if gallery is not None:
                gallery._reveal_if_ready(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.recipe_id)
        elif event.button() == Qt.RightButton:
            self.clicked.emit(self.recipe_id)
            self.contextRequested.emit(self.recipe_id, event.globalPosition().toPoint())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.recipe_id)
        super().mouseDoubleClickEvent(event)

    def _on_tray_toggled(self, checked):
        if self._compare_tray is None:
            return
        if checked:
            self._compare_tray.add(self.recipe_id)
        else:
            self._compare_tray.remove(self.recipe_id)

    def _sync_tray_check(self):
        '''Keep the checkbox in sync when another view changes the tray.'''
        if self._compare_tray is None:
            return
        should_be = self._compare_tray.contains(self.recipe_id)
        if self.tray_check.isChecked() != should_be:
            self.tray_check.blockSignals(True)
            self.tray_check.setChecked(should_be)
            self.tray_check.blockSignals(False)


class _Group(QWidget):
    '''"Bowls 4" header over a grid of cards.'''

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = QLabel()
        self.title.setTextFormat(Qt.RichText)
        self.title.setStyleSheet(f'color: {_KALE}; font-size: 16px; font-weight: 650;')
        self.grid = QGridLayout()
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(RecipeGallery.CARD_SPACING)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.title)
        layout.addLayout(self.grid)

    def set_title(self, name, n):
        self.title.setText(f'{group_title(name)}'
                           f' <span style="color: {_MUTED}; font-weight: 400">{n}</span>')


class RecipeGallery(QWidget):
    CARD_SPACING = 12
    SCROLLBAR_RESERVE = 24  # avoid column-count oscillation at the threshold

    recipeClicked = Signal(int)
    recipeActivated = Signal(int)
    contextMenuRequested = Signal(int, QPoint)

    def __init__(self, recipes_model, compare_tray=None, parent=None):
        super().__init__(parent)
        self._model = recipes_model
        self._compare_tray = compare_tray
        self._cards = {}           # recipe id → RecipeCard
        self._groups = {}          # format name → _Group
        self._accepts = lambda _row: True
        self._sort = 'name'
        self._selected_id = None
        self._current_columns = 4
        self._order = []           # recipe ids as laid out (for keyboard / tests)
        self._format_rank = {}

        self.container = QWidget()
        self.container.setObjectName('GalleryHost')
        self.container.setStyleSheet('QWidget#GalleryHost { background: #fffaf2; }')
        self._vbox = QVBoxLayout(self.container)
        self._vbox.setContentsMargins(20, 16, 20, 20)
        self._vbox.setSpacing(24)
        self._empty = QLabel('No recipes match these filters.')
        self._empty.setStyleSheet(f'color: {_MUTED};')
        self._vbox.addWidget(self._empty)
        self._vbox.addStretch()

        self.scroll = QScrollArea()
        self.scroll.setWidget(self.container)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.scroll)

        self._model.modelReset.connect(self.refresh)
        self.refresh()

    # --- configuration -------------------------------------------------

    def set_row_filter(self, accepts):
        self._accepts = accepts
        self._relayout()

    def set_sort(self, key):
        self._sort = key
        self._relayout()

    def set_selected_id(self, recipe_id):
        self._selected_id = recipe_id
        for rid, card in self._cards.items():
            card.set_selected(rid == recipe_id)
        card = self._cards.get(recipe_id)
        if card is not None and card.isVisible():
            self.scroll.ensureWidgetVisible(card, 0, 12)

    def visible_ids(self):
        return list(self._order)

    # --- layout --------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_columns()

    def showEvent(self, event):
        '''Recompute columns on every show, deferred: the viewport hasn't
        settled to its final width yet when a stacked page is shown.'''
        super().showEvent(event)
        QTimer.singleShot(0, self._sync_columns)

    def _sync_columns(self):
        new_cols = self._columns_for_width(self.scroll.viewport().width() - 40)
        if new_cols != self._current_columns:
            self._current_columns = new_cols
            self._relayout()

    def _columns_for_width(self, width):
        usable = max(RecipeCard.WIDTH, width - self.SCROLLBAR_RESERVE)
        return max(1, (usable + self.CARD_SPACING) // (RecipeCard.WIDTH + self.CARD_SPACING))

    def _group_order(self):
        names = [t['name'] for t in db.get_tags('recipe')]
        return {name: i for i, name in enumerate(names)}

    def _relayout(self):
        '''Place visible cards into their format groups, sorted, for the
        current column count. No cards are destroyed.'''
        key = SORTS.get(self._sort, SORTS['name'])[1]
        buckets = {}
        for card in self._cards.values():
            if self._accepts(card.row):
                buckets.setdefault(card.row.get('TagName') or SUB_RECIPE_GROUP, []).append(card)
            else:
                card.hide()
        rank = self._format_rank
        names = sorted(buckets, key=lambda n: (n == SUB_RECIPE_GROUP, rank.get(n, 999), n))

        self.container.setUpdatesEnabled(False)
        try:
            for group in self._groups.values():
                while group.grid.count():
                    group.grid.takeAt(0)
                group.hide()
            self._order = []
            for gi, name in enumerate(names):
                group = self._groups.get(name)
                if group is None:
                    group = self._groups[name] = _Group(self.container)
                # Keep groups in display order in the layout.
                self._vbox.removeWidget(group)
                self._vbox.insertWidget(gi, group)
                cards = sorted(buckets[name], key=lambda c: (key(c.row), c.row['Name'].lower()))
                group.set_title(name, len(cards))
                for i, card in enumerate(cards):
                    group.grid.addWidget(card, i // self._current_columns, i % self._current_columns)
                    card.setVisible(card._wedge_ready)
                    self._order.append(card.recipe_id)
                group.show()
            self._empty.setVisible(not names)
        finally:
            self.container.setUpdatesEnabled(True)

    def _reveal_if_ready(self, card):
        if self._accepts(card.row):
            card.setVisible(True)

    # --- model ---------------------------------------------------------

    def refresh(self):
        '''Sync cards to the model: update kept cards, add new ones,
        drop deleted ones, and re-render every wedge in the background.'''
        self._format_rank = self._group_order()
        rows = {r['Id']: r for r in self._model.rows()} if hasattr(self._model, 'rows') \
            else {self._model.row_dict(i)['Id']: self._model.row_dict(i) for i in range(self._model.rowCount())}
        for rid in list(self._cards):
            if rid not in rows:
                card = self._cards.pop(rid)
                card.setParent(None)
                card.deleteLater()
        pool = QThreadPool.globalInstance()
        for rid, row in rows.items():
            card = self._cards.get(rid)
            if card is None:
                card = RecipeCard(row, compare_tray=self._compare_tray, parent=self.container)
                card.clicked.connect(self.recipeClicked.emit)
                card.activated.connect(self.recipeActivated.emit)
                card.contextRequested.connect(self.contextMenuRequested.emit)
                card.hide()
                self._cards[rid] = card
            else:
                card.set_row(row)
            card.set_selected(rid == self._selected_id)
            card.start_render(pool)
        self._relayout()
