'''Diets a recipe fits, worked out from its allergens and nutrition.

Built-in rules for now (the Framework canvas's "Edit diet rules" comes
with the data-model slice): an allergen diet excludes recipes that
contain any of its allergens; a nutrient diet needs at least so much
per serving. A serving is one unit of the recipe's yield.

No Qt here — the Library filter pane, cards and inspector all read
`diets_for` / `diet_blockers`.
'''

# key, name, tooltip, excluded allergens, (nutrient key, minimum per serving)
DIETS = (
    ('vegan', 'Vegan', 'No meat, fish, shellfish, dairy or eggs',
     ('Meat', 'Fish', 'Shellfish', 'Dairy', 'Eggs'), None),
    ('vegetarian', 'Vegetarian', 'No meat, fish or shellfish',
     ('Meat', 'Fish', 'Shellfish'), None),
    ('dairy_free', 'Dairy-free', 'No dairy', ('Dairy',), None),
    ('gluten_free', 'Gluten-free', 'No gluten', ('Gluten',), None),
    ('high_protein', 'High protein', '30 g protein or more per serving', (), ('Protein', 30.0)),
    ('high_fiber', 'High fiber', '8 g fiber or more per serving', (), ('Fiber', 8.0)),
)

DIET_NAMES = {key: name for key, name, *_ in DIETS}
DIET_TIPS = {key: tip for key, _name, tip, *_ in DIETS}

_UNITS = {'Protein': 'g protein', 'Fiber': 'g fiber'}


def diets_for(allergens, per_serving):
    '''Keys of the diets a recipe fits, in DIETS order. `allergens` is
    an iterable of allergen names in the recipe's tree; `per_serving`
    maps 'Protein' / 'Fiber' to grams per serving (missing = 0).'''
    have = set(allergens or ())
    out = []
    for key, _name, _tip, excluded, nutrient in DIETS:
        if excluded and have.intersection(excluded):
            continue
        if nutrient is not None:
            field, minimum = nutrient
            if float(per_serving.get(field) or 0) < minimum:
                continue
        out.append(key)
    return out


def diet_blockers(allergen_sources, per_serving, only=None):
    '''Why a recipe misses each diet it doesn't fit, for the inspector:
    [(diet name, reason)], e.g. ('Vegetarian', 'chicken (Meat)').
    `allergen_sources` is [(allergen, [component names])] as from
    db.get_recipe_allergen_sources. `only` limits to those diet keys.'''
    sources = dict(allergen_sources or ())
    out = []
    for key, name, _tip, excluded, nutrient in DIETS:
        if only is not None and key not in only:
            continue
        if excluded:
            hits = [(a, sources[a]) for a in excluded if a in sources]
            if hits:
                out.append((name, '; '.join(f'{", ".join(src)} ({a})' for a, src in hits)))
                continue
        if nutrient is not None:
            field, minimum = nutrient
            have = float(per_serving.get(field) or 0)
            if have < minimum:
                out.append((name, f'{have:.0f} {_UNITS[field]} per serving, needs {minimum:.0f}'))
    return out
