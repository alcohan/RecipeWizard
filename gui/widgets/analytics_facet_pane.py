'''Analytics' left pane: the compare tray on top, then Format and Tags
checkboxes like the Library's filter pane, then saved comparisons.

- Format ("include"): one row per recipe format plus Sub-recipes, which
  starts unchecked, as in the Library.
- Tags ("any"): checking shows recipes with any checked tag (Untagged
  for none).

Counts are over what the views start from: the tray's recipes, or every
active recipe when it's empty. state() is JSON-ready and is what saved
comparisons keep; matches() (the Library's) applies it.
'''
from gui.models.recipes_model import SUB_RECIPES
from gui.widgets.facet_pane import FacetPane
from gui.widgets.recipes_facet_pane import _keys

import db


class AnalyticsFacetPane(FacetPane):
    SECTIONS = (
        ('format', 'Format', 'include', True),
        ('tag', 'Tags', 'any', True),
    )
    SETTINGS_PREFIX = 'analytics/facetOpen/'
    WIDTH = 252

    def __init__(self, parent=None):
        super().__init__(parent)
        self._top = 0
        self._rows = []

    def _default_checked(self, group, key):
        if group == 'format':
            return key != SUB_RECIPES
        return super()._default_checked(group, key)

    # --- layout ----------------------------------------------------------

    def add_top(self, widget):
        '''Above the filter sections (the compare tray).'''
        self._layout.insertWidget(self._top, widget)
        self._top += 1

    def add_bottom(self, widget):
        '''Below them (saved comparisons), above the closing stretch.'''
        self._layout.insertWidget(self._layout.count() - 1, widget)

    # --- filling -------------------------------------------------------

    def set_rows(self, rows):
        '''The Library rows the counts are over.'''
        self._rows = list(rows)
        fmt_counts = {}
        for r in self._rows:
            key = r.get('TagName') or SUB_RECIPES
            fmt_counts[key] = fmt_counts.get(key, 0) + 1
        formats = [(t['name'], t.get('color')) for t in db.get_tags('recipe')]
        names = [n for n, _c in formats]
        extra = sorted(k for k in fmt_counts if k not in names and k != SUB_RECIPES)
        self._fill('format', [(n, n, c, fmt_counts.get(n, 0), None) for n, c in formats]
                   + [(n, n, None, fmt_counts[n], None) for n in extra]
                   + [(SUB_RECIPES, 'Sub-recipes', None, fmt_counts.get(SUB_RECIPES, 0), None,
                       'Recipes with no format, like dressings and sauces')])
        tags = db.get_tags('recipe_tag')
        self._fill('tag', [(t['id'], t['name'], t.get('color'),
                            sum(1 for r in self._rows if t['id'] in (r.get('TagIds') or ())), None) for t in tags]
                   + [(None, 'Untagged', None, sum(1 for r in self._rows if not r.get('TagIds')), None)])
        self.section('tag').setVisible(bool(tags))

    # --- state -----------------------------------------------------------

    def state(self):
        '''{'formats': [names] or None (all), 'tags': [ids]}, for matches().'''
        return {'formats': _keys(self.included('format')), 'tags': _keys(self.checked('tag'))}

    def is_default(self):
        return not any(self._filtering(g) for g in self._groups)

    def apply_state(self, state):
        '''Check the boxes a state() asks for (also ones not built yet),
        then emit changed once.'''
        state = state or {}
        formats = state.get('formats')
        tags = set(state.get('tags') or ())
        format_keys = {t['name'] for t in db.get_tags('recipe')} | {SUB_RECIPES} | set(formats or ())
        format_keys |= set(self._groups['format']['boxes'])
        for k in format_keys:
            on = self._default_checked('format', k) if formats is None and 'formats' not in state \
                else (formats is None or k in formats)
            self._state[('format', k)] = on
        tag_keys = {t['id'] for t in db.get_tags('recipe_tag')} | {None} | tags | set(self._groups['tag']['boxes'])
        for k in tag_keys:
            self._state[('tag', k)] = k in tags
        for group in self._groups:
            for k, cb in self._groups[group]['boxes'].items():
                cb.blockSignals(True)
                cb.setChecked(self._state.get((group, k), self._default_checked(group, k)))
                cb.blockSignals(False)
            self._sync_section(group)
        self.changed.emit()
