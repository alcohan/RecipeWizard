'''A recipe's cost over time: today's recipe at past prices.

Framework-agnostic. The inputs come from db.recipe_cost_history_inputs():
the recipe's ingredients with their quantity per serving (sub-recipes
expanded), and every price entry those ingredients have. build() lays
the costs on a Monday-start week grid, one point per week, using the
price in effect at the end of each week (or today, for this week). That
matches how purchase import dates its weekly prices, and the last point
matches the cost the recipe tab shows.

Rules:
- Quantities are today's: the line moves only when prices do.
- Before an ingredient's first price, its first price is used, so the
  line runs back as far as any ingredient has history.
- An ingredient with no price history uses its current cost; one with
  neither counts as $0 and is listed in `unpriced`.

movers() ranks ingredients by how much each changed the cost per serving
between two weeks; summary() gives the headline numbers.
'''
import datetime
from dataclasses import dataclass, field


RANGES = [('3m', '3 months', 91), ('6m', '6 months', 182), ('1y', '1 year', 365), ('all', 'All', None)]
DEFAULT_RANGE = '6m'
_MIN_CHANGE = 0.005   # under half a cent per serving counts as unchanged


@dataclass
class Component:
    ingredient_id: int
    name: str
    unit: str
    qty: float                     # per serving, in the ingredient's unit
    current_price: float = None    # Ingredients.Cost; None when unset
    color: str = ''


@dataclass
class Price:
    ingredient_id: int
    date: datetime.date
    unit_price: float
    batch_id: int = None
    seq: int = 0                   # ingredient_prices.id: breaks same-day ties


@dataclass
class CostHistory:
    weeks: list = field(default_factory=list)       # Monday of each week
    costs: list = field(default_factory=list)       # cost per serving, per week
    lines: list = field(default_factory=list)       # per week: {ingredient_id: cost per serving}
    unit_prices: list = field(default_factory=list)  # per week: {ingredient_id: unit price}
    batches: dict = field(default_factory=dict)     # week index: [import batch ids that priced it]
    components: dict = field(default_factory=dict)  # ingredient_id: Component
    unpriced: list = field(default_factory=list)    # Components with no price at all

    def __len__(self):
        return len(self.weeks)


def from_inputs(inputs):
    '''(components, prices) from db.recipe_cost_history_inputs().'''
    comps = [Component(int(r['ingredient_id']), r['name'] or '', r['unit'] or '', float(r['qty'] or 0),
                       float(r['cost']) if r['cost'] is not None else None, r['color'] or '')
             for r in inputs['components']]
    prices = []
    for r in inputs['prices']:
        try:
            day = datetime.date.fromisoformat(str(r['effective_date'])[:10])
        except ValueError:
            continue
        prices.append(Price(int(r['ingredient_id']), day, float(r['unit_price']),
                            r.get('import_batch_id'), int(r['id'])))
    return comps, prices


def week_start(day):
    return day - datetime.timedelta(days=day.weekday())


def range_start(key, today=None):
    '''The first day a range covers, or None for All.'''
    today = today or datetime.date.today()
    days = next((d for k, _label, d in RANGES if k == key), None)
    return today - datetime.timedelta(days=days) if days else None


def _price_lookup(prices):
    by_ing = {}
    for p in sorted(prices, key=lambda p: (p.date, p.seq)):
        by_ing.setdefault(p.ingredient_id, []).append(p)
    return by_ing


def _price_at(entries, day):
    '''The entry in effect on `day`: the latest dated on or before it,
    or the first one when `day` is before all of them.'''
    chosen = entries[0]
    for p in entries:
        if p.date <= day:
            chosen = p
        else:
            break
    return chosen


def build(components, prices, since=None, today=None):
    '''CostHistory over the weeks from the earliest price (or `since`,
    whichever is later) to this week. Empty when there's no history.'''
    today = today or datetime.date.today()
    comps = {c.ingredient_id: c for c in components}
    by_ing = {k: v for k, v in _price_lookup(prices).items() if k in comps}
    hist = CostHistory(components=comps)
    hist.unpriced = [c for c in components if c.ingredient_id not in by_ing and not c.current_price]
    dated = [p.date for entries in by_ing.values() for p in entries if p.date <= today]
    if not dated:
        return hist
    first = week_start(min(dated))
    if since is not None:
        first = max(first, week_start(since))
    last = week_start(today)
    week = first
    while week <= last:
        end = min(week + datetime.timedelta(days=6), today)
        units, lines = {}, {}
        for iid, comp in comps.items():
            entries = by_ing.get(iid)
            if entries:
                unit = float(_price_at(entries, end).unit_price or 0)
            else:
                unit = float(comp.current_price or 0)
            units[iid] = unit
            lines[iid] = unit * comp.qty
        hist.weeks.append(week)
        hist.unit_prices.append(units)
        hist.lines.append(lines)
        hist.costs.append(sum(lines.values()))
        week += datetime.timedelta(days=7)
    index = {w: i for i, w in enumerate(hist.weeks)}
    for entries in by_ing.values():
        for p in entries:
            i = index.get(week_start(p.date))
            if i is not None and p.batch_id is not None and p.batch_id not in hist.batches.get(i, []):
                hist.batches.setdefault(i, []).append(p.batch_id)
    for ids in hist.batches.values():
        ids.sort()
    return hist


@dataclass
class Mover:
    ingredient_id: int
    name: str
    unit: str
    qty: float
    color: str
    price_from: float
    price_to: float
    change: float          # cost per serving, to − from


def movers(hist, i, j):
    '''Ingredients whose cost per serving changed between weeks i and j,
    biggest change first, and how many didn't change.'''
    if not hist.weeks:
        return [], 0
    a, b = sorted((i, j))
    rows, unchanged = [], 0
    for iid, comp in hist.components.items():
        delta = hist.lines[b][iid] - hist.lines[a][iid]
        if abs(delta) < _MIN_CHANGE:
            unchanged += 1
            continue
        rows.append(Mover(iid, comp.name, comp.unit, comp.qty, comp.color,
                          hist.unit_prices[a][iid], hist.unit_prices[b][iid], delta))
    rows.sort(key=lambda m: (-abs(m.change), m.name.casefold()))
    return rows, unchanged


@dataclass
class Summary:
    now: float
    now_week: datetime.date
    change: float              # from week i to week j
    change_pct: float          # None when the start cost is 0
    low: float
    low_week: datetime.date
    high: float
    high_week: datetime.date
    food_cost: float = None    # now ÷ menu price, as a fraction
    food_cost_change: float = None   # in percentage points
    room: float = None         # how much cost can rise before the target


def summary(hist, i, j, menu_price=None, target=None):
    if not hist.weeks:
        return None
    a, b = sorted((i, j))
    now = hist.costs[-1]
    change = hist.costs[b] - hist.costs[a]
    pct = change / hist.costs[a] if hist.costs[a] else None
    lo = min(range(len(hist)), key=lambda k: (hist.costs[k], k))
    hi = max(range(len(hist)), key=lambda k: (hist.costs[k], k))
    s = Summary(now, hist.weeks[-1], change, pct, hist.costs[lo], hist.weeks[lo], hist.costs[hi], hist.weeks[hi])
    if menu_price:
        s.food_cost = now / menu_price
        s.food_cost_change = (hist.costs[b] - hist.costs[a]) / menu_price * 100
        if target:
            s.room = target * menu_price - now
    return s
