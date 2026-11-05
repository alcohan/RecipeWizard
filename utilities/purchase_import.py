'''Purchase imports: invoice lines from a purchase-history export become
ingredient prices.

The pieces, all framework-agnostic:

- An **import format** (`import_formats`) says which column of a file is
  which field, plus reading rules and choices remembered between imports
  (locations and GL codes left out, vendor name → supplier).
- A **vendor item** (`vendor_items`) is one thing a vendor sells, keyed by
  vendor + item code, or vendor + description + pack size when the export
  has no code (Sysco lines have none). A mapped vendor item says which
  ingredient it is and what a case yields: case quantity + unit + yield %,
  turned into portions with the ingredient's measured portion weight in
  grams; things counted by each use portions per each instead.
- An **import** (`ImportSession`) reads a file, lets the caller choose
  locations and GL codes, and prices each ingredient by blending: total
  spend ÷ total portions, across every vendor item mapped to it and every
  included location — weekly (one price per Monday–Sunday week) or from
  the latest purchase date.
- Applying writes `ingredient_prices` rows tagged with an
  `import_batch_id`. The batch keeps its per-day totals (`import_lines`),
  so it can be undone, or re-priced after a vendor item's yield is fixed.

Flags catch case-yield mistakes: a new price more than ±30% off the
current one, or vendor items for one ingredient whose per-portion costs
are more than 1.5× apart.
'''
import collections
import csv
import datetime
import html
import json
import os
import re
import sqlite3

import config


JUMP_LIMIT = 0.30         # flag a price that moved more than ±30%
DISAGREE_LIMIT = 1.5      # flag vendor items for one ingredient > 1.5× apart
UNCHANGED_BELOW = 0.01    # under 1% counts as unchanged in the review
SWING_MIN = 0.03          # location preview shows items moving 3% or more

BUILTIN_FORMAT_NAME = 'Purchase history (inventory system)'

# Field key, label, required, what it's for. Order is the column mapper's.
FIELDS = (
    ('date', 'Purchase date', True, 'Groups prices into weeks'),
    ('vendor', 'Vendor', True, 'Matched to a supplier'),
    ('item_code', 'Item code', False, 'Blank codes fall back to description + pack'),
    ('description', 'Description', True, 'Vendor item name'),
    ('pack_size', 'Pack size', False, 'Read to suggest a case yield'),
    ('quantity', 'Quantity', True, 'Cases, or pounds for catch weight'),
    ('amount', 'Amount', False, 'Line total'),
    ('unit_price', 'Unit price', False, 'Used when Amount is missing'),
    ('location', 'Location', False, 'Lets you choose which stores to blend'),
    ('inventory_item', 'Inventory item', False, 'Suggests the ingredient for new items'),
    ('invoice', 'Invoice number', False, 'Shown on the import'),
)
FIELD_LABELS = {key: label for key, label, _, _ in FIELDS}
REQUIRED_FIELDS = tuple(key for key, _, required, _ in FIELDS if required)

DATE_FORMATS = {
    'MM/DD/YYYY': '%m/%d/%Y',
    'YYYY-MM-DD': '%Y-%m-%d',
    'DD/MM/YYYY': '%d/%m/%Y',
}

# Grams per unit. Volumes use the workbook's convention (1 f.oz weighs
# 28.375 g, a gallon 128 of them) — the portion itself is a measured
# weight, so the case should be one too wherever possible.
UNIT_GRAMS = {
    'lb': 454.0,
    'oz': 28.375,
    'g': 1.0,
    'kg': 1000.0,
    'gal': 3632.0,
    'qt': 908.0,
    'fl oz': 28.375,
    'l': 959.5,
}
CASE_UNITS = ('lb', 'oz', 'g', 'kg', 'gal', 'qt', 'fl oz', 'l', 'ea')


def builtin_format_settings():
    '''The format the first sample export (13 columns) reads with.'''
    return {
        'columns': {
            'date': 'PurchaseDate',
            'vendor': 'Vendor',
            'item_code': 'VPI Code',
            'description': 'VPI',
            'pack_size': 'PackSize',
            'quantity': 'Quantity',
            'amount': 'Amount',
            'unit_price': 'AvgPrice',
            'location': 'LocationName',
            'inventory_item': 'InventoryItemName',
            'invoice': 'InvoiceNumber',
        },
        'date_format': 'MM/DD/YYYY',
        'price_from': 'amount',        # 'amount' (Amount ÷ Quantity) or 'unit_price'
        'skip_credits': True,
        'catch_weight': True,          # "LB WEIGHT" pack: quantity is pounds
        'basis': 'weekly',             # 'weekly' or 'latest'
        'excluded_locations': [],
        'vendor_suppliers': {},        # name in file → supplier id
    }


def default_settings():
    s = builtin_format_settings()
    s['columns'] = {}
    return s


# --- small helpers ------------------------------------------------------

def _connect(path=None):
    con = sqlite3.connect(path or config.DATABASE)
    con.row_factory = sqlite3.Row
    return con


def _norm(text):
    return ' '.join(html.unescape(str(text or '')).split()).casefold()


def _clean(text):
    return ' '.join(html.unescape(str(text or '')).split())


def _num(text):
    try:
        return float(str(text).replace(',', '').replace('$', '').strip())
    except (TypeError, ValueError):
        return None


def week_start(day):
    '''The Monday of `day`'s week.'''
    return day - datetime.timedelta(days=day.weekday())


def money(value, places=2):
    return '—' if value is None else f'${value:,.{places}f}'


def vendor_key(vendor, item_code, description, pack_size):
    '''One vendor item's identity across imports.'''
    code = _norm(item_code)
    if code:
        return f'{_norm(vendor)}|{code}'
    return f'{_norm(vendor)}|{_norm(description)}|{_norm(pack_size)}'


# --- pack sizes ---------------------------------------------------------

_UNIT_WORDS = {
    'LB': 'lb', 'LBS': 'lb', '#': 'lb', 'OZ': 'oz', 'GAL': 'gal', 'QT': 'qt',
    'CT': 'ea', 'EA': 'ea', 'PC': 'ea', 'PCS': 'ea', 'CNT': 'ea', 'COUNT': 'ea',
    'KG': 'kg', 'G': 'g', 'GR': 'g', 'EACH': 'ea', 'L': 'l', 'LT': 'l', 'LTR': 'l',
    'FOZ': 'fl oz', 'FLOZ': 'fl oz',
}


def _unit_word(word):
    '''"LB" → lb, and a unit run into another word ("LBBAG") → lb.'''
    word = (word or '').rstrip('.')
    if word in _UNIT_WORDS:
        return _UNIT_WORDS[word]
    for size in (4, 3, 2):
        if word[:size] in _UNIT_WORDS and size < len(word):
            return _UNIT_WORDS[word[:size]]
    return None
_PREFIX_RE = re.compile(r'^(CA|CS|EA|BG|BX|PK|RL|PC|BU|DZ|BL|BD)\b\.?\s*(.*)$')
_NUM = r'(\d+(?:\.\d+)?)'
_PACK_RE = re.compile(_NUM + r'\s*[/X]\s*' + _NUM + r'\s*([A-Z#]+)?')
_SINGLE_RE = re.compile(_NUM + r'\s*(LBS?|#|FOZ|OZ|GAL|QT|CT|EACH|EA|PCS?|CNT|KG|GR|G|LTR|LT|L)\b')


def parse_pack(text):
    '''Read a pack size into a suggested case yield:
    {'qty', 'unit', 'reading'} or None when it can't be read.

    "CA 2/5LB" → 10 lb, "6/2LB" → 12 lb, "CA 12/12 OZ" → 144 oz,
    "60/70CT" → 65 ea (a count range), "CA 1000" → 1000 ea,
    "EA 2/8LB" → 8 lb (a split case: one of the inner packs),
    "LB WEIGHT" → 1 lb (catch weight, priced per pound).'''
    t = _clean(text).upper()
    if not t:
        return None
    if 'WEIGHT' in t and 'LB' in t:
        return {'qty': 1.0, 'unit': 'lb', 'reading': 'catch weight: priced per lb'}
    split = False
    m = _PREFIX_RE.match(t)
    if m:
        split = m.group(1) == 'EA'
        rest = m.group(2).strip()
        if not rest:
            return {'qty': 1.0, 'unit': 'ea', 'reading': '1 each'} if split else None
        if re.fullmatch(r'\d+', rest):
            n = float(rest)
            return {'qty': n, 'unit': 'ea', 'reading': f'{n:g} count'}
        t = rest
    m = re.fullmatch(r'(\d+)\s*/\s*(EA|EACH)', t)
    if m:
        n = float(m.group(1))
        return {'qty': n, 'unit': 'ea', 'reading': f'{n:g} each'}
    m = _PACK_RE.search(t)
    if m:
        n, size = float(m.group(1)), float(m.group(2))
        unit = _unit_word(m.group(3))
        if unit is None:
            return None    # "6/10 CAN": #10 cans — enter a drained weight
        if unit == 'ea' and n >= 24 and size >= n and size - n <= n * 0.5:
            avg = (n + size) / 2
            return {'qty': avg, 'unit': 'ea', 'reading': f'{n:g}–{size:g} count, about {avg:g}'}
        if split:
            return {'qty': size, 'unit': unit, 'reading': f'split case: one {size:g} {unit} pack'}
        return {'qty': n * size, 'unit': unit, 'reading': f'{n:g} × {size:g} {unit} = {n * size:g} {unit}'}
    m = _SINGLE_RE.search(t)
    if m:
        qty, unit = float(m.group(1)), _UNIT_WORDS[m.group(2)]
        return {'qty': qty, 'unit': unit, 'reading': f'{qty:g} {unit}'}
    if re.fullmatch(r'\d+', t):
        return {'qty': float(t), 'unit': 'ea', 'reading': f'{float(t):g} count'}
    return None


# --- yields -------------------------------------------------------------

def portions_per_case(item, portion_grams):
    '''Portions one case (one purchased unit) of `item` yields, or None
    with the reason it can't be worked out yet.

    `item` has case_qty, case_unit, yield_pct, portions_per_each;
    `portion_grams` is the ingredient's measured portion weight.'''
    qty = _num(item.get('case_qty'))
    unit = item.get('case_unit')
    yield_pct = _num(item.get('yield_pct'))
    yield_pct = 100.0 if yield_pct is None else yield_pct
    if not qty or qty <= 0 or not unit:
        return None, 'no case yield'
    if unit == 'ea':
        per_each = _num(item.get('portions_per_each'))
        if not per_each or per_each <= 0:
            return None, 'no portions per each'
        return qty * per_each * yield_pct / 100.0, None
    grams = UNIT_GRAMS.get(unit)
    if grams is None:
        return None, f'unknown unit {unit}'
    weight = _num(portion_grams)
    if not weight or weight <= 0:
        return None, 'ingredient has no portion weight'
    return qty * grams * yield_pct / 100.0 / weight, None


def yield_formula(item, portion_grams):
    '''"20 lb × 454 g × 90% ÷ 146 g = 56.0 portions" for the UI.'''
    ppc, why = portions_per_case(item, portion_grams)
    qty = _num(item.get('case_qty')) or 0
    unit = item.get('case_unit') or ''
    y = _num(item.get('yield_pct'))
    y = 100.0 if y is None else y
    if ppc is None:
        return why
    if unit == 'ea':
        per = _num(item.get('portions_per_each'))
        text = f'{qty:g} ea × {per:g} portions'
        if y != 100:
            text += f' × {y:g}%'
        return f'{text} = {ppc:,.1f} portions per case'
    return (f'{qty:g} {unit} × {UNIT_GRAMS[unit]:g} g × {y:g}% ÷ {_num(portion_grams):g} g'
            f' = {ppc:,.1f} portions per case')


def yield_short(item):
    qty = _num(item.get('case_qty'))
    unit = item.get('case_unit')
    if not qty or not unit:
        return '—'
    if unit == 'ea':
        per = _num(item.get('portions_per_each'))
        return f'{qty:g} ea × {per:g}' if per else f'{qty:g} ea'
    y = _num(item.get('yield_pct'))
    return f'{qty:g} {unit} · {100.0 if y is None else y:g}%'


# --- reading files ------------------------------------------------------

def read_csv(path):
    '''(headers, rows as dicts). Tries UTF-8 then Windows-1252.'''
    last_error = None
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, newline='', encoding=encoding) as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                return [h.strip() for h in (reader.fieldnames or [])], rows
        except UnicodeDecodeError as e:
            last_error = e
    raise last_error


def missing_columns(settings, headers):
    '''Required fields this format can't find in `headers`.'''
    have = {_norm(h) for h in headers}
    cols = settings.get('columns', {})
    missing = []
    for key in REQUIRED_FIELDS:
        col = cols.get(key)
        if not col or _norm(col) not in have:
            missing.append(key)
    if not (_mapped(settings, 'amount', have) or _mapped(settings, 'unit_price', have)):
        missing.append('amount')
    return missing


def _mapped(settings, key, have):
    col = settings.get('columns', {}).get(key)
    return bool(col) and _norm(col) in have


def detect_format(headers, formats):
    '''The saved format whose mapped columns are all in `headers`
    (the one mapping the most columns wins), or None.'''
    best, best_count = None, -1
    have = {_norm(h) for h in headers}
    for fmt in formats:
        settings = fmt['settings']
        if missing_columns(settings, headers):
            continue
        count = sum(1 for col in settings.get('columns', {}).values() if col and _norm(col) in have)
        if count > best_count:
            best, best_count = fmt, count
    return best


def guess_columns(headers):
    '''A first guess at a new file's column mapping, by header name.'''
    hints = {
        'date': ('purchasedate', 'invoicedate', 'date'),
        'vendor': ('vendor', 'supplier', 'distributor'),
        'item_code': ('vpicode', 'itemcode', 'itemnumber', 'sku', 'supc', 'productcode', 'code'),
        'description': ('vpi', 'description', 'itemdescription', 'productdescription', 'item', 'product'),
        'pack_size': ('packsize', 'pack', 'size'),
        'quantity': ('quantity', 'qty', 'qtyshipped', 'cases'),
        'amount': ('amount', 'extendedprice', 'extprice', 'total', 'linetotal'),
        'unit_price': ('avgprice', 'unitprice', 'price', 'caseprice'),
        'location': ('locationname', 'location', 'store', 'site'),
        'inventory_item': ('inventoryitemname', 'inventoryitem'),
        'invoice': ('invoicenumber', 'invoice', 'invoiceno'),
    }
    squashed = {re.sub(r'[^a-z0-9]', '', h.lower()): h for h in headers}
    out, used = {}, set()
    for key, names in hints.items():
        for name in names:
            h = squashed.get(name)
            if h and h not in used:
                out[key] = h
                used.add(h)
                break
    return out


class Line:
    __slots__ = ('date', 'vendor', 'item_code', 'description', 'pack_size', 'quantity', 'amount',
                 'location', 'inventory_item', 'invoice', 'key')

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))


def parse_lines(rows, settings):
    '''Rows (dicts by header) → (lines, stats). Credits and unreadable
    rows are skipped and counted.'''
    cols = settings.get('columns', {})
    by_norm = {}
    if rows:
        by_norm = {_norm(h): h for h in rows[0].keys() if h is not None}

    def col(key):
        name = cols.get(key)
        return by_norm.get(_norm(name)) if name else None

    c = {key: col(key) for key, *_ in FIELDS}
    fmt = DATE_FORMATS.get(settings.get('date_format'), '%m/%d/%Y')
    use_unit_price = settings.get('price_from') == 'unit_price' or not c['amount']
    stats = collections.Counter()
    lines = []
    for row in rows:
        get = lambda key: (row.get(c[key]) if c[key] else None)  # noqa: E731
        raw_date = (get('date') or '').strip()
        try:
            day = datetime.datetime.strptime(raw_date.split(' ')[0], fmt).date()
        except ValueError:
            stats['unreadable'] += 1
            continue
        qty = _num(get('quantity'))
        if use_unit_price:
            price = _num(get('unit_price'))
            amount = None if price is None or qty is None else price * qty
        else:
            amount = _num(get('amount'))
        if qty is None or amount is None:
            stats['unreadable'] += 1
            continue
        if qty < 0 or amount < 0 or (settings.get('skip_credits', True) and qty <= 0):
            stats['credits'] += 1
            continue
        if qty == 0:
            stats['unreadable'] += 1
            continue
        line = Line(
            date=day,
            vendor=_clean(get('vendor')),
            item_code=_clean(get('item_code')),
            description=_clean(get('description')),
            pack_size=_clean(get('pack_size')),
            quantity=qty,
            amount=amount,
            location=_clean(get('location')) or 'All locations',
            inventory_item=_clean(get('inventory_item')),
            invoice=_clean(get('invoice')),
        )
        line.key = vendor_key(line.vendor, line.item_code, line.description, line.pack_size)
        lines.append(line)
    return lines, stats


# --- store: formats, vendor items, suppliers ------------------------------

def get_formats():
    with _connect() as con:
        rows = con.execute('SELECT id, name, settings FROM import_formats ORDER BY id;').fetchall()
        uses = dict(con.execute('SELECT format_id, COUNT(*) FROM import_batches GROUP BY format_id;').fetchall())
    out = []
    for r in rows:
        try:
            settings = json.loads(r['settings'])
        except ValueError:
            settings = default_settings()
        merged = default_settings()
        merged.update(settings)
        out.append({'id': r['id'], 'name': r['name'], 'settings': merged, 'uses': uses.get(r['id'], 0)})
    return out


def save_format(name, settings, format_id=None):
    with _connect() as con:
        if format_id:
            con.execute('UPDATE import_formats SET name = ?, settings = ? WHERE id = ?;',
                        (name, json.dumps(settings), format_id))
            return format_id
        return con.execute('INSERT INTO import_formats (name, settings) VALUES (?, ?);',
                           (name, json.dumps(settings))).lastrowid


def delete_format(format_id):
    with _connect() as con:
        con.execute('DELETE FROM import_formats WHERE id = ?;', (format_id,))


def get_vendor_items():
    '''Every vendor item with its ingredient's name and portion weight.'''
    with _connect() as con:
        rows = con.execute('''
            SELECT v.*, i.Name AS ingredient_name, i.Weight AS portion_grams, i.Unit AS ingredient_unit
            FROM vendor_items v LEFT JOIN Ingredients i ON i.Id = v.ingredient_id
            ORDER BY v.vendor_name COLLATE NOCASE, v.description COLLATE NOCASE;''').fetchall()
    return [dict(r) for r in rows]


def get_vendor_items_by_key():
    return {v['vendor_key']: v for v in get_vendor_items()}


def save_vendor_item(item):
    '''Insert or update by vendor_key; returns its id.'''
    fields = ('vendor_name', 'item_code', 'description', 'pack_size', 'inventory_item', 'gl_code',
              'status', 'ingredient_id', 'case_qty', 'case_unit', 'yield_pct', 'portions_per_each',
              'notes', 'last_case_price', 'last_seen')
    values = {k: item.get(k) for k in fields}
    if values['yield_pct'] is None:
        values['yield_pct'] = 100
    if not values['status']:
        values['status'] = 'new'
    with _connect() as con:
        row = con.execute('SELECT id FROM vendor_items WHERE vendor_key = ?;', (item['vendor_key'],)).fetchone()
        if row:
            sets = ', '.join(f'{k} = ?' for k in fields)
            con.execute(f"UPDATE vendor_items SET {sets}, updated_at = datetime('now', 'localtime') WHERE id = ?;",
                        [values[k] for k in fields] + [row['id']])
            return row['id']
        cols = ', '.join(fields)
        marks = ', '.join('?' for _ in fields)
        return con.execute(f"INSERT INTO vendor_items (vendor_key, {cols}, updated_at)"
                           f" VALUES (?, {marks}, datetime('now', 'localtime'));",
                           [item['vendor_key']] + [values[k] for k in fields]).lastrowid


def get_ingredients():
    '''Id, Name, Unit, Weight (portion grams), Cost (per portion).'''
    with _connect() as con:
        rows = con.execute('SELECT Id, Name, Unit, Weight, Cost FROM Ingredients'
                           ' ORDER BY Name COLLATE NOCASE;').fetchall()
    return [dict(r) for r in rows]


def get_suppliers():
    with _connect() as con:
        return [dict(r) for r in con.execute('SELECT id, name FROM suppliers ORDER BY name COLLATE NOCASE;')]


def match_supplier(vendor_name, suppliers, aliases=None):
    '''A supplier id for a vendor name in a file: a saved alias, an
    exact name, or a supplier whose name starts the vendor's name
    ("Sysco PAY OnLine - NO CHECKS" → Sysco). None if nothing fits.'''
    aliases = aliases or {}
    if vendor_name in aliases:
        sid = aliases[vendor_name]
        if any(s['id'] == sid for s in suppliers):
            return sid
    key = _norm(vendor_name)
    for s in suppliers:
        if _norm(s['name']) == key:
            return s['id']
    best = None
    for s in suppliers:
        name = _norm(s['name'])
        if name and (key.startswith(name + ' ') or key.startswith(name)) and \
                (best is None or len(name) > len(_norm(best['name']))):
            best = s
    return best['id'] if best else None


# --- suggestions --------------------------------------------------------

_STOP = {'the', 'and', 'with', 'for', 'fresh', 'frozen', 'case', 'bulk', 'pack', 'bag', 'sysco',
         'produce', 'dry', 'good', 'meat', 'dairy', 'prep', 'side', 'packaging', 'paper', 'herbs'}


def _tokens(text):
    words = re.findall(r'[a-z]+|\d+(?:\.\d+)?', _norm(text))
    out = set()
    for w in words:
        if w[0].isdigit():
            out.add(w)
            continue
        if len(w) < 3 or w in _STOP:
            continue
        if len(w) > 4 and w.endswith('ies'):
            w = w[:-3] + 'y'
        elif len(w) > 4 and w.endswith('oes'):
            w = w[:-2]
        elif len(w) > 3 and w.endswith('s') and not w.endswith('ss'):
            w = w[:-1]
        out.add(w)
    return out


def suggest_mapping(item, ingredients, vendor_items):
    '''A suggestion for a new vendor item, or None:
    {'ingredient_id', 'reason', and maybe case_qty/case_unit/yield_pct/
    portions_per_each copied from a sibling with the same pack}.

    First choice: other vendor items under the same inventory item that
    are already mapped (the inventory system already grouped them).
    Second: every word of an ingredient's name appears in the item's
    inventory name or description, and no other ingredient fits as well.'''
    inv = _norm(item.get('inventory_item'))
    if inv:
        siblings = [v for v in vendor_items if v['status'] == 'mapped' and v.get('ingredient_id')
                    and _norm(v.get('inventory_item')) == inv and v['vendor_key'] != item['vendor_key']]
        if siblings:
            counts = collections.Counter(v['ingredient_id'] for v in siblings)
            ing_id, n = counts.most_common(1)[0]
            name = next((i['Name'] for i in ingredients if i['Id'] == ing_id), '?')
            out = {'ingredient_id': ing_id,
                   'reason': (f'Suggested from the inventory item: its {n} other vendor item'
                              f'{"s are" if n != 1 else " is"} mapped to {name}.')}
            same_pack = next((v for v in siblings if v['ingredient_id'] == ing_id
                              and _norm(v.get('pack_size')) == _norm(item.get('pack_size'))), None)
            if same_pack:
                for k in ('case_qty', 'case_unit', 'yield_pct', 'portions_per_each', 'notes'):
                    out[k] = same_pack.get(k)
                out['reason'] += ' Its yield is copied from the one with the same pack size.'
            else:
                ref = next(v for v in siblings if v['ingredient_id'] == ing_id)
                out['yield_pct'] = ref.get('yield_pct')
                if ref.get('case_unit') == 'ea':
                    out['portions_per_each'] = ref.get('portions_per_each')
            return out
    text = ' '.join(filter(None, [
        (item.get('inventory_item') or '').split(' - ', 1)[-1], item.get('description')]))
    have = _tokens(text)
    if not have:
        return None
    scored = []
    for ing in ingredients:
        need = _tokens(ing['Name'])
        if need and need <= have:
            scored.append((len(need), ing))
    if not scored:
        return None
    scored.sort(key=lambda s: -s[0])
    if len(scored) > 1 and scored[1][0] == scored[0][0]:
        return None
    ing = scored[0][1]
    return {'ingredient_id': ing['Id'], 'reason': f'Matched by name: “{ing["Name"]}”.'}


# --- pricing ------------------------------------------------------------

def blend(entries, item_ppc):
    '''Total spend ÷ total portions for (vendor_item_id, qty, amount)
    entries; items without a yield are left out. Returns
    (per_portion, spend, portions, per_item_spend) or None.'''
    spend = portions = 0.0
    per_item = collections.Counter()
    for vid, qty, amount in entries:
        ppc = item_ppc.get(vid)
        if not ppc:
            continue
        spend += amount
        portions += qty * ppc
        per_item[vid] += amount
    if portions <= 0:
        return None
    return spend / portions, spend, portions, per_item


def price_points(daily, items, ingredients_by_id, basis):
    '''Ingredient prices from per-day totals.

    `daily`: iterable of (vendor_item_id, date, qty, amount).
    `items`: {vendor_item_id: vendor item dict (status, ingredient_id, yield)}.
    Returns {ingredient_id: [point, ...]} oldest first, each point
    {'date', 'label', 'per_portion', 'spend', 'portions', 'quantity',
    'items': {vid: spend}, 'lines'}.'''
    ppc = {}
    for vid, item in items.items():
        if item.get('status') != 'mapped' or not item.get('ingredient_id'):
            continue
        ing = ingredients_by_id.get(item['ingredient_id'])
        if ing is None:
            continue
        value, _ = portions_per_case(item, ing.get('Weight'))
        if value:
            ppc[vid] = value
    by_ing = collections.defaultdict(list)
    for vid, day, qty, amount in daily:
        if vid in ppc:
            by_ing[items[vid]['ingredient_id']].append((vid, day, qty, amount))
    out = {}
    for ing_id, entries in by_ing.items():
        if basis == 'latest':
            last = max(e[1] for e in entries)
            groups = {last: [e for e in entries if e[1] == last]}
        else:
            groups = collections.defaultdict(list)
            for e in entries:
                groups[week_start(e[1])].append(e)
        points = []
        for start in sorted(groups):
            group = groups[start]
            b = blend([(vid, qty, amount) for vid, _, qty, amount in group], ppc)
            if b is None:
                continue
            per_portion, spend, portions, per_item = b
            label = (f'week of {start:%b} {start.day}' if basis != 'latest'
                     else f'{start:%b} {start.day}')
            points.append({'date': start, 'label': label, 'per_portion': per_portion, 'spend': spend,
                           'portions': portions, 'quantity': sum(e[2] for e in group),
                           'items': dict(per_item), 'ppc': {v: ppc[v] for v in per_item}})
        if points:
            out[ing_id] = points
    return out


def item_portion_costs(daily, items, ingredients_by_id):
    '''{vendor_item_id: per-portion cost over all of `daily`} for mapped
    items with a yield — what the "vendor items disagree" flag compares.'''
    totals = collections.defaultdict(lambda: [0.0, 0.0])
    for vid, _, qty, amount in daily:
        totals[vid][0] += qty
        totals[vid][1] += amount
    out = {}
    for vid, (qty, amount) in totals.items():
        item = items.get(vid)
        if not item or item.get('status') != 'mapped' or not item.get('ingredient_id') or qty <= 0:
            continue
        ing = ingredients_by_id.get(item['ingredient_id'])
        if ing is None:
            continue
        ppc, _ = portions_per_case(item, ing.get('Weight'))
        if ppc:
            out[vid] = amount / qty / ppc
    return out


def flags_for(ing, points, item_costs, items):
    '''Why this ingredient's import needs a look: a list of
    (title, detail) pairs, empty when it's fine.'''
    out = []
    current = _num(ing.get('Cost'))
    latest = points[-1]['per_portion'] if points else None
    if current and latest:
        change = latest / current - 1
        if abs(change) > JUMP_LIMIT:
            out.append((f'{"Jumped" if change > 0 else "Dropped"} {change * 100:+.0f}%',
                        f'{money(current, 3)} → {money(latest, 3)} a portion'))
    mine = {vid: c for vid, c in item_costs.items() if items[vid].get('ingredient_id') == ing['Id']}
    if len(mine) > 1:
        lo_vid = min(mine, key=mine.get)
        hi_vid = max(mine, key=mine.get)
        if mine[lo_vid] > 0 and mine[hi_vid] / mine[lo_vid] > DISAGREE_LIMIT:
            lo, hi = items[lo_vid], items[hi_vid]
            out.append((f'Vendor items disagree {mine[hi_vid] / mine[lo_vid]:.1f}×',
                        f'{lo["description"]} {lo.get("pack_size") or ""} {money(mine[lo_vid], 3)} vs'
                        f' {hi["description"]} {hi.get("pack_size") or ""} {money(mine[hi_vid], 3)} a portion'))
    return out


def vendor_item_flags(items=None):
    '''{vendor_item_id: (title, detail)} for mapped items whose last
    per-portion cost is more than DISAGREE_LIMIT away from the median of
    the other items mapped to the same ingredient.'''
    items = items if items is not None else get_vendor_items()
    costs = {}
    for v in items:
        if v['status'] != 'mapped' or not v.get('ingredient_id') or not v.get('last_case_price'):
            continue
        ppc, _ = portions_per_case(v, v.get('portion_grams'))
        if ppc:
            costs[v['id']] = (v['ingredient_id'], v['last_case_price'] / ppc)
    by_ing = collections.defaultdict(list)
    for vid, (ing, cost) in costs.items():
        by_ing[ing].append((vid, cost))
    out = {}
    names = {v['id']: v for v in items}
    for ing, group in by_ing.items():
        if len(group) < 2:
            continue
        for vid, cost in group:
            others = sorted(c for v2, c in group if v2 != vid)
            mid = others[len(others) // 2]
            if mid <= 0:
                continue
            ratio = cost / mid
            if ratio > DISAGREE_LIMIT or ratio < 1 / DISAGREE_LIMIT:
                out[vid] = (f'{ratio:.1f}× the other {names[vid].get("ingredient_name") or "ingredient"} items'
                            if ratio > 1 else
                            f'{1 / ratio:.1f}× cheaper than the other {names[vid].get("ingredient_name") or ""} items',
                            f'{money(cost, 3)} a portion against {money(mid, 3)} for the others.'
                            ' Check this case yield.')
    return out


# --- an import ----------------------------------------------------------

class ImportSession:
    '''One file being imported. Build it with `ImportSession.open(path)`,
    then set `fmt` (if it wasn't recognized), choose locations and GL
    codes, map new items, `review()`, `apply()`.'''

    def __init__(self, path, headers, rows):
        self.path = path
        self.file_name = os.path.basename(path)
        self.headers = headers
        self.rows = rows
        self.fmt = None
        self.settings = default_settings()
        self.lines = []
        self.stats = collections.Counter()
        self.basis = 'weekly'
        self.excluded_locations = set()
        self.ingredients = []
        self.ingredients_by_id = {}
        self.known = {}             # vendor_key → saved vendor item
        self.pending = {}           # vendor_key → vendor item edited in this import
        self.reload_library()

    @classmethod
    def open(cls, path):
        headers, rows = read_csv(path)
        session = cls(path, headers, rows)
        fmt = detect_format(headers, get_formats())
        if fmt:
            session.use_format(fmt)
        return session

    def reload_library(self):
        self.ingredients = get_ingredients()
        self.ingredients_by_id = {i['Id']: i for i in self.ingredients}
        self.known = get_vendor_items_by_key()

    def use_format(self, fmt):
        '''fmt: {'id', 'name', 'settings'}; id None for a format not saved yet.'''
        self.fmt = fmt
        self.settings = dict(fmt['settings'])
        self.basis = self.settings.get('basis', 'weekly')
        self.lines, self.stats = parse_lines(self.rows, self.settings)
        present_locs = {l.location for l in self.lines}
        self.excluded_locations = set(self.settings.get('excluded_locations') or []) & present_locs

    # --- what's in the file ---

    @property
    def date_range(self):
        if not self.lines:
            return None, None
        days = [l.date for l in self.lines]
        return min(days), max(days)

    def vendors(self):
        return sorted({l.vendor for l in self.lines}, key=str.casefold)

    def locations(self):
        '''[(location, line count)], by name.'''
        c = collections.Counter(l.location for l in self.lines)
        return sorted(c.items(), key=lambda kv: kv[0].casefold())

    def included_lines(self, excluded_locations=None):
        ex = self.excluded_locations if excluded_locations is None else excluded_locations
        return [l for l in self.lines if l.location not in ex]

    def avg_case_prices(self):
        '''{vendor_key: average case price} over every line in the file.'''
        totals = collections.defaultdict(lambda: [0.0, 0.0])
        for l in self.lines:
            totals[l.key][0] += l.quantity
            totals[l.key][1] += l.amount
        return {k: a / q for k, (q, a) in totals.items() if q}

    def item_for(self, key):
        return self.pending.get(key) or self.known.get(key)

    def file_items(self):
        '''One dict per vendor item in the file, with
        purchase totals; saved fields come from the library or from edits
        in this import.'''
        groups = collections.OrderedDict()
        for l in self.lines:
            g = groups.get(l.key)
            if g is None:
                g = groups[l.key] = {'key': l.key, 'line': l, 'qty': 0.0, 'amount': 0.0, 'lines': 0,
                                     'last': l.date, 'locations': set()}
            g['qty'] += l.quantity
            g['amount'] += l.amount
            g['lines'] += 1
            g['last'] = max(g['last'], l.date)
            g['locations'].add(l.location)
        out = []
        for key, g in groups.items():
            l = g['line']
            saved = self.item_for(key)
            item = dict(saved) if saved else {
                'vendor_key': key, 'vendor_name': l.vendor, 'item_code': l.item_code,
                'description': l.description, 'pack_size': l.pack_size,
                'inventory_item': l.inventory_item, 'status': 'new',
                'yield_pct': 100,
            }
            item.update({'_qty': g['qty'], '_amount': g['amount'], '_lines': g['lines'],
                         '_last': g['last'], '_locations': len(g['locations']),
                         '_avg_case': g['amount'] / g['qty'] if g['qty'] else None,
                         '_saved': saved is not None and key not in self.pending})
            out.append(item)
        return out

    def counts(self):
        items = self.file_items()
        c = collections.Counter(self._state(i) for i in items)
        c['total'] = len(items)
        return c

    def _state(self, item):
        status = item.get('status') or 'new'
        if status == 'mapped' and item.get('ingredient_id'):
            return 'mapped'
        if status == 'ignored':
            return 'ignored'
        return 'new'

    def new_items(self):
        '''Items to map: never mapped or ignored before (including ones
        skipped in an earlier import), biggest spend first.'''
        items = [i for i in self.file_items() if self._state(i) == 'new' or i['vendor_key'] in self.pending]
        items.sort(key=lambda i: -i['_amount'])
        return items

    def suggestion(self, item):
        others = [v for v in list(self.known.values()) + list(self.pending.values())]
        return suggest_mapping(item, self.ingredients, others)

    def set_item(self, item):
        '''Remember a mapped / ignored / skipped item for this import;
        written to the library on apply.'''
        clean = {k: v for k, v in item.items() if not k.startswith('_')}
        self.pending[clean['vendor_key']] = clean

    # --- locations ---

    def location_swings(self, excluded, limit=None):
        '''How leaving locations out moves blended case prices: rows for
        vendor items whose price moves by SWING_MIN or more, or that only
        the left-out locations bought —
        {'ingredient', 'item', 'low', 'high', 'all', 'selected', 'change'},
        biggest move first. Empty when nothing is left out.'''
        if not excluded:
            return []
        per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
        for l in self.lines:
            t = per[l.key][l.location]
            t[0] += l.quantity
            t[1] += l.amount
        rows = []
        for key, locs in per.items():
            if len(locs) < 2:
                continue
            avgs = [a / q for q, a in locs.values() if q > 0]
            if not avgs:
                continue
            all_q = sum(q for q, _ in locs.values())
            all_a = sum(a for _, a in locs.values())
            sel = [(q, a) for loc, (q, a) in locs.items() if loc not in excluded]
            sel_q = sum(q for q, _ in sel)
            sel_a = sum(a for _, a in sel)
            all_avg = all_a / all_q
            sel_avg = sel_a / sel_q if sel_q else None
            item = self.item_for(key)
            if item and item.get('status') == 'ignored':
                continue   # never priced, so its swing doesn't matter
            line = next(l for l in self.lines if l.key == key)
            ing = None
            if item and item.get('status') == 'mapped' and item.get('ingredient_id'):
                ing = self.ingredients_by_id.get(item['ingredient_id'], {}).get('Name')
            rows.append({
                'ingredient': ing or '—',
                'item': f'{line.vendor} · {line.description} · {line.pack_size}'.strip(' ·'),
                'low': min(avgs), 'high': max(avgs), 'all': all_avg, 'selected': sel_avg,
                'change': None if sel_avg is None else sel_avg / all_avg - 1,
                'spread': max(avgs) / min(avgs) - 1 if min(avgs) > 0 else 0,
                'mapped': ing is not None,
            })
        rows = [r for r in rows if r['change'] is None or abs(r['change']) >= SWING_MIN]
        rows.sort(key=lambda r: (r['change'] is None, -abs(r['change'] or 0), not r['mapped']))
        return rows[:limit] if limit else rows

    def same_price_share(self):
        '''Share of vendor items bought at 2+ locations whose price was
        the same everywhere (within half a percent).'''
        per = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
        for l in self.lines:
            t = per[l.key][l.location]
            t[0] += l.quantity
            t[1] += l.amount
        multi = [locs for locs in per.values() if len(locs) > 1]
        if not multi:
            return None
        same = 0
        for locs in multi:
            avgs = [a / q for q, a in locs.values() if q > 0]
            if avgs and min(avgs) > 0 and max(avgs) / min(avgs) - 1 < 0.005:
                same += 1
        return same / len(multi)

    # --- review & apply ---

    def _items_now(self):
        '''{vendor_key: item} with this import's edits on top.'''
        items = dict(self.known)
        items.update(self.pending)
        return items

    def daily_totals(self):
        '''{vendor_key: {date: [qty, amount, lines]}} for included lines.'''
        out = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0, 0]))
        for l in self.included_lines():
            t = out[l.key][l.date]
            t[0] += l.quantity
            t[1] += l.amount
            t[2] += 1
        return out

    def review(self):
        '''One row per ingredient that gets prices:
        {'ingredient', 'points', 'current', 'latest', 'change', 'flags',
        'sources' (vendor item descriptions), 'first'} — biggest change
        first, flagged first.'''
        items = self._items_now()
        by_key = {k: dict(v, id=k) for k, v in items.items()}
        daily = [(key, day, t[0], t[1]) for key, days in self.daily_totals().items()
                 for day, t in days.items() if key in by_key]
        points = price_points(daily, by_key, self.ingredients_by_id, self.basis)
        costs = item_portion_costs(daily, by_key, self.ingredients_by_id)
        rows = []
        for ing_id, pts in points.items():
            ing = self.ingredients_by_id[ing_id]
            current = _num(ing.get('Cost'))
            latest = pts[-1]['per_portion']
            change = None if not current else latest / current - 1
            sources = sorted({key for p in pts for key in p['items']})
            rows.append({
                'ingredient': ing, 'points': pts, 'current': current, 'latest': latest, 'change': change,
                'flags': flags_for(ing, pts, costs, by_key),
                'sources': [by_key[k] for k in sources], 'first': current is None or current == 0,
            })
        rows.sort(key=lambda r: (not r['flags'], -(abs(r['change']) if r['change'] is not None else 0),
                                 r['ingredient']['Name'].casefold()))
        return rows

    def unpriced(self):
        '''Mapped items in the file that can't price yet, with why:
        [(item, reason)].'''
        out = []
        for item in self.file_items():
            if self._state(item) != 'mapped':
                continue
            ing = self.ingredients_by_id.get(item['ingredient_id'])
            if ing is None:
                out.append((item, 'its ingredient was deleted'))
                continue
            ppc, why = portions_per_case(item, ing.get('Weight'))
            if ppc is None:
                out.append((item, why))
        return out

    def overlapping_batches(self):
        start, end = self.date_range
        if not start:
            return []
        with _connect() as con:
            rows = con.execute('SELECT id, imported_at, file_name, date_from, date_to FROM import_batches'
                               ' WHERE date_from <= ? AND date_to >= ? ORDER BY id;',
                               (end.isoformat(), start.isoformat())).fetchall()
        return [dict(r) for r in rows]

    def apply(self, ingredient_ids, remember=True):
        '''Write the vendor items edited in this import, the batch and its
        per-day totals, and weekly (or latest) prices for `ingredient_ids`.
        Older imported prices for the same ingredient and date are
        replaced. Returns the batch id.'''
        ingredient_ids = set(ingredient_ids)
        start, end = self.date_range
        suppliers = get_suppliers()
        aliases = dict(self.settings.get('vendor_suppliers') or {})
        con = _connect()
        try:
            con.execute('BEGIN IMMEDIATE;')
            # Suppliers for every vendor in the included lines.
            vendor_supplier = {}
            for vendor in sorted({l.vendor for l in self.included_lines()}):
                sid = match_supplier(vendor, suppliers, aliases)
                if sid is None:
                    sid = con.execute('INSERT INTO suppliers (name) VALUES (?);', (vendor,)).lastrowid
                    suppliers.append({'id': sid, 'name': vendor})
                vendor_supplier[vendor] = sid
                aliases[vendor] = sid
            # Vendor items: save edits, and make sure every included
            # item that isn't ignored has a row (new ones stay 'new').
            totals = self.daily_totals()
            last_price = {}
            for key, days in totals.items():
                q = sum(t[0] for t in days.values())
                a = sum(t[1] for t in days.values())
                last_day = max(days)
                last_price[key] = (a / q if q else None, last_day)
            ids = {}
            sample = {}
            for l in self.included_lines():
                sample.setdefault(l.key, l)
            for key, l in sample.items():
                item = self.item_for(key) or {
                    'vendor_key': key, 'vendor_name': l.vendor, 'item_code': l.item_code,
                    'description': l.description, 'pack_size': l.pack_size,
                    'inventory_item': l.inventory_item, 'status': 'new',
                }
                item = dict(item)
                price, day = last_price.get(key, (None, None))
                if price is not None:
                    item['last_case_price'] = round(price, 4)
                    item['last_seen'] = day.isoformat()
                ids[key] = _save_item(con, item)
            for key, item in self.pending.items():
                if key not in ids:
                    ids[key] = _save_item(con, item)
            settings = {'basis': self.basis, 'excluded_locations': sorted(self.excluded_locations),
                    'format': self.fmt and self.fmt.get('name')}
            batch_id = con.execute(
                "INSERT INTO import_batches (imported_at, file_name, format_id, date_from, date_to, settings)"
                " VALUES (datetime('now', 'localtime'), ?, ?, ?, ?, ?);",
                (self.file_name, self.fmt and self.fmt.get('id'), start and start.isoformat(),
                 end and end.isoformat(), json.dumps(settings))).lastrowid
            for key, days in totals.items():
                item = self.item_for(key)
                if item and item.get('status') == 'ignored':
                    continue
                for day, (q, a, n) in days.items():
                    con.execute('INSERT INTO import_lines (batch_id, vendor_item_id, purchase_date, quantity,'
                                ' amount, line_count) VALUES (?, ?, ?, ?, ?, ?);',
                                (batch_id, ids[key], day.isoformat(), q, a, n))
            _write_prices(con, batch_id, self.basis, ingredient_ids)
            if remember and self.fmt and self.fmt.get('id'):
                saved = dict(self.settings)
                saved.pop('excluded_gl', None)
                saved['columns'] = {k: v for k, v in saved.get('columns', {}).items() if k != 'gl_code'}
                saved.update({'basis': self.basis,
                              'excluded_locations': sorted(self.excluded_locations),
                              'vendor_suppliers': aliases,
                              'headers': self.headers,
                              'sample': {h: (self.rows[0].get(h) or '') for h in self.headers} if self.rows else {}})
                con.execute('UPDATE import_formats SET settings = ? WHERE id = ?;',
                            (json.dumps(saved), self.fmt['id']))
            con.execute('COMMIT;')
        except BaseException:
            con.execute('ROLLBACK;')
            raise
        finally:
            con.close()
        self.pending.clear()
        self.reload_library()
        return batch_id


def _save_item(con, item):
    fields = ('vendor_name', 'item_code', 'description', 'pack_size', 'inventory_item', 'gl_code',
              'status', 'ingredient_id', 'case_qty', 'case_unit', 'yield_pct', 'portions_per_each',
              'notes', 'last_case_price', 'last_seen')
    values = [item.get(k) for k in fields]
    values[fields.index('yield_pct')] = item.get('yield_pct') if item.get('yield_pct') is not None else 100
    values[fields.index('status')] = item.get('status') or 'new'
    row = con.execute('SELECT id FROM vendor_items WHERE vendor_key = ?;', (item['vendor_key'],)).fetchone()
    if row:
        sets = ', '.join(f'{k} = ?' for k in fields)
        con.execute(f"UPDATE vendor_items SET {sets}, updated_at = datetime('now', 'localtime') WHERE id = ?;",
                    values + [row[0]])
        return row[0]
    return con.execute(f"INSERT INTO vendor_items (vendor_key, {', '.join(fields)}, updated_at)"
                       f" VALUES (?, {', '.join('?' for _ in fields)}, datetime('now', 'localtime'));",
                       [item['vendor_key']] + values).lastrowid


def _batch_points(con, batch_id, basis, ingredient_ids=None):
    '''Price points for a stored batch with today's vendor item yields.'''
    items = {r['id']: dict(r) for r in con.execute('SELECT * FROM vendor_items;')}
    ings = {r['Id']: dict(r) for r in con.execute('SELECT Id, Name, Unit, Weight, Cost FROM Ingredients;')}
    daily = [(r['vendor_item_id'], datetime.date.fromisoformat(r['purchase_date']), r['quantity'], r['amount'])
             for r in con.execute('SELECT * FROM import_lines WHERE batch_id = ?;', (batch_id,))
             if r['vendor_item_id'] in items]
    points = price_points(daily, items, ings, basis)
    if ingredient_ids is not None:
        points = {k: v for k, v in points.items() if k in ingredient_ids}
    return points, items, ings, daily


def _write_prices(con, batch_id, basis, ingredient_ids):
    points, items, ings, _ = _batch_points(con, batch_id, basis, ingredient_ids)
    supplier_of = _supplier_lookup(con)
    touched = set()
    for ing_id, pts in points.items():
        for p in pts:
            main_vid = max(p['items'], key=p['items'].get)
            ppc = p['ppc'][main_vid]
            item = items[main_vid]
            day = p['date'].isoformat()
            # A later import of the same week wins: re-pricing an older
            # batch leaves it alone, and a new one replaces older ones.
            if con.execute('SELECT 1 FROM ingredient_prices WHERE ingredient_id = ? AND effective_date = ?'
                           ' AND import_batch_id > ?;', (ing_id, day, batch_id)).fetchone():
                continue
            con.execute('DELETE FROM ingredient_prices WHERE ingredient_id = ? AND effective_date = ?'
                        ' AND import_batch_id IS NOT NULL AND import_batch_id < ?;', (ing_id, day, batch_id))
            n = len(p['items'])
            note = (f'Import #{batch_id}, {p["label"]}: {money(p["spend"])} across {n} vendor item'
                    f'{"s" if n != 1 else ""} ({p["quantity"]:g} units). Case: {item["description"]}'
                    f' {item.get("pack_size") or ""} = {ppc:,.1f} portions.')
            con.execute('INSERT INTO ingredient_prices (ingredient_id, supplier_id, case_price, units_per_case,'
                        ' effective_date, notes, is_auto_generated, import_batch_id)'
                        ' VALUES (?, ?, ?, ?, ?, ?, 1, ?);',
                        (ing_id, supplier_of(item.get('vendor_name')), round(p['per_portion'] * ppc, 4),
                         round(ppc, 4), day, note, batch_id))
        touched.add(ing_id)
    _recompute_costs(con, touched)
    return touched


def _supplier_lookup(con):
    suppliers = [dict(r) for r in con.execute('SELECT id, name FROM suppliers;')]
    aliases = {}
    for (settings,) in con.execute('SELECT settings FROM import_formats;'):
        try:
            aliases.update(json.loads(settings).get('vendor_suppliers') or {})
        except ValueError:
            pass
    return lambda name: match_supplier(name or '', suppliers, aliases)


def _recompute_costs(con, ingredient_ids):
    for ing_id in ingredient_ids:
        con.execute('''UPDATE Ingredients SET Cost = COALESCE((
                SELECT unit_price FROM ingredient_prices
                WHERE ingredient_id = ?1 AND effective_date <= date('now')
                ORDER BY effective_date DESC, id DESC LIMIT 1), Cost)
            WHERE Id = ?1;''', (ing_id,))


# --- history: undo and re-price ------------------------------------------

def get_batches():
    with _connect() as con:
        rows = con.execute('''
            SELECT b.*,
                (SELECT COUNT(DISTINCT ingredient_id) FROM ingredient_prices p WHERE p.import_batch_id = b.id)
                    AS ingredient_count,
                (SELECT COUNT(*) FROM ingredient_prices p WHERE p.import_batch_id = b.id) AS price_count,
                (SELECT COUNT(DISTINCT v.id) FROM import_lines l JOIN vendor_items v ON v.id = l.vendor_item_id
                    WHERE l.batch_id = b.id AND v.updated_at > b.imported_at) AS changed_since
            FROM import_batches b ORDER BY b.id DESC;''').fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d['settings'] = json.loads(d['settings'] or '{}')
        except ValueError:
            d['settings'] = {}
        out.append(d)
    return out


def undo_batch(batch_id):
    '''Remove every price the import wrote and its stored totals.
    Returns the ingredient ids whose prices changed.'''
    con = _connect()
    try:
        con.execute('BEGIN IMMEDIATE;')
        touched = {r[0] for r in con.execute(
            'SELECT DISTINCT ingredient_id FROM ingredient_prices WHERE import_batch_id = ?;', (batch_id,))}
        con.execute('DELETE FROM ingredient_prices WHERE import_batch_id = ?;', (batch_id,))
        con.execute('DELETE FROM import_lines WHERE batch_id = ?;', (batch_id,))
        con.execute('DELETE FROM import_batches WHERE id = ?;', (batch_id,))
        _recompute_costs(con, touched)
        con.execute('COMMIT;')
    except BaseException:
        con.execute('ROLLBACK;')
        raise
    finally:
        con.close()
    # Weeks this import had replaced in older imports come back.
    if touched:
        with _connect() as c2:
            older = [r[0] for r in c2.execute('SELECT id FROM import_batches WHERE id < ? ORDER BY id DESC;',
                                              (batch_id,))]
        for older_id in older:
            reprice_batch(older_id, ingredient_ids=touched)
    return touched


def reprice_batch(batch_id, ingredient_ids=None, skip_flagged=True):
    '''Recompute a batch's prices with today's vendor item yields.
    `ingredient_ids` limits it to some ingredients (None: all in the
    batch). Flagged ingredients are left as they were when
    `skip_flagged`. Returns (repriced ids, [(name, flag title)]).'''
    con = _connect()
    try:
        con.execute('BEGIN IMMEDIATE;')
        row = con.execute('SELECT settings FROM import_batches WHERE id = ?;', (batch_id,)).fetchone()
        if row is None:
            con.execute('ROLLBACK;')
            return set(), []
        basis = (json.loads(row['settings'] or '{}') or {}).get('basis', 'weekly')
        points, items, ings, daily = _batch_points(con, batch_id, basis, ingredient_ids)
        costs = item_portion_costs(daily, items, ings)
        # Flags compare with the price before this batch, not its own.
        skipped, todo = [], set()
        for ing_id, pts in points.items():
            before = con.execute('SELECT unit_price FROM ingredient_prices WHERE ingredient_id = ?'
                                 ' AND (import_batch_id IS NULL OR import_batch_id != ?)'
                                 ' AND effective_date < ? ORDER BY effective_date DESC, id DESC LIMIT 1;',
                                 (ing_id, batch_id, pts[0]['date'].isoformat())).fetchone()
            ing = dict(ings[ing_id], Cost=before[0] if before else None)
            fl = flags_for(ing, pts, costs, items)
            if fl and skip_flagged:
                skipped.append((ing['Name'], fl[0][0]))
            else:
                todo.add(ing_id)
        # Ingredients this batch priced before but can't now (unmapped)
        # lose those prices; flagged ones keep theirs.
        old = {r[0] for r in con.execute(
            'SELECT DISTINCT ingredient_id FROM ingredient_prices WHERE import_batch_id = ?;', (batch_id,))}
        if ingredient_ids is not None:
            old &= set(ingredient_ids)
        clear = todo | (old - set(points))
        for ing_id in clear:
            con.execute('DELETE FROM ingredient_prices WHERE import_batch_id = ? AND ingredient_id = ?;',
                        (batch_id, ing_id))
        written = _write_prices(con, batch_id, basis, todo)
        _recompute_costs(con, clear)
        con.execute('COMMIT;')
    except BaseException:
        con.execute('ROLLBACK;')
        raise
    finally:
        con.close()
    return written, skipped


def batches_with_item(vendor_item_id):
    with _connect() as con:
        return [r[0] for r in con.execute('SELECT DISTINCT batch_id FROM import_lines WHERE vendor_item_id = ?'
                                          ' ORDER BY batch_id;', (vendor_item_id,))]


def update_vendor_item(item, reprice=True):
    '''Save a vendor item edited on the Vendor items page and re-price
    the imports that bought it, for its old and new ingredient.
    Returns the number of batches re-priced.'''
    with _connect() as con:
        old = con.execute('SELECT ingredient_id FROM vendor_items WHERE id = ?;', (item['id'],)).fetchone()
    old_ing = old[0] if old else None
    save_vendor_item(item)
    if not reprice:
        return 0
    scope = {i for i in (old_ing, item.get('ingredient_id')) if i}
    batches = batches_with_item(item['id'])
    for b in batches:
        reprice_batch(b, ingredient_ids=scope, skip_flagged=False)
    return len(batches)
