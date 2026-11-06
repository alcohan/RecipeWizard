import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
# config reads these at import; keep the tests off the real library.
_TMP = tempfile.mkdtemp(prefix='rw-tests-')
os.environ.setdefault('RECIPEWIZARD_DB', os.path.join(_TMP, 'unused.db'))
os.environ.setdefault('RECIPEWIZARD_INGREDIENTS', os.path.join(_TMP, 'ingredients'))
os.environ.setdefault('RECIPEWIZARD_RECIPE_IMAGES', os.path.join(_TMP, 'recipes'))

import config  # noqa: E402
import setup  # noqa: E402


class Library:
    '''A fresh, migrated library (canonical tags and default portion
    rules seeded) with helpers for building recipes.'''

    def __init__(self, path):
        self.path = path

    def sql(self, statement, params=()):
        con = sqlite3.connect(self.path)
        try:
            cur = con.execute(statement, params)
            rows = cur.fetchall()
            con.commit()
            return rows, cur.lastrowid
        finally:
            con.close()

    def tag(self, name, kind):
        return self.sql('SELECT id FROM tags WHERE name = ? AND kind = ?;', (name, kind))[0][0][0]

    def ingredient(self, name, unit, category=None, cost=1.0):
        _rows, ing_id = self.sql('INSERT INTO Ingredients (Name, Unit, Weight, Cost) VALUES (?, ?, 100, ?);',
                                 (name, unit, cost))
        if category:
            self.sql('INSERT INTO ingredient_tags_mapping (tag_id, ingredient_id) VALUES (?, ?);',
                     (self.tag(category, 'ingredient'), ing_id))
        return ing_id

    def recipe(self, name, fmt=None):
        _rows, rid = self.sql("INSERT INTO Recipes (Name, Unit, OutputQty) VALUES (?, 'ea', 1);", (name,))
        if fmt:
            self.sql('INSERT INTO recipe_tags_mapping (tag_id, recipe_id) VALUES (?, ?);',
                     (self.tag(fmt, 'recipe'), rid))
        return rid

    def rows(self, recipe_id):
        '''{ingredient name: (quantity, share, from_template)}'''
        rows, _ = self.sql('''SELECT i.Name, c.Quantity, c.portion_share, c.from_template_tag_id
                              FROM Connections c JOIN Ingredients i ON i.Id = c.ChildIngredient
                              WHERE c.ParentRecipe = ?;''', (recipe_id,))
        return {name: (qty, share, tpl) for name, qty, share, tpl in rows}

    def qty(self, recipe_id):
        return {name: round(q, 4) for name, (q, _s, _t) in self.rows(recipe_id).items()}


@pytest.fixture
def lib(tmp_path, monkeypatch):
    path = str(tmp_path / 'builder.db')
    con = sqlite3.connect(path)
    for f in ('sql/setup/tables.sql', 'sql/setup/views.sql'):
        con.executescript(open(os.path.join(ROOT, f), encoding='utf-8').read())
    con.commit()
    con.close()
    monkeypatch.setattr(config, 'DATABASE', path)
    setup.migrateDB(path)
    return Library(path)
