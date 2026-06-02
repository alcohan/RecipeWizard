import os
import re
import sqlite3
import config

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')
_token_re = re.compile(r'[a-z0-9]+')
_trailing_id_re = re.compile(r'-\d+$')

def _stem_plural(token):
    '''Strip simple English plural endings so "Carrots" matches "Carrot".'''
    if len(token) > 4 and token.endswith('ies'):
        return token[:-3] + 'y'  # berries -> berry
    if len(token) > 4 and token.endswith('oes'):
        return token[:-2]        # tomatoes -> tomato, potatoes -> potato
    if len(token) > 3 and token.endswith('s') and not token.endswith('ss'):
        return token[:-1]        # carrots -> carrot, peppers -> pepper
    return token

def _normalize_for_match(name):
    '''Normalize a filename or ingredient name into a sorted, stemmed token
    string for matching. Strips extension and a trailing `-NNN` suffix,
    tokenizes on non-alphanumeric, lowercases, applies simple plural stemming,
    drops pure-digit tokens, and sorts the result so word order doesn't matter.'''
    base = os.path.splitext(name)[0]
    base = _trailing_id_re.sub('', base)
    tokens = _token_re.findall(base.lower())
    tokens = [_stem_plural(t) for t in tokens if not t.isdigit()]
    return ' '.join(sorted(tokens))

# def deleteDB():
#     if os.path.exists('builder.db'):
#         os.remove('builder.db')
#         print('builder.db deleted')
#     else:
#         print('builder.db does not exist')

def initializeDB(includeSampleData=True):
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()

    for file in ('sql/setup/tables.sql', 'sql/setup/views.sql'):
        print(f'Executing script {file}')
        sql = config.get_resource(file)
        cursor.executescript(sql)

    connection.commit()
    connection.close()

    if includeSampleData:
        # Prefer a locally generated proprietary sample if present, otherwise
        # fall back to the generic seed shipped in the repo. Lets internal
        # users run `tools/generate_sample_data.py --xlsx ...` once to drop a
        # gitignored sampledata.local.sql in place that this file picks up
        # automatically on first init.
        try:
            sql = config.get_resource('sql/setup/sampledata.local.sql')
            print('Loading sample data: sampledata.local.sql (proprietary override)')
        except (FileNotFoundError, OSError):
            sql = config.get_resource('sql/setup/sampledata.sql')
            print('Loading sample data: sampledata.sql (generic)')
        connection = sqlite3.connect(config.DATABASE)
        cursor = connection.cursor()
        cursor.executescript(sql)
        connection.commit()
        connection.close()

    # Run after sample data so any tags the sample inserts (with their own
    # numeric ids) are present first; migrateDB's tag seed is idempotent and
    # only fills in canonical tags that aren't already there by (name, kind).
    migrateDB()

    # Fill in ImageFilename for any ingredient that didn't ship with one —
    # matches by normalized name against files in INGREDIENTS_PATH. Skips
    # rows that already have an image, so it's safe even when the sample
    # data populated images itself.
    auto_assign_images()

    print('Database initialized')

def auto_assign_images():
    '''Match files in INGREDIENTS_PATH to ingredients by normalized name.
    Only fills rows where ImageFilename is NULL or empty. A normalized name
    must map to exactly one file to be assigned (ambiguous matches skipped).
    Returns {'assigned': N, 'ambiguous': N, 'unmatched': N}.'''
    counts = {'assigned': 0, 'ambiguous': 0, 'unmatched': 0}
    if not os.path.isdir(config.INGREDIENTS_PATH):
        return counts

    file_index = {}
    for fname in os.listdir(config.INGREDIENTS_PATH):
        if os.path.splitext(fname)[1].lower() not in IMAGE_EXTENSIONS:
            continue
        file_index.setdefault(_normalize_for_match(fname), []).append(fname)

    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()
    cursor.execute("SELECT Id, Name FROM Ingredients WHERE ImageFilename IS NULL OR ImageFilename = ''")
    for ingredient_id, name in cursor.fetchall():
        matches = file_index.get(_normalize_for_match(name), [])
        if len(matches) == 1:
            cursor.execute('UPDATE Ingredients SET ImageFilename=? WHERE Id=?', (matches[0], ingredient_id))
            counts['assigned'] += 1
        elif len(matches) > 1:
            counts['ambiguous'] += 1
        else:
            counts['unmatched'] += 1

    connection.commit()
    connection.close()
    return counts

def migrateDB():
    '''Idempotently bring an existing database up to the current schema.'''
    connection = sqlite3.connect(config.DATABASE)
    cursor = connection.cursor()

    def column_exists(table, column):
        cursor.execute(f"PRAGMA table_info({table})")
        return any(row[1] == column for row in cursor.fetchall())

    if not column_exists('Ingredients', 'ImageFilename'):
        print('Migrating: adding Ingredients.ImageFilename')
        cursor.execute('ALTER TABLE Ingredients ADD COLUMN ImageFilename TEXT')

    if not column_exists('Connections', 'SortOrder'):
        print('Migrating: adding Connections.SortOrder')
        cursor.execute('ALTER TABLE Connections ADD COLUMN SortOrder INTEGER')
        # Backfill from rowid order per parent — gives each existing row a
        # stable, distinct SortOrder reflecting the order it was inserted.
        cursor.execute('''
            UPDATE Connections
            SET SortOrder = (
                SELECT COUNT(*)
                FROM Connections c2
                WHERE c2.ParentRecipe = Connections.ParentRecipe
                  AND c2.rowid <= Connections.rowid
            )
        ''')

    if not column_exists('tags', 'kind'):
        print("Migrating: adding tags.kind (existing tags default to 'ingredient')")
        cursor.execute("ALTER TABLE tags ADD COLUMN kind TEXT NOT NULL DEFAULT 'ingredient'")

    if not column_exists('tags', 'color'):
        print('Migrating: adding tags.color')
        cursor.execute('ALTER TABLE tags ADD COLUMN color TEXT')

    if not column_exists('tags', 'shape'):
        print('Migrating: adding tags.shape')
        cursor.execute("ALTER TABLE tags ADD COLUMN shape TEXT NOT NULL DEFAULT 'none'")
        # Backfill canonical recipe-kind tags by name so existing user DBs
        # show the right silhouette right after upgrade (the user can change
        # them later in the Tags Manager).
        for tag_name, shape in _CANONICAL_RECIPE_SHAPES.items():
            cursor.execute(
                "UPDATE tags SET shape=? WHERE name=? AND kind='recipe';",
                (shape, tag_name),
            )

    if not column_exists('Connections', 'from_template_tag_id'):
        print('Migrating: adding Connections.from_template_tag_id')
        cursor.execute('ALTER TABLE Connections ADD COLUMN from_template_tag_id INTEGER')

    def table_exists(table):
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        return cursor.fetchone() is not None

    if not table_exists('tag_components'):
        print('Migrating: creating tag_components')
        cursor.execute('''
            CREATE TABLE tag_components (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tag_id INTEGER NOT NULL,
              child_recipe INTEGER,
              child_ingredient INTEGER,
              quantity FLOAT NOT NULL DEFAULT 1,
              FOREIGN KEY (tag_id) REFERENCES tags(id)
            )
        ''')

    if not table_exists('tag_category_multipliers'):
        print('Migrating: creating tag_category_multipliers')
        cursor.execute('''
            CREATE TABLE tag_category_multipliers (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              tag_id INTEGER NOT NULL,
              category_tag_id INTEGER NOT NULL,
              multiplier FLOAT NOT NULL DEFAULT 1,
              UNIQUE (tag_id, category_tag_id),
              FOREIGN KEY (tag_id) REFERENCES tags(id),
              FOREIGN KEY (category_tag_id) REFERENCES tags(id)
            )
        ''')

    # Seed the canonical tag set if the user's DB doesn't have it yet. Only
    # inserts a missing tag by (name, kind) — won't clobber any user-created
    # tags or rename ones they've kept.
    for name, kind, color, shape in _DEFAULT_TAGS:
        cursor.execute(
            "SELECT id FROM tags WHERE name=? AND kind=?", (name, kind),
        )
        if cursor.fetchone() is None:
            cursor.execute(
                'INSERT INTO tags (name, kind, color, shape) VALUES (?, ?, ?, ?);',
                (name, kind, color, shape),
            )

    # Backfill missing colors so badges always have a color to paint with.
    cursor.execute("UPDATE tags SET color = ? WHERE color IS NULL OR color = ''", ('#64748b',))

    # updated_at on Ingredients and Recipes powers the home tab's
    # "recently edited" strip. SQLite's ALTER TABLE ADD COLUMN forbids
    # a non-constant default expression, so the migrated column is
    # nullable with no default; existing rows get backfilled, and
    # future INSERTs go through create_ingredient.sql/create_recipe.sql
    # which set datetime('now') explicitly.
    if not column_exists('Ingredients', 'updated_at'):
        print('Migrating: adding Ingredients.updated_at')
        cursor.execute('ALTER TABLE Ingredients ADD COLUMN updated_at TEXT')
        cursor.execute("UPDATE Ingredients SET updated_at = datetime('now') WHERE updated_at IS NULL")
    if not column_exists('Recipes', 'updated_at'):
        print('Migrating: adding Recipes.updated_at')
        cursor.execute('ALTER TABLE Recipes ADD COLUMN updated_at TEXT')
        cursor.execute("UPDATE Recipes SET updated_at = datetime('now') WHERE updated_at IS NULL")

    # Trigger set is rebuilt on every migration so changes to the bump
    # logic propagate without bespoke migration steps. The WHEN guard on
    # the row-self-update triggers prevents infinite recursion.
    cursor.executescript('''
        DROP TRIGGER IF EXISTS ingredients_bump_updated_at;
        CREATE TRIGGER ingredients_bump_updated_at AFTER UPDATE ON Ingredients
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE Ingredients SET updated_at = datetime('now') WHERE Id = NEW.Id;
        END;

        DROP TRIGGER IF EXISTS recipes_bump_updated_at;
        CREATE TRIGGER recipes_bump_updated_at AFTER UPDATE ON Recipes
        WHEN NEW.updated_at = OLD.updated_at
        BEGIN
          UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.Id;
        END;

        DROP TRIGGER IF EXISTS connections_bump_recipe_after_insert;
        CREATE TRIGGER connections_bump_recipe_after_insert AFTER INSERT ON Connections
        BEGIN
          UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.ParentRecipe;
        END;

        DROP TRIGGER IF EXISTS connections_bump_recipe_after_update;
        CREATE TRIGGER connections_bump_recipe_after_update AFTER UPDATE ON Connections
        BEGIN
          UPDATE Recipes SET updated_at = datetime('now') WHERE Id = NEW.ParentRecipe;
        END;

        DROP TRIGGER IF EXISTS connections_bump_recipe_after_delete;
        CREATE TRIGGER connections_bump_recipe_after_delete AFTER DELETE ON Connections
        BEGIN
          UPDATE Recipes SET updated_at = datetime('now') WHERE Id = OLD.ParentRecipe;
        END;
    ''')

    # Repair fallout from the recipes-in-templates bug: an earlier version
    # of the templates editor let the user pick a sub-recipe in the
    # "+ Add Item" dialog. Adding a recipe that was itself tagged with the
    # template produced a self-referential Connections row when the
    # template was reconciled, and the recursive CTE in
    # RecipesWithNutrition hangs forever on that cycle. Two-step repair:
    cursor.execute(
        'SELECT COUNT(*) FROM tag_components WHERE child_recipe IS NOT NULL;'
    )
    bad_components = cursor.fetchone()[0]
    if bad_components:
        print(f'Migrating: removing {bad_components} recipe-typed tag_components row(s)')
        cursor.execute('DELETE FROM tag_components WHERE child_recipe IS NOT NULL;')
    cursor.execute(
        'SELECT COUNT(*) FROM Connections WHERE ParentRecipe = ChildRecipe;'
    )
    self_refs = cursor.fetchone()[0]
    if self_refs:
        print(f'Migrating: removing {self_refs} self-referential Connections row(s)')
        cursor.execute('DELETE FROM Connections WHERE ParentRecipe = ChildRecipe;')

    connection.commit()
    connection.close()


# Default silhouette shape for each canonical recipe-kind tag. Used both by
# the column-add migration backfill and the seed below; keeps the two in sync.
_CANONICAL_RECIPE_SHAPES = {
    'Salad': 'ring',
    'Wrap': 'wrap',
    'Bowl': 'bowl',
    'Catering': 'tray',
}

# Canonical seed tags. Recipe formats drive the homepage silhouette; ingredient
# categories drive the colored badges. The migration inserts any of these that
# are absent from the user's DB by (name, kind), so the set is always present
# without overwriting user customizations.
#
# Note: legacy tags (Base, Veggies) are NOT auto-removed for users upgrading.
# Migration is additive — old tags stay around with whatever mappings the user
# had, and they can be manually deleted in the Tags Manager when ready.
_DEFAULT_TAGS = (
    ('Salad', 'recipe', '#16a34a', 'ring'),
    ('Wrap', 'recipe', '#b45309', 'wrap'),
    ('Bowl', 'recipe', '#ea580c', 'bowl'),
    ('Catering', 'recipe', '#7c3aed', 'tray'),
    ('Greens', 'ingredient', '#15803d', 'none'),
    ('Grains', 'ingredient', '#92400e', 'none'),
    ('Toppings', 'ingredient', '#dc2626', 'none'),
    ('Cheese', 'ingredient', '#eab308', 'none'),
    ('Crunchies', 'ingredient', '#a16207', 'none'),
    ('Premiums', 'ingredient', '#9333ea', 'none'),
    ('Protein', 'ingredient', '#be185d', 'none'),
    ('Dressing', 'ingredient', '#0891b2', 'none'),
    ('Finish', 'ingredient', '#db2777', 'none'),
    ('Packaging', 'ingredient', '#475569', 'none'),
)

if __name__=="__main__":
    initializeDB()