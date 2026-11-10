'''Ingredients portioned by weight keep nutrition and prices per gram, so
a portion change rescales them, price history included.'''
import pytest

import db
import setup
from utilities.portions import portioned_by_weight


def _chicken(lib):
    iid = lib.ingredient('Chicken', '3 f.oz', 'Protein')
    lib.sql("UPDATE Ingredients SET Weight = 60, Calories = 90, ProteinGrams = 15, basis = 'g' WHERE Id = ?;", (iid,))
    for day, case in (('2026-01-05', 120.0), ('2026-03-02', 150.0)):
        lib.sql('INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)'
                ' VALUES (?, ?, 100, ?);', (iid, case, day))
    rid = lib.recipe('Chicken Bowl')
    lib.sql('INSERT INTO Connections (ParentRecipe, ChildIngredient, Quantity) VALUES (?, ?, 1);', (rid, iid))
    return iid, rid


def _ing(lib, iid):
    (row,), _ = lib.sql('SELECT Weight, Calories, ProteinGrams, Cost, Calories_g FROM Ingredients WHERE Id = ?;',
                        (iid,))
    return row


def _prices(lib, iid):
    rows, _ = lib.sql('SELECT units_per_case, unit_price, grams_per_case FROM ingredient_prices'
                      ' WHERE ingredient_id = ? ORDER BY effective_date;', (iid,))
    return rows


@pytest.mark.parametrize('unit, weight, expected', [
    ('3 f.oz', 85, True), ('1 cup', 30, True), ('1 w.oz', 28, True),
    ('1 ea', 43, False), ('.5 ea', 61, False), ('1/6th wedge', 14, False), ('', 5, False), ('1', 1, False),
    ('3 f.oz', None, False), ('3 f.oz', 0, False),
])
def test_basis_rule(unit, weight, expected):
    assert portioned_by_weight(unit, weight) is expected


def test_per_gram_values_follow_entries(lib):
    iid, _ = _chicken(lib)
    assert _ing(lib, iid)[4] == pytest.approx(1.5)
    assert [p[2] for p in _prices(lib, iid)] == [pytest.approx(6000), pytest.approx(6000)]


def test_portion_change_rescales_nutrition_and_history(lib):
    iid, rid = _chicken(lib)
    assert db.rescale_portion(iid, 80)
    weight, cal, protein, cost, _ = _ing(lib, iid)
    assert (weight, cal, protein) == (80, pytest.approx(120), pytest.approx(20))
    # Every price, not just the latest: 6000 g a case is 75 portions of 80 g.
    assert [(p[0], p[1]) for p in _prices(lib, iid)] == [(pytest.approx(75), pytest.approx(1.6)),
                                                         (pytest.approx(75), pytest.approx(2.0))]
    assert cost == pytest.approx(2.0)
    (total,), _ = lib.sql('SELECT Cost, Calories FROM RecipeTotalValues WHERE Id = ?;', (rid,))
    assert total == (pytest.approx(2.0), pytest.approx(120))


def test_typo_fix_keeps_per_portion_numbers(lib):
    iid, _ = _chicken(lib)
    lib.sql('UPDATE Ingredients SET Weight = 85 WHERE Id = ?;', (iid,))
    weight, cal, _p, _c, cal_g = _ing(lib, iid)
    assert (weight, cal, cal_g) == (85, 90, pytest.approx(90 / 85))
    assert [(p[0], p[2]) for p in _prices(lib, iid)] == [(100, pytest.approx(8500))] * 2
    # A portion change after the fix scales from the corrected weight.
    db.rescale_portion(iid, 170)
    assert _ing(lib, iid)[1] == pytest.approx(180)


def test_round_trip_restores_everything(lib):
    iid, _ = _chicken(lib)
    before = (_ing(lib, iid), _prices(lib, iid))
    db.rescale_portion(iid, 77.3)
    db.rescale_portion(iid, 60)
    after = (_ing(lib, iid), _prices(lib, iid))
    assert after[0][:4] == pytest.approx(before[0][:4])
    assert [tuple(p) for p in after[1]] == [pytest.approx(tuple(p)) for p in before[1]]


def test_each_items_do_not_rescale(lib):
    egg = lib.ingredient('Egg', '1 ea', 'Protein')
    lib.sql("UPDATE Ingredients SET Weight = 43, Calories = 70, basis = 'each' WHERE Id = ?;", (egg,))
    assert db.rescale_portion(egg, 50) is False
    assert _ing(lib, egg)[:2] == (43, 70)
    assert _ing(lib, egg)[4] is None


def test_vendor_items_bought_by_the_each_scale_in_grams(lib):
    iid, _ = _chicken(lib)
    lib.sql("INSERT INTO vendor_items (vendor_key, ingredient_id, case_qty, case_unit, portions_per_each)"
            " VALUES ('k', ?, 10, 'ea', 4);", (iid,))
    db.rescale_portion(iid, 120)
    (row,), _ = lib.sql('SELECT portions_per_each, grams_per_each FROM vendor_items;')
    assert row == (pytest.approx(2), pytest.approx(240))


def test_migration_fills_basis_without_marking_edits(lib):
    iid = lib.ingredient('Rice', '8 f.oz', 'Grains')
    lib.sql('UPDATE Ingredients SET Calories = 200, basis = NULL WHERE Id = ?;', (iid,))
    lib.sql("UPDATE Ingredients SET updated_at = '2026-01-01 00:00:00' WHERE Id = ?;", (iid,))
    setup.migrateDB(lib.path)
    (row,), _ = lib.sql('SELECT basis, Calories_g, updated_at FROM Ingredients WHERE Id = ?;', (iid,))
    assert row == ('g', pytest.approx(2.0), '2026-01-01 00:00:00')


def test_each_portion_scales_by_ratio(lib):
    avo = lib.ingredient('Avocado', '.5 ea', 'Premiums')
    lib.sql("UPDATE Ingredients SET Weight = 61, Calories = 100, basis = 'each' WHERE Id = ?;", (avo,))
    lib.sql('INSERT INTO ingredient_prices (ingredient_id, case_price, units_per_case, effective_date)'
            " VALUES (?, 48, 96, '2026-01-05');", (avo,))
    lib.sql("INSERT INTO vendor_items (vendor_key, ingredient_id, case_qty, case_unit, portions_per_each)"
            " VALUES ('a', ?, 48, 'ea', 2);", (avo,))
    assert db.scale_portion(avo, 2)   # .5 ea -> 1 ea
    weight, cal, _p, cost, cal_g = _ing(lib, avo)
    assert (weight, cal, cost, cal_g) == (122, 200, pytest.approx(1.0), None)
    assert _prices(lib, avo)[0][:2] == (48, pytest.approx(1.0))
    (row,), _ = lib.sql('SELECT portions_per_each FROM vendor_items;')
    assert row == (1,)


def test_scale_portion_by_weight_matches_rescale(lib):
    iid, _ = _chicken(lib)
    assert db.scale_portion(iid, 4 / 3)
    assert _ing(lib, iid)[:2] == (pytest.approx(80), pytest.approx(120))


def test_merge_brings_old_prices_in_at_this_portion_size(lib, tmp_path):
    from utilities import backup
    iid, _ = _chicken(lib)   # 60 g, 2 prices of 6000 g a case
    path = str(tmp_path / 'b.rwbackup')
    backup.create_backup(path, db_path=lib.path, images_dir=str(tmp_path))
    db.rescale_portion(iid, 80)
    lib.sql("DELETE FROM ingredient_prices WHERE effective_date = '2026-01-05';")
    backup.restore_merge(path, db_path=lib.path, images_dir=str(tmp_path),
                         branding_dir=str(tmp_path / 'brand'), safety=False)
    # The missing price comes back as 75 portions of 80 g; the other
    # isn't duplicated.
    assert [(p[0], p[2]) for p in _prices(lib, iid)] == [(pytest.approx(75), pytest.approx(6000))] * 2
