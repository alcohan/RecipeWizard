from utilities import compare


def _detail(rid, name, category, cost, **nutrients):
    row = {'recipe_id': rid, 'ingredient_name': name, 'category': category, 'cost': cost}
    row.update(nutrients)
    return row


RECIPES = [
    {'Id': 1, 'Name': 'Cobb', 'TagName': 'Salad', 'MenuPrice': 10.0, 'Allergens': ['Egg', 'Milk'],
     'FacilityAllergens': ['Peanuts']},
    {'Id': 2, 'Name': 'Ranch', 'TagName': None, 'MenuPrice': None, 'Allergens': [], 'FacilityAllergens': []},
    {'Id': 3, 'Name': 'Wrap', 'TagName': 'Wrap', 'MenuPrice': '8', 'Archived': True},
]
DETAILS = [
    _detail(1, 'Romaine', 'Greens', 0.5, calories=10, sat_fat=0, sugar=1),
    _detail(1, 'Spinach', 'Greens', 0.25, calories=5),
    _detail(1, 'Bacon', 'Protein', 1.25, calories=200, sat_fat=4, sugar=0),
    _detail(1, 'Romaine', 'Greens', 0.5, calories=10),   # a second appearance via a sub-recipe
    _detail(2, 'Buttermilk', 'Dairy', 0.4, calories=60, sugar=3),
    _detail(3, 'Tortilla', 'Bread', 0.6, calories=150),
]
CATS = ['Greens', 'Protein', 'Bread', 'Dairy', compare.UNCATEGORIZED]


def _build(ids=(1, 2, 3)):
    return compare.build(DETAILS, RECIPES, list(ids), CATS)


def test_build_rolls_up_cost_by_category_and_food_cost():
    data = _build()
    cobb, ranch, wrap = data['recipes']
    assert data['categories'] == ['Greens', 'Protein', 'Bread', 'Dairy']
    assert cobb['categories'] == {'Greens': 1.25, 'Protein': 1.25}
    assert cobb['cost'] == 2.5
    assert cobb['pct'] == 25.0
    assert ranch['pct'] is None and ranch['menu_price'] is None
    assert wrap['menu_price'] == 8.0 and wrap['archived']


def test_ingredients_are_distinct_and_in_category_order():
    cobb = _build()['recipes'][0]
    assert cobb['ingredients'] == ['Romaine', 'Spinach', 'Bacon']
    assert cobb['items'] == {'Greens': ['Romaine', 'Spinach'], 'Protein': ['Bacon']}


def test_sat_fat_and_sugar_are_summed():
    cobb = _build()['recipes'][0]
    assert cobb['totals']['sat_fat'] == 4
    assert cobb['totals']['sugar'] == 1
    assert cobb['totals']['calories'] == 225


def test_allergens_keep_contains_and_facility_apart():
    cobb = _build()['recipes'][0]
    assert cobb['allergens'] == ['Egg', 'Milk']
    assert cobb['facility'] == ['Peanuts']


def test_unknown_ids_dropped_and_order_kept():
    data = _build((3, 99, 1))
    assert [r['id'] for r in data['recipes']] == [3, 1]


def test_averages_count_missing_category_as_zero_and_price_only_when_priced():
    avg = compare.averages(_build((1, 2)))
    assert avg['categories']['Greens'] == 0.625
    assert avg['pct'] == 25.0
    assert avg['menu_price'] == 10.0
    assert avg['cost'] == (2.5 + 0.4) / 2


def test_averages_empty():
    avg = compare.averages(_build(()))
    assert avg['cost'] is None and avg['calories'] is None


def test_pricing_csv():
    rows = compare.pricing_csv(_build((1, 2)))
    assert rows[0] == ['Recipe', 'Template', 'Ingredients', 'Ingredient list', 'Greens', 'Protein', 'Dairy',
                       'Food cost', 'Menu price', 'Food cost %']
    assert rows[1] == ['Cobb', 'Salad', 3, 'Romaine; Spinach; Bacon', 1.25, 1.25, '', 2.5, 10.0, 25.0]
    assert rows[2][:4] == ['Ranch', '', 1, 'Buttermilk']
    assert rows[2][-2:] == ['', '']
    assert rows[-1][0] == 'Average'


def test_nutrition_csv():
    rows = compare.nutrition_csv(_build((1,)))
    assert rows[0][:4] == ['Recipe', 'Template', 'Weight (g)', 'Calories']
    assert rows[0][-2:] == ['Contains', 'Facility']
    assert 'Sat fat (g)' in rows[0] and 'Sugar (g)' in rows[0]
    assert rows[1][-2:] == ['Egg, Milk', 'Peanuts']
    assert rows[-1][0] == 'Average'
