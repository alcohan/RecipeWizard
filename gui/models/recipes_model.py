'''Recipes for the Library: db.recipe_info() plus the Library's extras
(nutrition per serving, allergens, ingredient categories, recipe tags,
diets, food cost %, sub-recipe flag, Archived), in a handful of
whole-library queries.

Rows are dicts; the table shows COLUMNS, sorts on Qt.UserRole, and
everything else (gallery, filter pane, inspector) reads rows().
'''
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

import db
from utilities import diets


# Per-row sort keys, shared by the table headers and the Sort menu.
SORTS = {
    'food_cost': ('Food cost %', lambda r: (r['FoodCostPct'] is None, r['FoodCostPct'] or 0)),
    'name': ('Name', lambda r: r['Name'].lower()),
    'cost': ('Cost', lambda r: r['CostRaw'] or 0),
    'calories': ('Calories', lambda r: r['CaloriesPerServing']),
    'edited': ('Recently edited', lambda r: _neg_text(r.get('UpdatedAt') or '')),
}


FOOD_COST_TARGET = 28.0
SUB_RECIPES = '__sub__'     # the format filter's key for recipes with no format


def prices_drifted(cost_raw, cost_snapshot, min_delta=0.01):
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


def review_reasons(row, prices_in_use=True):
    '''Why a recipe is in the Needs review view (empty = it isn't):
    prices moved since its last save, a menu item (it has a format)
    without a menu price or over the food-cost target, or no calories
    (its ingredients are missing nutrition). "No menu price" only
    counts once the library uses menu prices (prices_in_use), or every
    menu item would need review.'''
    reasons = []
    if prices_drifted(row.get('CostRaw'), row.get('CostSnapshot')):
        reasons.append('Prices changed since last save')
    if row.get('TagName'):
        pct = row.get('FoodCostPct')
        if pct is None:
            if prices_in_use:
                reasons.append('No menu price')
        elif pct > FOOD_COST_TARGET:
            reasons.append(f'Food cost over {FOOD_COST_TARGET:.0f}%')
    if not row.get('CaloriesPerServing'):
        reasons.append('Missing nutrition')
    return reasons


def _neg_text(s):
    '''Sorts ISO timestamps newest first under an ascending sort.'''
    return tuple(-ord(ch) for ch in s)


def food_cost_pct(cost, menu_price):
    try:
        cost, menu_price = float(cost), float(menu_price)
    except (TypeError, ValueError):
        return None
    return cost / menu_price * 100.0 if menu_price > 0 else None


class RecipesModel(QAbstractTableModel):
    COLUMNS = ('Name', 'TagName', 'Cost', 'FoodCostPct', 'Calories', 'Components')
    HEADERS = {'Name': 'Name', 'TagName': 'Format', 'Cost': 'Cost', 'FoodCostPct': 'Food cost',
               'Calories': 'Calories', 'Components': 'Components'}
    NUMERIC_COLUMNS = ('Cost', 'FoodCostPct', 'Calories', 'Components')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._by_id = {}
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        rows = db.recipe_info()
        extras = db.get_recipe_library_extras()
        diets.set_rules(db.get_diets())
        tag_order = [(t['id'], t['name']) for t in db.get_tags('recipe_tag')]
        for r in rows:
            r.update(extras.get(r['Id'], {}))
            r.setdefault('Allergens', [])
            r.setdefault('CategoryIds', set())
            r.setdefault('PerServing', {})
            r.setdefault('CaloriesPerServing', 0.0)
            r.setdefault('TagIds', set())
            r['TagNames'] = [name for tid, name in tag_order if tid in r['TagIds']]
            r['Diets'] = diets.diets_for(r['Allergens'], r['PerServing'])
            r['FoodCostPct'] = food_cost_pct(r.get('CostRaw'), r.get('MenuPrice'))
            r['Archived'] = r.get('Status') == 'archived'
            r['SearchText'] = ' '.join(
                str(v) for v in (r['Name'], r.get('TagName'), r.get('Unit'), ' '.join(r['Allergens']),
                                 ' '.join(r['TagNames']), 'archived' if r['Archived'] else '')
                if v).lower()
        prices_in_use = any(r['FoodCostPct'] is not None for r in rows)
        for r in rows:
            r['ReviewReasons'] = review_reasons(r, prices_in_use)
        self._rows = rows
        self._by_id = {r['Id']: i for i, r in enumerate(rows)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        col = self.COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            if col == 'Cost':
                return f'${float(row.get("CostRaw") or 0):.2f}'
            if col == 'FoodCostPct':
                return '—' if row['FoodCostPct'] is None else f'{row["FoodCostPct"]:.1f}%'
            if col == 'Calories':
                return f'{row["CaloriesPerServing"]:.0f}'
            if col == 'TagName':
                return row.get('TagName') or 'Sub-recipe'
            value = row.get(col)
            return '' if value is None else str(value)
        if role == Qt.UserRole:
            if col == 'Name':
                return row['Name'].lower()
            if col == 'Cost':
                return float(row.get('CostRaw') or 0)
            if col == 'FoodCostPct':
                # Unpriced recipes sort after priced ones.
                return row['FoodCostPct'] if row['FoodCostPct'] is not None else 1e9
            if col == 'Calories':
                return row['CaloriesPerServing']
            if col == 'Components':
                return int(row.get('Components') or 0)
            return (row.get(col) or '').lower()
        if role == Qt.TextAlignmentRole and col in self.NUMERIC_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        if role == Qt.ForegroundRole and row['Archived']:
            return QColor('#7d8771')
        if role == Qt.ToolTipRole and row['Archived'] and col == 'Name':
            return f"{row['Name']} · archived"
        return None

    def archived_count(self):
        return sum(1 for r in self._rows if r['Archived'])

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[self.COLUMNS[section]]
        if role == Qt.TextAlignmentRole and orientation == Qt.Horizontal \
                and self.COLUMNS[section] in self.NUMERIC_COLUMNS:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def id_at_row(self, row):
        return self._rows[row]['Id']

    def row_dict(self, row):
        return self._rows[row]

    def row_for_id(self, recipe_id):
        return self._by_id.get(recipe_id, -1)

    def rows(self):
        return self._rows
