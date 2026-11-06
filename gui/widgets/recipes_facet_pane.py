'''Left filter pane for the Recipes Library, per the Framework canvas:
Saved views, Include archived, then Format, Tags, Diets, Contains
category, Free from and Food cost.

- Saved views: All recipes (the defaults) and Needs review (recipes
  with ReviewReasons: prices changed, no menu price, over the
  food-cost target, missing nutrition) are built in; then the user's
  own, stored in the library (saved_views). A view is the pane's
  state() — every filter here, not the text filter — plus the
  Library's Group by and Sort (set_layout_hooks); built-in views leave
  Group by and Sort as they are.
  The view matching the current filters is highlighted; when none
  does, "Save view…" saves them, and "Update" overwrites the view you
  last picked. Right-click your own view to update, rename or delete
  it. Each view shows how many recipes it has.

- Include archived: archived recipes (off the menu) are hidden until
  it's checked. Counts below cover what it lets through.

- Format ("include"): one row per recipe format, plus Sub-recipes
  (recipes with no format, e.g. dressings), which start unchecked so
  the Library opens on menu items.
- Tags ("any"): recipe tags (Core, Seasonal…, set up in Configure)
  plus Untagged; checking shows recipes with any checked tag.
- Diets ("all"): checking Vegan and High protein shows recipes that
  are both. Built-in rules (utilities/diets.py).
- Contains category ("all"): recipes with every checked ingredient
  category somewhere in their tree. Starts collapsed.
- Free from ("exclude"): hides recipes containing any checked
  allergen. Starts collapsed.
- Food cost: "Up to N%" slider over recipes with a menu price; at the
  top stop it's off. Disabled, with a note, until any recipe has one.

'''
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton, QSlider, QVBoxLayout,
    QWidget,
)

import db
from gui.services import food_cost
from gui.models.recipes_facet_proxy import matches
from gui.models.recipes_model import SUB_RECIPES
from gui.widgets.elided_label import ElidedLabel
from gui.widgets.facet_pane import BORDER, KALE, MUTED, ROMAINE, WARN, FacetPane, FacetSection
from gui.widgets.toolbar_controls import ToggleSwitch
from utilities import diets


FOOD_COST_OFF = 50          # slider top stop = no food-cost filter
_FOOD_COST_MIN = 15


def _target_text():
    t = food_cost.target_percent()
    return f' · target {t:.0f}%' if t is not None else ''


class RecipesFacetPane(FacetPane):
    SECTIONS = (
        ('format', 'Format', 'include', True),
        ('tag', 'Tags', 'any', True),
        ('diet', 'Diets', 'all', True),
        ('category', 'Contains category', 'all', False),
        ('allergen', 'Free from', 'exclude', False),
    )
    SETTINGS_PREFIX = 'recipes/facetOpen/'

    def __init__(self, parent=None):
        super().__init__(parent)
        self._formats = []        # [(name, color)] in format order
        self._categories = []     # [(id, name, color)] in category order
        self._rows = []
        self._needs_review = False
        self._user_views = []     # [{id, name, state}]
        self._last_view = None    # id of the user view last picked
        self._build_archived()
        self._build_views()
        self._build_food_cost()
        self.changed.connect(self._sync_views)

    def _default_checked(self, group, key):
        if group == 'format':
            return key != SUB_RECIPES
        return super()._default_checked(group, key)

    def _build_archived(self):
        row = QWidget()
        hl = QHBoxLayout(row)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(6)
        self.include_archived = ToggleSwitch()
        self.include_archived.toggled.connect(self._on_archived_toggled)
        label = ElidedLabel('Include archived')
        label.setStyleSheet(f'color: {KALE};')
        # Clicking the words flips the switch too.
        label.mousePressEvent = lambda _e: self.include_archived.toggle()
        self.archived_count = QLabel('0')
        self.archived_count.setStyleSheet(f'color: {MUTED};')
        hl.addWidget(label, stretch=1)
        hl.addWidget(self.archived_count)
        hl.addWidget(self.include_archived)
        self._layout.insertWidget(0, row)

    def _on_archived_toggled(self, _on):
        self._refill()
        self.changed.emit()

    def _build_food_cost(self):
        section = FacetSection('food_cost', 'Food cost', 'slider', True, self.SETTINGS_PREFIX)
        self.food_cost = QSlider(Qt.Horizontal)
        self.food_cost.setRange(_FOOD_COST_MIN, FOOD_COST_OFF)
        self.food_cost.setValue(FOOD_COST_OFF)
        self.food_cost.setPageStep(5)
        self.food_cost.setTickPosition(QSlider.TicksBelow)
        self.food_cost.setTickInterval(5)
        self.food_cost.valueChanged.connect(self._on_food_cost)
        self.food_cost_label = QLabel('')
        self.food_cost_label.setWordWrap(True)
        self.food_cost_label.setStyleSheet(f'color: {MUTED}; font-size: 12px;')
        section.body.addWidget(self.food_cost)
        section.body.addWidget(self.food_cost_label)
        self._food_section = section
        # Above the stretch at the end of the base layout.
        self._layout.insertWidget(self._layout.count() - 1, section)
        self._sync_food_cost()

    # --- building ------------------------------------------------------

    def set_library(self, rows):
        self._rows = list(rows)
        self._user_views = db.get_saved_views()
        self._refill()

    def _refill(self):
        all_rows = self._rows
        self.archived_count.setText(str(sum(1 for r in all_rows if r.get('Archived'))))
        rows = [r for r in all_rows if self.include_archived.isChecked() or not r.get('Archived')]
        # Re-read each time: formats and categories are edited in Configure.
        self._formats = [(t['name'], t.get('color')) for t in db.get_tags('recipe')]
        self._categories = [(t['id'], t['name'], t.get('color')) for t in db.get_tags('ingredient')]

        fmt_counts = {}
        for r in rows:
            key = r.get('TagName') or SUB_RECIPES
            fmt_counts[key] = fmt_counts.get(key, 0) + 1
        names = [n for n, _c in self._formats]
        extra = sorted(k for k in fmt_counts if k not in names and k != SUB_RECIPES)
        self._fill('format', [(name, name, color, fmt_counts.get(name, 0), None)
                              for name, color in self._formats]
                   + [(name, name, None, fmt_counts[name], None) for name in extra]
                   + [(SUB_RECIPES, 'Sub-recipes', None, fmt_counts.get(SUB_RECIPES, 0), None,
                       'Recipes with no format, like dressings and sauces')])

        tags = db.get_tags('recipe_tag')
        self._fill('tag', [(t['id'], t['name'], t.get('color'), sum(1 for r in rows if t['id'] in r['TagIds']), None)
                           for t in tags]
                   + [(None, 'Untagged', None, sum(1 for r in rows if not r['TagIds']), None)])
        self.section('tag').setVisible(bool(tags))

        self._fill('diet', [(d['key'], d['name'], None, sum(1 for r in rows if d['key'] in r['Diets']), None,
                             diets.describe(d)) for d in diets.rules()])

        self._fill('category', [(cid, name, color, sum(1 for r in rows if cid in r['CategoryIds']), None)
                                for cid, name, color in self._categories])

        allergens = db.get_all_allergens()
        self._fill('allergen', [(a, a, None, sum(1 for r in rows if a not in r['Allergens']
                                                and a not in (r.get('FacilityAllergens') or ())), None,
                                 f'Recipes without {a.lower()}, and no facility warning for it')
                                for a in allergens])

        self._priced = sum(1 for r in rows if r.get('FoodCostPct') is not None)
        self._sync_food_cost()
        self._sync_views()

    # --- saved views ---------------------------------------------------

    def _build_views(self):
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        title = QLabel('SAVED VIEWS')
        title.setStyleSheet(f'color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 1px;')
        v.addWidget(title)
        v.addSpacing(4)
        self._view_rows = QVBoxLayout()
        self._view_rows.setSpacing(2)
        v.addLayout(self._view_rows)

        self.review_note = QPushButton('Only recipes needing review  ×')
        self.review_note.setCursor(Qt.PointingHandCursor)
        self.review_note.setToolTip('Click to turn off')
        self.review_note.setStyleSheet(f'QPushButton {{ color: {WARN}; background: #fff0dc; border: 0;'
                                       ' border-radius: 8px; padding: 1px 8px; font-size: 11px; font-weight: 600;'
                                       ' text-align: left; }')
        self.review_note.clicked.connect(self._drop_review)
        v.addWidget(self.review_note)

        links = QHBoxLayout()
        links.setContentsMargins(8, 4, 0, 0)
        links.setSpacing(12)
        self.save_link = _link('+ Save view…')
        self.save_link.setToolTip('Save these filters as a view')
        self.save_link.clicked.connect(self.save_view)
        self.update_link = _link('Update')
        self.update_link.clicked.connect(lambda: self.update_view(self._last_view))
        links.addWidget(self.save_link)
        links.addWidget(self.update_link)
        links.addStretch()
        v.addLayout(links)
        self._layout.insertWidget(0, box)

    def views(self):
        '''Built-in views, then the user's: [(key, name, state, user view id or None)].'''
        default = self._default_state()
        review = dict(default, needs_review=True)
        return ([('all', 'All recipes', default, None), ('review', 'Needs review', review, None)]
                + [(f'user:{v["id"]}', v['name'], v['state'], v['id']) for v in self._user_views])

    def set_layout_hooks(self, get, put):
        '''Group by and Sort live in the Library toolbar: get() returns
        {'group': …, 'sort': …}; put(dict) applies a view's.'''
        self._layout_get = get
        self._layout_put = put

    def full_state(self):
        '''state() plus Group by and Sort: what a saved view stores.'''
        st = self.state()
        get = getattr(self, '_layout_get', None)
        if get is not None:
            st.update(get())
        return st

    def _view_matches(self, st, current=None):
        '''Filters match, and Group by / Sort too where the view has them.'''
        current = current or self.full_state()
        filters = {k: v for k, v in st.items() if k not in LAYOUT_KEYS}
        if not _same(filters, {k: v for k, v in current.items() if k not in LAYOUT_KEYS}):
            return False
        return all(st[k] == current.get(k) for k in LAYOUT_KEYS if k in st)

    def active_view(self):
        '''Key of the view matching the current filters, or None. Your
        own views come first: they also pin Group by and Sort, so they're
        the more specific match.'''
        current = self.full_state()
        views = self.views()
        picked = getattr(self, '_picked', None)
        ordered = ([v for v in views if v[0] == picked]
                   + [v for v in views if v[3] is not None] + [v for v in views if v[3] is None])
        return next((key for key, _n, st, _id in ordered if self._view_matches(st, current)), None)

    def _pick_view(self, key, state, view_id):
        self._picked = key      # the view you clicked stays highlighted while it still matches
        self.apply_state(state, view_id=view_id)

    def refresh_views(self):
        if hasattr(self, '_rows'):
            self._sync_views()

    def _sync_views(self):
        while self._view_rows.count():
            w = self._view_rows.takeAt(0).widget()
            if w is not None:
                w.deleteLater()
        current = self.state()
        active = self.active_view()
        for key, name, st, view_id in self.views():
            n = sum(1 for r in self._rows if matches(r, st))
            row = _ViewRow(name, n, warn=key == 'review' and n > 0, active=key == active)
            if key == 'review':
                row.setToolTip('Prices changed since last save, no menu price, food cost over target,'
                               ' or missing nutrition')
            row.clicked.connect(lambda st=st, vid=view_id, k=key: self._pick_view(k, st, vid))
            if view_id is not None:
                row.menuRequested.connect(lambda pos, vid=view_id: self._view_menu(vid, pos))
            self._view_rows.addWidget(row)
        last = next((v for v in self._user_views if v['id'] == self._last_view), None)
        self.save_link.setVisible(active is None)
        self.update_link.setVisible(active is None and last is not None)
        if last is not None:
            self.update_link.setText(f'Update “{_short(last["name"])}”')
            self.update_link.setToolTip(f'Save these filters as “{last["name"]}”')
        self.review_note.setVisible(bool(current.get('needs_review')) and active != 'review')

    def _drop_review(self):
        self._needs_review = False
        self.changed.emit()

    def _view_menu(self, view_id, pos):
        view = next(v for v in self._user_views if v['id'] == view_id)
        menu = QMenu(self)
        upd = menu.addAction('Update to current filters', lambda: self.update_view(view_id))
        upd.setEnabled(not self._view_matches(view['state']))
        menu.addAction('Rename…', lambda: self.rename_view(view_id))
        menu.addSeparator()
        menu.addAction('Delete…', lambda: self.delete_view(view_id))
        menu.exec(pos)

    def _ask_name(self, title, current=''):
        '''A new, unused view name, or None if cancelled.'''
        name = current
        while True:
            name, ok = QInputDialog.getText(self, title, 'View name:', text=name)
            name = (name or '').strip()
            if not ok or not name:
                return None
            taken = {n.lower() for _k, n, _s, vid in self.views() if n.lower() != current.lower()}
            if name.lower() not in taken:
                return name
            QMessageBox.information(self, title, f'There is already a view called “{name}”.')

    def save_view(self, name=None):
        '''Save the current filters as a new view (asks for a name).'''
        name = name or self._ask_name('Save view')
        if name is None:
            return None
        view_id = db.create_saved_view(name, self.full_state())
        self._user_views = db.get_saved_views()
        self._last_view = view_id
        self._sync_views()
        return view_id

    def update_view(self, view_id):
        if view_id is None:
            return
        db.update_saved_view(view_id, state=self.full_state())
        self._user_views = db.get_saved_views()
        self._last_view = view_id
        self._sync_views()

    def rename_view(self, view_id, name=None):
        view = next(v for v in self._user_views if v['id'] == view_id)
        name = name or self._ask_name('Rename view', view['name'])
        if name:
            db.update_saved_view(view_id, name=name)
            self._user_views = db.get_saved_views()
            self._sync_views()

    def delete_view(self, view_id, confirm=True):
        view = next(v for v in self._user_views if v['id'] == view_id)
        if confirm and QMessageBox.question(
                self, 'Delete view', f'Delete the view “{view["name"]}”? Your recipes stay as they are.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        db.delete_saved_view(view_id)
        self._user_views = db.get_saved_views()
        if self._last_view == view_id:
            self._last_view = None
        self._sync_views()

    # --- state -----------------------------------------------------------

    def state(self):
        '''Every filter here, JSON-ready: what RecipesFacetProxy.set_state
        takes and saved views store.'''
        return {
            'formats': _keys(self.included('format')),
            'tags': _keys(self.checked('tag')),
            'diets': _keys(self.checked('diet')),
            'categories': _keys(self.checked('category')),
            'free_from': _keys(self.checked('allergen')),
            'max_food_cost': self.max_food_cost(),
            'include_archived': self.include_archived.isChecked(),
            'needs_review': self._needs_review,
        }

    def _default_state(self):
        boxes = self._groups['format']['boxes']
        on = {k for k in boxes if self._default_checked('format', k)}
        return {'formats': None if len(on) == len(boxes) else _keys(on), 'tags': [], 'diets': [],
                'categories': [], 'free_from': [], 'max_food_cost': None, 'include_archived': False,
                'needs_review': False}

    def apply_state(self, state, view_id=None):
        '''Set every filter from a state() dict (a saved view), then
        emit changed once.'''
        for group, key in (('format', 'formats'), ('tag', 'tags'), ('diet', 'diets'),
                           ('category', 'categories'), ('allergen', 'free_from')):
            want = state.get(key)
            for k in self._groups[group]['boxes']:
                on = (want is None or k in want) if group == 'format' else k in (want or ())
                self._state[(group, k)] = on
        cap = state.get('max_food_cost')
        self.food_cost.blockSignals(True)
        self.food_cost.setValue(FOOD_COST_OFF if cap is None else int(round(cap)))
        self.food_cost.blockSignals(False)
        self.include_archived.blockSignals(True)
        self.include_archived.setChecked(bool(state.get('include_archived')))
        self.include_archived.blockSignals(False)
        self._needs_review = bool(state.get('needs_review'))
        self._last_view = view_id
        put = getattr(self, '_layout_put', None)
        layout = {k: state[k] for k in LAYOUT_KEYS if state.get(k)}
        if put is not None and layout:
            put(layout)
        self._refill()
        self.changed.emit()

    # --- food cost -----------------------------------------------------

    def _on_food_cost(self, _value):
        self._sync_food_cost()
        self.changed.emit()

    def _sync_food_cost(self):
        priced = getattr(self, '_priced', 0)
        self.food_cost.setEnabled(bool(priced))
        value = self.food_cost.value()
        if not priced:
            self.food_cost_label.setText('No menu prices yet')
        elif value >= FOOD_COST_OFF:
            self.food_cost_label.setText(f'Any{_target_text()} · {priced} priced')
        else:
            self.food_cost_label.setText(f'Up to {value}%{_target_text()}')
        self._food_section.set_filtering(bool(priced) and value < FOOD_COST_OFF)

    def max_food_cost(self):
        '''Percent, or None for no food-cost filter.'''
        v = self.food_cost.value()
        return None if v >= FOOD_COST_OFF or not self.food_cost.isEnabled() else float(v)

    # --- reading -------------------------------------------------------

    def selection(self):
        '''(formats, tags, diets, categories, free_from, max_food_cost,
        include_archived) for RecipesFacetProxy.set_facets.'''
        return (self.included('format'), self.checked('tag'), self.checked('diet'), self.checked('category'),
                self.checked('allergen'), self.max_food_cost(), self.include_archived.isChecked())

    def clear(self):
        self._needs_review = False
        self._last_view = None
        if self.include_archived.isChecked():
            self.include_archived.blockSignals(True)
            self.include_archived.setChecked(False)
            self.include_archived.blockSignals(False)
            self._refill()
        self.food_cost.blockSignals(True)
        self.food_cost.setValue(FOOD_COST_OFF)
        self.food_cost.blockSignals(False)
        self._sync_food_cost()
        super().clear()


def _keys(keys):
    '''A set of facet keys as a sorted list (None, for Untagged, first);
    None stays None (an include section with everything checked).'''
    if keys is None:
        return None
    return sorted(keys, key=lambda k: (k is not None, str(k)))


LAYOUT_KEYS = ('group', 'sort')


def _same(a, b):
    '''Two states filter the same (lists compared as sets).'''
    for key in set(a) | set(b):
        x, y = a.get(key), b.get(key)
        if isinstance(x, list) or isinstance(y, list):
            if (x is None) != (y is None) or set(x or ()) != set(y or ()):
                return False
        elif (x or None) != (y or None):
            return False
    return True


def _short(name, n=18):
    return name if len(name) <= n else name[:n - 1] + '…'


def _link(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(f'QPushButton {{ color: {ROMAINE}; border: 0; background: transparent; padding: 0;'
                      ' font-size: 12px; } QPushButton:hover { text-decoration: underline; }')
    return btn


class _ViewRow(QFrame):
    '''One saved view: name and count; the current one is highlighted.'''

    clicked = Signal()
    menuRequested = Signal(object)   # global QPoint

    def __init__(self, name, count, warn=False, active=False, parent=None):
        super().__init__(parent)
        self.setObjectName('ViewRow')
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f'QFrame#ViewRow {{ border-radius: 6px; background: {"#f3ece0" if active else "transparent"}; }}'
            f' QFrame#ViewRow:hover {{ background: {"#f3ece0" if active else "#f8f2e6"}; }}')
        hl = QHBoxLayout(self)
        hl.setContentsMargins(8, 4, 8, 4)
        hl.setSpacing(6)
        self.name = ElidedLabel(name)
        self.name.setStyleSheet(f'color: {KALE}; font-weight: {"650" if active else "400"};')
        self.count = QLabel(str(count))
        self.count.setStyleSheet(f'color: {WARN if warn else MUTED}; font-weight: {"600" if warn else "400"};')
        hl.addWidget(self.name, stretch=1)
        hl.addWidget(self.count)
        self.active = active

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.RightButton:
            self.menuRequested.emit(event.globalPosition().toPoint())
