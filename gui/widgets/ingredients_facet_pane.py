'''Left filter pane for the Ingredients place: Category, Needs
attention, Supplier, Allergens — checkboxes with counts, per the
Framework canvas.

Category and Supplier are "include" sections (everything starts
checked; unchecking hides those ingredients); Needs attention and
Allergens are "any" sections (checking shows only ingredients with any
checked item). Supplier and Allergens start collapsed. Sections,
collapsing and All / None come from FacetPane.

Counts are totals over the whole library, so they don't jump as other
filters change. `set_library(rows)` rebuilds the lists from the
model's rows, keeping each checkbox's state by key.
'''
from gui.models.ingredients_model import ATTENTION_KEYS, NO_ALLERGENS
from gui.widgets.facet_pane import MUTED, FacetPane


_ATTENTION_LABELS = {
    'price_up': ('Price up 5%+ (90 days)', '#8a4a00'),
    'no_price': ('No price', '#b80700'),
    'no_nutrition': ('No nutrition', MUTED),
    'no_photo': ('No photo', MUTED),
    'unused': ('Not used in any recipe', MUTED),
}


class IngredientsFacetPane(FacetPane):
    SECTIONS = (
        ('category', 'Category', 'include', True),
        ('attention', 'Needs attention', 'any', True),
        ('supplier', 'Supplier', 'include', False),
        ('allergen', 'Allergens', 'any', False),
    )
    SETTINGS_PREFIX = 'ingredients/facetOpen/'

    def set_library(self, rows):
        cats = {}
        for r in rows:
            key = r.get('TagId')
            entry = cats.setdefault(key, {'name': r.get('TagName') or 'Uncategorized',
                                          'color': r.get('TagColor') or '#a7ad9c',
                                          'sort': r.get('TagSort', 1000), 'n': 0})
            entry['n'] += 1
        self._fill('category', [
            (k, v['name'], v['color'], v['n'], None)
            for k, v in sorted(cats.items(), key=lambda kv: (kv[1]['sort'], kv[1]['name']))
        ])

        counts = {k: sum(1 for r in rows if r['Flags'][k]) for k in ATTENTION_KEYS}
        self._fill('attention', [
            (k, _ATTENTION_LABELS[k][0], None, counts[k], _ATTENTION_LABELS[k][1] if counts[k] else MUTED)
            for k in ATTENTION_KEYS
        ])

        sups = {}
        for r in rows:
            key = r.get('SupplierId')
            entry = sups.setdefault(key, {'name': r.get('SupplierName') or 'No supplier', 'n': 0})
            entry['n'] += 1
        self._fill('supplier', [
            (k, v['name'], None, v['n'], None)
            for k, v in sorted(sups.items(), key=lambda kv: (kv[0] is None, kv[1]['name'].lower()))
        ])

        # Allergens in the canonical order they appear in rows (each
        # row's list is already sorted that way), then "No allergens".
        order, counts = [], {}
        for r in rows:
            for name in r['AllergenList']:
                if name not in counts:
                    order.append(name)
                    counts[name] = 0
                counts[name] += 1
        none_n = sum(1 for r in rows if not r['AllergenList'])
        self._fill('allergen', [(name, name, None, counts[name], None) for name in order]
                   + [(NO_ALLERGENS, 'No allergens', None, none_n, None)])

    def selection(self):
        '''(categories, attention, suppliers, allergens) for
        IngredientsFacetProxy. An include section with everything
        checked returns None (no filter); an any section returns the
        set of checked keys (empty = no filter).'''
        return (self.included('category'), self.checked('attention'),
                self.included('supplier'), self.checked('allergen'))
