'''Left filter pane for the Recipes Library, per the Framework canvas:
Format, Tags, Diets, Contains category, Free from and Food cost.

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

Saved views come with the data-model slice.
'''
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

import db
from gui.widgets.facet_pane import KALE, MUTED, FacetPane, FacetSection
from utilities.diets import DIETS


SUB_RECIPES = '__sub__'
FOOD_COST_OFF = 50          # slider top stop = no food-cost filter
_FOOD_COST_MIN = 15
_FOOD_COST_TARGET = 28      # the canvas's target line


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
        self._build_food_cost()

    def _default_checked(self, group, key):
        if group == 'format':
            return key != SUB_RECIPES
        return super()._default_checked(group, key)

    def _build_food_cost(self):
        section = FacetSection('food_cost', 'Food cost', 'slider', True, self.SETTINGS_PREFIX)
        self.food_cost = QSlider(Qt.Horizontal)
        self.food_cost.setRange(_FOOD_COST_MIN, FOOD_COST_OFF)
        self.food_cost.setValue(FOOD_COST_OFF)
        self.food_cost.setPageStep(5)
        self.food_cost.setTickPosition(QSlider.TicksBelow)
        self.food_cost.setTickInterval(5)
        self.food_cost.setToolTip(f'Target food cost: {_FOOD_COST_TARGET}%')
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

        self._fill('diet', [(key, name, None, sum(1 for r in rows if key in r['Diets']), None, tip)
                            for key, name, tip, *_ in DIETS])

        self._fill('category', [(cid, name, color, sum(1 for r in rows if cid in r['CategoryIds']), None)
                                for cid, name, color in self._categories])

        allergens = db.get_all_allergens()
        self._fill('allergen', [(a, a, None, sum(1 for r in rows if a not in r['Allergens']), None,
                                 f'Recipes without {a.lower()}')
                                for a in allergens])

        self._priced = sum(1 for r in rows if r.get('FoodCostPct') is not None)
        self._sync_food_cost()

    # --- food cost -----------------------------------------------------

    def _on_food_cost(self, _value):
        self._sync_food_cost()
        self.changed.emit()

    def _sync_food_cost(self):
        priced = getattr(self, '_priced', 0)
        self.food_cost.setEnabled(bool(priced))
        value = self.food_cost.value()
        if not priced:
            self.food_cost_label.setText('Set menu prices on recipes to filter by food cost.')
        elif value >= FOOD_COST_OFF:
            self.food_cost_label.setText(f'Any · target {_FOOD_COST_TARGET}% · {priced} priced')
        else:
            self.food_cost_label.setText(f'Up to {value}% · target {_FOOD_COST_TARGET}%')
        self._food_section.set_filtering(bool(priced) and value < FOOD_COST_OFF)

    def max_food_cost(self):
        '''Percent, or None for no food-cost filter.'''
        v = self.food_cost.value()
        return None if v >= FOOD_COST_OFF or not self.food_cost.isEnabled() else float(v)

    # --- reading -------------------------------------------------------

    def selection(self):
        '''(formats, tags, diets, categories, free_from, max_food_cost)
        for RecipesFacetProxy.set_facets.'''
        return (self.included('format'), self.checked('tag'), self.checked('diet'), self.checked('category'),
                self.checked('allergen'), self.max_food_cost())

    def clear(self):
        self.food_cost.blockSignals(True)
        self.food_cost.setValue(FOOD_COST_OFF)
        self.food_cost.blockSignals(False)
        self._sync_food_cost()
        super().clear()
