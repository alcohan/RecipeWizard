import pytest

from utilities import portions
from utilities.portions import Rule, parse_unit, rule_quantities, shares_from_quantities


@pytest.mark.parametrize('text, floz', [
    ('3 cups', 24.0), ('8 f.oz', 8.0), (' 1 f.oz', 1.0), ('1/2 f.oz', 0.5), ('1 1/2 cups', 12.0),
    ('2 Tbsp', 1.0), ('1/4 tsp', 1 / 24), ('8 fl oz', 8.0), ('4 oz', 4.0),
])
def test_volume_units(text, floz):
    unit = parse_unit(text)
    assert unit.is_volume
    assert unit.floz == pytest.approx(floz)


@pytest.mark.parametrize('text', ['1 ea', '.5 ea', '1 w.oz', '1/40th loaf', '1/6th wedge', '1'])
def test_non_volume_units(text):
    unit = parse_unit(text)
    assert unit is not None and not unit.is_volume


@pytest.mark.parametrize('text', [None, '', 'each', '0 cups'])
def test_units_without_an_amount(text):
    assert parse_unit(text) is None


def test_base_splits_by_share():
    out = rule_quantities(Rule('base', 3, 'cup'), [('romaine', '3 cups', 2), ('kale', '3 cups', 1)])
    assert out['romaine'] == pytest.approx(2 / 3)   # 2 cups of a 3-cup unit
    assert out['kale'] == pytest.approx(1 / 3)


def test_base_converts_to_each_ingredients_unit():
    out = rule_quantities(Rule('base', 8, 'f.oz'), [('rice', '8 f.oz', 1), ('farro', '4 f.oz', 1)])
    assert out == {'rice': pytest.approx(0.5), 'farro': pytest.approx(1.0)}


def test_fixed_gives_every_row_the_amount():
    out = rule_quantities(Rule('fixed', 0.5, 'cup'), [('romaine', '3 cups', 1), ('kale', '3 cups', 1)])
    assert out == {'romaine': pytest.approx(1 / 6), 'kale': pytest.approx(1 / 6)}


def test_unsizable_rows_are_left_out_of_the_split():
    out = rule_quantities(Rule('base', 4, 'f.oz'), [('rice', '8 f.oz', 1), ('wrap', '1 ea', 1)])
    assert out == {'rice': pytest.approx(0.5), 'wrap': None}


def test_shares_reproduce_the_current_split_by_volume():
    shares = shares_from_quantities([('a', '3 cups', 0.25), ('b', '8 f.oz', 0.75), ('c', '1 ea', 1)])
    assert shares == {'a': pytest.approx(0.5), 'b': pytest.approx(0.5)}


def test_matches_uses_a_relative_tolerance():
    assert portions.matches(0.333, 1 / 3)
    assert not portions.matches(0.15, 1 / 6)
