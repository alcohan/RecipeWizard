import datetime

import db
from utilities import cost_history as ch

D = datetime.date


def _comp(iid, qty, cost=None, name=None):
    return ch.Component(iid, name or f'ing{iid}', 'oz', qty, cost)


def test_weekly_points_use_price_in_effect_at_week_end():
    comps = [_comp(1, 2.0), _comp(2, 1.0)]
    prices = [ch.Price(1, D(2026, 10, 5), 1.00, seq=1), ch.Price(1, D(2026, 10, 14), 1.50, batch_id=7, seq=2),
              ch.Price(2, D(2026, 10, 5), 0.50, seq=3)]
    h = ch.build(comps, prices, today=D(2026, 10, 21))
    assert h.weeks == [D(2026, 10, 5), D(2026, 10, 12), D(2026, 10, 19)]
    assert h.costs == [2.5, 3.5, 3.5]
    assert h.batches == {1: [7]}


def test_first_price_backfills_and_unpriced_counts_zero():
    comps = [_comp(1, 1.0), _comp(2, 1.0), _comp(3, 1.0, cost=0.25), _comp(4, 1.0)]
    prices = [ch.Price(1, D(2026, 9, 7), 1.0, seq=1), ch.Price(2, D(2026, 10, 5), 2.0, seq=2)]
    h = ch.build(comps, prices, today=D(2026, 10, 6))
    # ingredient 2's first price (Oct 5) is used back to Sep 7
    assert h.costs[0] == 1.0 + 2.0 + 0.25
    assert [c.ingredient_id for c in h.unpriced] == [4]


def test_since_trims_and_movers_rank_by_change():
    comps = [_comp(1, 4.0, name='Chicken'), _comp(2, 1.0, name='Kale'), _comp(3, 1.0, name='Farro')]
    prices = [ch.Price(1, D(2026, 9, 1), 0.30, seq=1), ch.Price(1, D(2026, 10, 1), 0.35, seq=2),
              ch.Price(2, D(2026, 9, 1), 0.10, seq=3), ch.Price(2, D(2026, 10, 1), 0.08, seq=4),
              ch.Price(3, D(2026, 9, 1), 0.20, seq=5)]
    h = ch.build(comps, prices, since=D(2026, 9, 10), today=D(2026, 10, 10))
    assert h.weeks[0] == D(2026, 9, 7)
    rows, unchanged = ch.movers(h, 0, len(h) - 1)
    assert [m.name for m in rows] == ['Chicken', 'Kale'] and unchanged == 1
    assert round(rows[0].change, 2) == 0.20
    s = ch.summary(h, 0, len(h) - 1, menu_price=10.0, target=0.28)
    assert round(s.now, 2) == 1.68 and round(s.room, 2) == 1.12


def test_inputs_from_library(lib):
    rid = lib.recipe('Bowl')
    kale = lib.ingredient('Kale', 'oz', 'Greens', cost=0)
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 3);', (rid, kale))
    lib.sql("INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)"
            " VALUES (?, 10, 100, '2026-09-01');", (kale,))
    comps, prices = ch.from_inputs(db.recipe_cost_history_inputs(rid))
    assert comps[0].qty == 3 and comps[0].color
    h = ch.build(comps, prices, today=D(2026, 9, 20))
    assert round(h.costs[-1], 2) == 0.30
