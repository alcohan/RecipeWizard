'''Ingredients library model, backed by db.get_ingredient_library().

One query per refresh (≈7 ms for the sample library); every derived
value — the 90-day price change, the "needs attention" flags, the
filter's search text — is computed once in refresh(), so data() is a
dictionary lookup and scrolling never touches the DB.

Rows keep the keys the gallery and main window already read (Id, Name,
TagName, TagColor, ImageFilename, Portion, Unit, Calories).
'''
import os

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

import config
import db
from gui.widgets.tag_badge import TagColorRole


SubTextRole = Qt.UserRole + 20     # second line under the main text
ChangeRole = Qt.UserRole + 21      # float change since BasePrice, or None (no price)
RowRole = Qt.UserRole + 22         # the whole row dict

_ARCHIVED_FG = QColor('#a7ad9c')

# "Price up 5%+ (90 days)" threshold.
PRICE_UP_THRESHOLD = 0.05

ATTENTION_KEYS = ('price_up', 'no_price', 'no_nutrition', 'no_photo', 'unused')
# Allergen-filter key for "contains none".
NO_ALLERGENS = '__none__'


class IngredientsModel(QAbstractTableModel):
    COLUMNS = ('Name', 'Unit', 'Cost', 'Change', 'Supplier', 'Calories', 'Allergens', 'UsedIn')
    HEADERS = {
        'Name': 'INGREDIENT', 'Unit': 'UNIT · TOOL', 'Cost': 'COST / UNIT',
        'Change': '90 DAYS', 'Supplier': 'SUPPLIER', 'Calories': 'KCAL',
        'Allergens': 'ALLERGENS', 'UsedIn': 'USED IN',
    }
    RIGHT_ALIGNED = ('Cost', 'Calories', 'UsedIn')

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []
        self._by_id = {}
        self.refresh()

    def refresh(self):
        self.beginResetModel()
        rows = db.get_ingredient_library()
        try:
            photos = set(os.listdir(config.INGREDIENTS_PATH))
        except OSError:
            photos = set()
        for r in rows:
            price = r.get('PriceUnit')
            base = r.get('BasePrice')
            change = None
            if price is not None:
                change = (price / base - 1.0) if base else 0.0
            r['ChangePct'] = change
            r['Archived'] = r.get('status') == 'archived'
            # Archived ingredients don't need attention.
            r['Flags'] = {k: False for k in ATTENTION_KEYS} if r['Archived'] else {
                'price_up': change is not None and change >= PRICE_UP_THRESHOLD,
                'no_price': not r.get('PriceCount'),
                'no_nutrition': not r.get('Calories'),
                'no_photo': not r.get('ImageFilename') or r['ImageFilename'] not in photos,
                'unused': not r.get('UsedIn') and not r.get('ScenarioUses'),
            }
            r['AllergenList'] = [a.strip() for a in (r.get('Allergens') or '').split(',') if a.strip()]
            r['SearchText'] = ' '.join(str(r.get(k) or '') for k in (
                'Name', 'TagName', 'SupplierName', 'Allergens', 'Unit', 'Portion')).lower()                 + (' archived' if r['Archived'] else '')
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
        col = self.COLUMNS[index.column()]
        row = self._rows[index.row()]
        if role == RowRole:
            return row
        if role == TagColorRole:
            return row.get('TagColor')
        if role == ChangeRole:
            return row.get('ChangePct')
        if role == SubTextRole:
            if col == 'Name':
                return (row.get('TagName') or 'Uncategorized') + (' · archived' if row['Archived'] else '')
            if col == 'Unit':
                return row.get('Portion') or ''
            return None
        if role == Qt.DisplayRole:
            return _display(col, row)
        if role == Qt.ForegroundRole and row['Archived']:
            return _ARCHIVED_FG
        if role == Qt.ToolTipRole and row['Archived'] and col == 'Name':
            return f"{row['Name']} · archived"
        if role == Qt.UserRole:
            return _sort_key(col, row)
        if role == Qt.TextAlignmentRole and col in self.RIGHT_ALIGNED:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation != Qt.Horizontal:
            return None
        col = self.COLUMNS[section]
        if role == Qt.DisplayRole:
            return self.HEADERS[col]
        if role == Qt.TextAlignmentRole:
            align = Qt.AlignRight if col in self.RIGHT_ALIGNED else Qt.AlignLeft
            return int(align | Qt.AlignVCenter)
        return None

    def id_at_row(self, row):
        return self._rows[row]['Id']

    def row_dict(self, row):
        return self._rows[row]

    def row_for_id(self, ingredient_id):
        return self._by_id.get(ingredient_id, -1)

    def rows(self):
        return self._rows

    def archived_count(self):
        return sum(1 for r in self._rows if r['Archived'])


def format_unit_price(value):
    '''Unit prices are small — three decimals ("$0.370").'''
    if value is None:
        return '—'
    return f'${float(value):.3f}'


def format_change(pct):
    if pct is None:
        return ''
    if abs(pct) < 0.0005:
        return '0.0%'
    sign = '+' if pct > 0 else '−'
    return f'{sign}{abs(pct) * 100:.1f}%'


def _display(col, row):
    if col == 'Name':
        return row.get('Name') or ''
    if col == 'Unit':
        return row.get('Unit') or ''
    if col == 'Cost':
        # Ingredients.Cost is what recipes are costed with (kept equal to
        # the latest price by a trigger), so show that.
        return format_unit_price(row.get('Cost') or None)
    if col == 'Change':
        return format_change(row.get('ChangePct'))
    if col == 'Supplier':
        return row.get('SupplierName') or '—'
    if col == 'Calories':
        return '' if row.get('Calories') in (None, '') else f"{float(row['Calories']):.0f}"
    if col == 'Allergens':
        return row.get('Allergens') or '—'
    if col == 'UsedIn':
        if row.get('UsedIn'):
            return str(row['UsedIn'])
        return 'Scenario' if row.get('ScenarioUses') else 'Unused'
    return ''


def _sort_key(col, row):
    if col == 'Name':
        return (row.get('Name') or '').lower()
    if col in ('Cost', 'Calories', 'UsedIn', 'Change'):
        value = {'Cost': row.get('Cost') or None, 'Calories': row.get('Calories'),
                 'UsedIn': row.get('UsedIn'), 'Change': row.get('ChangePct')}[col]
        # Missing values sort below everything.
        return float(value) if value is not None else float('-inf')
    return (_display(col, row) or '').lower()
