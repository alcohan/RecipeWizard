'''Library backups: one .rwbackup file holding the database and,
optionally, the ingredient photos; restoring one by overwriting the
library or merging it in.

A .rwbackup is a zip:

    manifest.json              what's inside (see _manifest)
    builder.db                 a consistent snapshot (SQLite backup API)
    images/ingredients/<file>  ingredient photos, when included

Plain .db backups from earlier versions open too: they're a database
with no images.

    create_backup(dest, include_images)    -> manifest
    read_backup(path)                      -> BackupInfo
    restore_overwrite(path)                -> {'safety': path, 'images': n, ...}
    restore_merge(path)                    -> MergeReport

Restores run setup.migrateDB() so older backups come up to date, and
both keep a safety backup of the current library first. Merge rule:
the current library wins. Anything in the backup whose name (natural
key) is already here is left as it is and listed as kept; everything
else is added, with its ids remapped. Two things add up instead of
clashing: price history (entries an ingredient doesn't have yet), and
a format or diet here that has no rules of its own (as seeded into a
new library) takes the backup's. Photos are copied only where no file
of that name exists. No Qt here; `progress(done, total, text)`
callbacks let a dialog show progress.
'''
import collections
import datetime
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile

import config
import setup

EXTENSION = '.rwbackup'
FORMAT = 'RecipeWizard library backup'
FORMAT_VERSION = 1
_DB_MEMBER = 'builder.db'
_MANIFEST_MEMBER = 'manifest.json'
_IMAGES_PREFIX = 'images/ingredients/'

# Counted into the manifest and shown before a restore.
_COUNTS = (
    ('ingredients', 'Ingredients'),
    ('recipes', 'Recipes'),
    ('suppliers', 'suppliers'),
    ('prices', 'ingredient_prices'),
)


class BackupError(Exception):
    '''A file that isn't a usable backup, or a restore that couldn't
    finish (the library is left as it was).'''


# --- creating -------------------------------------------------------------

def default_backup_dir():
    return config.user_data_dir()


def timestamped_name(prefix='RecipeWizard_backup'):
    stamp = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    return f'{prefix}_{stamp}{EXTENSION}'


def is_backup_file(filename):
    '''What the status bar and Library health count as a backup: any
    .rwbackup, or an older plain copy named *backup*.db.'''
    lower = filename.lower()
    return lower.endswith(EXTENSION) or ('backup' in lower and lower.endswith('.db'))


def list_backups(folder=None):
    '''[(path, mtime)] of backup files in `folder` (the data folder by
    default), newest first.'''
    folder = folder or default_backup_dir()
    out = []
    try:
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if is_backup_file(entry) and os.path.isfile(full):
                out.append((full, os.path.getmtime(full)))
    except OSError:
        return []
    out.sort(key=lambda t: -t[1])
    return out


def image_files(images_dir=None):
    '''Photo filenames in the ingredient images folder.'''
    images_dir = images_dir or config.INGREDIENTS_PATH
    try:
        return sorted(n for n in os.listdir(images_dir)
                      if os.path.splitext(n)[1].lower() in setup.IMAGE_EXTENSIONS
                      and os.path.isfile(os.path.join(images_dir, n)))
    except OSError:
        return []


def images_size(images_dir=None):
    '''Total bytes of the ingredient photos, for "adds 266 MB".'''
    images_dir = images_dir or config.INGREDIENTS_PATH
    return sum(os.path.getsize(os.path.join(images_dir, n)) for n in image_files(images_dir))


def _snapshot(db_path, dest):
    '''Copy a (possibly open) database with the backup API, so the copy
    is consistent even mid-write.'''
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _counts(db_path):
    con = sqlite3.connect(db_path)
    try:
        out = {}
        for key, table in _COUNTS:
            try:
                out[key] = con.execute(f'SELECT COUNT(*) FROM "{table}";').fetchone()[0]
            except sqlite3.Error:
                out[key] = 0
        return out
    finally:
        con.close()


def _schema(db_path):
    '''Tables and one-time migration markers: enough to tell an old
    backup from a current one.'''
    con = sqlite3.connect(db_path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
            " AND name NOT LIKE 'sqlite_%' ORDER BY name;")]
        markers = []
        if 'app_meta' in tables:
            markers = [r[0] for r in con.execute('SELECT key FROM app_meta ORDER BY key;')]
        return {'tables': tables, 'migrations': markers}
    finally:
        con.close()


def _manifest(db_path, images):
    counts = _counts(db_path)
    counts['images'] = len(images)
    return {
        'format': FORMAT,
        'format_version': FORMAT_VERSION,
        'app': config.APPNAME,
        'created': datetime.datetime.now().isoformat(timespec='seconds'),
        'includes_images': bool(images),
        'counts': counts,
        'schema': _schema(db_path),
    }


def create_backup(dest, include_images=False, db_path=None, images_dir=None, progress=None):
    '''Write a .rwbackup of the library to `dest`. Written beside it
    first and moved into place, so a failed backup never leaves half a
    file. Returns the manifest.'''
    db_path = db_path or config.DATABASE
    images_dir = images_dir or config.INGREDIENTS_PATH
    images = image_files(images_dir) if include_images else []
    total = len(images) + 1
    with tempfile.TemporaryDirectory(prefix='rwbackup-') as tmp:
        snap = os.path.join(tmp, _DB_MEMBER)
        _report(progress, 0, total, 'Copying the library')
        _snapshot(db_path, snap)
        manifest = _manifest(snap, images)
        part = dest + '.part'
        try:
            with zipfile.ZipFile(part, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(_MANIFEST_MEMBER, json.dumps(manifest, indent=2))
                zf.write(snap, _DB_MEMBER)
                for i, name in enumerate(images, start=1):
                    _report(progress, i, total, f'Adding photos ({i} of {len(images)})')
                    # Photos are already compressed; storing them is as
                    # small and much faster.
                    zf.write(os.path.join(images_dir, name), _IMAGES_PREFIX + name,
                             compress_type=zipfile.ZIP_STORED)
            os.replace(part, dest)
        except BaseException:
            if os.path.exists(part):
                os.remove(part)
            raise
    _report(progress, total, total, 'Done')
    return manifest


def _report(progress, done, total, text):
    if progress:
        progress(done, total, text)


# --- reading --------------------------------------------------------------

class BackupInfo:
    '''What a backup file holds. `kind` is 'rwbackup' or 'db'.'''

    def __init__(self, path, kind, manifest, image_names):
        self.path = path
        self.kind = kind
        self.manifest = manifest
        self.image_names = image_names

    @property
    def has_images(self):
        return bool(self.image_names)

    @property
    def counts(self):
        return self.manifest.get('counts', {})

    @property
    def created(self):
        return self.manifest.get('created')


def _check_library(db_path):
    '''Raise BackupError unless this is a RecipeWizard database.'''
    try:
        con = sqlite3.connect(db_path)
        try:
            ok = con.execute('PRAGMA quick_check;').fetchone()[0]
            tables = {r[0].lower() for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table';")}
        finally:
            con.close()
    except sqlite3.DatabaseError as exc:
        raise BackupError(f"This file isn't a RecipeWizard library ({exc}).") from exc
    if ok != 'ok':
        raise BackupError(f'The library in this backup is damaged ({ok}).')
    if not {'ingredients', 'recipes', 'connections'} <= tables:
        raise BackupError("This file isn't a RecipeWizard library.")


def _safe_image_name(member):
    '''The photo filename for a zip member under images/ingredients/,
    or None. Only a bare filename with an image extension; nothing
    that could climb out of the images folder.'''
    if not member.startswith(_IMAGES_PREFIX):
        return None
    name = member[len(_IMAGES_PREFIX):]
    if not name or name != os.path.basename(name) or '/' in name or '\\' in name or name in ('.', '..'):
        return None
    if os.path.splitext(name)[1].lower() not in setup.IMAGE_EXTENSIONS:
        return None
    return name


def read_backup(path):
    '''Open a .rwbackup or a plain .db backup. Raises BackupError for
    anything else.'''
    if zipfile.is_zipfile(path):
        try:
            with zipfile.ZipFile(path) as zf:
                names = zf.namelist()
                if _DB_MEMBER not in names:
                    raise BackupError('This backup has no library in it.')
                try:
                    manifest = json.loads(zf.read(_MANIFEST_MEMBER).decode('utf-8'))
                except (KeyError, ValueError):
                    manifest = {}
                images = sorted(n for n in (_safe_image_name(m) for m in names) if n)
        except zipfile.BadZipFile as exc:
            raise BackupError(f'This backup file is damaged ({exc}).') from exc
        manifest.setdefault('counts', {})
        manifest['counts']['images'] = len(images)
        manifest['includes_images'] = bool(images)
        return BackupInfo(path, 'rwbackup', manifest, images)
    _check_library(path)
    manifest = {
        'format': 'RecipeWizard database (older backup)',
        'created': datetime.datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec='seconds'),
        'includes_images': False,
        'counts': dict(_counts(path), images=0),
    }
    return BackupInfo(path, 'db', manifest, [])


def _extract_db(info, tmp):
    '''The backup's database as a file in `tmp`, checked.'''
    dest = os.path.join(tmp, 'incoming.db')
    if info.kind == 'rwbackup':
        with zipfile.ZipFile(info.path) as zf, zf.open(_DB_MEMBER) as src, open(dest, 'wb') as out:
            shutil.copyfileobj(src, out)
    else:
        _snapshot(info.path, dest)
    _check_library(dest)
    return dest


def _copy_images(info, images_dir, names, progress, overwrite):
    '''Copy photos `names` out of the backup; returns how many were
    written. Without `overwrite`, files already here are left alone.'''
    os.makedirs(images_dir, exist_ok=True)
    written = 0
    with zipfile.ZipFile(info.path) as zf:
        for i, name in enumerate(names, start=1):
            _report(progress, i, len(names), f'Copying photos ({i} of {len(names)})')
            target = os.path.join(images_dir, name)
            if not overwrite and os.path.exists(target):
                continue
            part = target + '.part'
            with zf.open(_IMAGES_PREFIX + name) as src, open(part, 'wb') as out:
                shutil.copyfileobj(src, out)
            os.replace(part, target)
            written += 1
    return written


def _safety_backup(db_path, images_dir, include_images, progress):
    '''Back up the current library before a restore changes it, into
    the data folder (so it shows up as a backup there).'''
    path = os.path.join(default_backup_dir(), timestamped_name('RecipeWizard_before-restore'))
    create_backup(path, include_images=include_images, db_path=db_path,
                  images_dir=images_dir, progress=progress)
    return path


# --- overwrite ------------------------------------------------------------

def restore_overwrite(path, db_path=None, images_dir=None, progress=None):
    '''Replace the library with the backup's, and the photos too when
    the backup has them (photos with the same name are replaced; other
    photos here stay). A safety backup of the current library comes
    first, with photos when they'll be replaced.'''
    db_path = db_path or config.DATABASE
    images_dir = images_dir or config.INGREDIENTS_PATH
    info = read_backup(path)
    with tempfile.TemporaryDirectory(prefix='rwrestore-') as tmp:
        incoming = _extract_db(info, tmp)
        # Upgrade the copy first, so a backup that can't be migrated
        # fails here, before anything of the user's has changed.
        setup.migrateDB(incoming)
        safety = _safety_backup(db_path, images_dir, info.has_images, progress)
        # Restoring through the backup API rewrites the library in
        # place, so the file the app has open stays the one in use.
        _snapshot(incoming, db_path)
    setup.migrateDB(db_path)
    images = _copy_images(info, images_dir, info.image_names, progress, overwrite=True) if info.has_images else 0
    return {'safety': safety, 'images': images, 'counts': _counts(db_path)}


# --- merge ----------------------------------------------------------------

class MergeReport:
    '''Per kind of thing: names added and names kept (already here, so
    the current version stayed). Plus extra rows (prices, components)
    and photos copied.'''

    KINDS = (
        ('suppliers', 'Suppliers'),
        ('tags', 'Tags & categories'),
        ('allergens', 'Allergens'),
        ('diets', 'Diets'),
        ('ingredients', 'Ingredients'),
        ('recipes', 'Recipes'),
        ('saved_views', 'Saved views'),
        ('saved_comparisons', 'Saved comparisons'),
        ('vendor_items', 'Vendor items'),
        ('import_formats', 'Import formats'),
    )

    def __init__(self):
        self.added = {k: [] for k, _ in self.KINDS}
        self.kept = {k: [] for k, _ in self.KINDS}
        self.prices_added = 0
        self.images_copied = 0
        self.notes = []
        self.safety = None

    def as_dict(self):
        return {'added': self.added, 'kept': self.kept, 'prices_added': self.prices_added,
                'images_copied': self.images_copied, 'notes': self.notes, 'safety': self.safety}

    def summary_lines(self):
        '''One line per kind that had anything, e.g.
        "Ingredients: 4 added, 118 already here (kept yours)".'''
        lines = []
        for key, label in self.KINDS:
            added, kept = len(self.added[key]), len(self.kept[key])
            if not added and not kept:
                continue
            parts = []
            if added:
                parts.append(f'{added} added')
            if kept:
                parts.append(f'{kept} already here (kept yours)')
            lines.append(f'{label}: {", ".join(parts)}')
        if self.prices_added:
            lines.append(f'Price history: {self.prices_added} entries added')
        if self.images_copied:
            lines.append(f'Photos: {self.images_copied} copied')
        return lines


def _norm(text):
    return ' '.join(str(text or '').split()).casefold()


class _Merger:
    '''One merge, in one transaction on the library with the backup
    attached as `src`. Each kind maps src ids to library ids: a name
    match maps to the existing row (kept as it is); otherwise the row
    is copied in and maps to the new id.'''

    def __init__(self, con, report, src_had):
        self.con = con
        self.report = report
        self.src_had = src_had   # tables / markers the backup had before migrating
        self.maps = {}

    def cols(self, schema, table):
        return [r[1] for r in self.con.execute(f'PRAGMA {schema}.table_info("{table}");')]

    def src_has(self, table):
        return self.con.execute("SELECT 1 FROM src.sqlite_master WHERE type = 'table'"
                                ' AND lower(name) = lower(?);', (table,)).fetchone() is not None

    def src_rows(self, table, order='rowid'):
        if not self.src_has(table):
            return []   # older libraries had no allergens, for one
        cur = self.con.execute(f'SELECT * FROM src."{table}" ORDER BY {order};')
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r)) for r in cur.fetchall()]

    def insert(self, table, row, skip=('id',), **overrides):
        '''Copy `row` into main.table, keeping only columns the library
        has and that aren't generated; returns the new rowid.'''
        main_cols = {c.lower(): c for c in self._insertable(table)}
        values = dict(row, **overrides)
        cols = [main_cols[k.lower()] for k in values
                if k.lower() in main_cols and k.lower() not in {s.lower() for s in skip}]
        data = {k.lower(): v for k, v in values.items()}
        sql = (f'INSERT INTO main."{table}" ({", ".join(f"{chr(34)}{c}{chr(34)}" for c in cols)})'
               f' VALUES ({", ".join("?" for _ in cols)});')
        return self.con.execute(sql, [data[c.lower()] for c in cols]).lastrowid

    def _insertable(self, table):
        # table_xinfo's `hidden` is 2/3 for generated columns
        # (unit_price), which can't be inserted into.
        return [r[1] for r in self.con.execute(f'PRAGMA main.table_xinfo("{table}");') if r[6] == 0]

    def next_order(self, table, where='', params=()):
        return self.con.execute(
            f'SELECT COALESCE(MAX(sortOrder), 0) FROM main."{table}" {where};', params).fetchone()[0]

    def index(self, table, key_sql, id_col='id', where=''):
        '''{normalized natural key: library id}, lowest id on duplicates.'''
        out = {}
        for key, row_id in self.con.execute(
                f'SELECT {key_sql}, {id_col} FROM main."{table}" {where} ORDER BY {id_col} DESC;'):
            out[_norm(key)] = row_id
        return out

    # Each step fills self.maps[kind] = {src id: library id}.

    def suppliers(self):
        have = self.index('suppliers', 'name')
        self.maps['suppliers'] = m = {}
        for row in self.src_rows('suppliers', 'id'):
            key = _norm(row['name'])
            if key in have:
                m[row['id']] = have[key]
                self.report.kept['suppliers'].append(row['name'])
            else:
                m[row['id']] = have[key] = self.insert('suppliers', row)
                self.report.added['suppliers'].append(row['name'])

    def tags(self):
        have = {}
        for tag_id, name, kind in self.con.execute(
                'SELECT id, name, kind FROM main.tags ORDER BY id DESC;'):
            have[(kind, _norm(name))] = tag_id
        self.maps['tags'] = m = {}
        new_formats = []
        # Recipe tags were seeded into an old backup by migrating it;
        # they're not the user's, so don't bring them in.
        skip_recipe_tags = 'seeded_recipe_tags' not in self.src_had['markers']
        for row in self.src_rows('tags', 'id'):
            key = (row['kind'], _norm(row['name']))
            seeded = skip_recipe_tags and row['kind'] == 'recipe_tag'
            if key in have:
                m[row['id']] = have[key]
                if not seeded:
                    self.report.kept['tags'].append(row['name'])
                if row['kind'] == 'recipe' and self._empty_template(have[key]):
                    new_formats.append(row['id'])
                continue
            if seeded:
                continue
            order = self.next_order('tags', 'WHERE kind = ?', (row['kind'],)) + 1
            m[row['id']] = have[key] = self.insert('tags', row, sortOrder=order)
            self.report.added['tags'].append(row['name'])
            if row['kind'] == 'recipe':
                new_formats.append(row['id'])
        self._new_formats = new_formats

    def _empty_template(self, tag_id):
        '''A format here that auto-adds nothing and sizes nothing (the
        seeded Bowl, Wrap… in a new library) takes the backup's
        template; one the user has set up keeps its own.'''
        return not self.con.execute(
            'SELECT 1 FROM main.tag_components WHERE tag_id = ?1'
            ' UNION ALL SELECT 1 FROM main.tag_portion_rules WHERE tag_id = ?1;',
            (tag_id,)).fetchone()

    def allergens(self):
        have = self.index('allergens', 'name')
        self.maps['allergens'] = m = {}
        for row in self.src_rows('allergens', 'COALESCE(sortOrder, id), id'):
            key = _norm(row['name'])
            if key in have:
                m[row['id']] = have[key]
                self.report.kept['allergens'].append(row['name'])
            else:
                m[row['id']] = have[key] = self.insert(
                    'allergens', row, sortOrder=self.next_order('allergens') + 1)
                self.report.added['allergens'].append(row['name'])

    def ingredients(self):
        have = self.index('Ingredients', 'Name', id_col='Id')
        self.maps['ingredients'] = m = {}
        added = []
        for row in self.src_rows('Ingredients', 'Id'):
            key = _norm(row['Name'])
            if key in have:
                m[row['Id']] = have[key]
                self.report.kept['ingredients'].append(row['Name'])
            else:
                m[row['Id']] = have[key] = self.insert('Ingredients', row, skip=('Id',))
                added.append(row['Id'])
                self.report.added['ingredients'].append(row['Name'])
        tags, allergens = self.maps['tags'], self.maps['allergens']
        has_allergens = self.src_has('ingredient_allergens')
        for src_id in added:
            new_id = m[src_id]
            for (tag_id,) in self.con.execute(
                    'SELECT tag_id FROM src.ingredient_tags_mapping WHERE ingredient_id = ?;', (src_id,)):
                if tag_id in tags:
                    self.con.execute('INSERT INTO main.ingredient_tags_mapping (tag_id, ingredient_id)'
                                     ' VALUES (?, ?);', (tags[tag_id], new_id))
            for (allergen_id,) in self.con.execute(
                    'SELECT allergen_id FROM src.ingredient_allergens WHERE ingredient_id = ?;',
                    (src_id,)) if has_allergens else ():
                if allergen_id in allergens:
                    self.con.execute('INSERT INTO main.ingredient_allergens (allergen_id, ingredient_id)'
                                     ' VALUES (?, ?);', (allergens[allergen_id], new_id))

    def prices(self):
        '''Price history adds up rather than clashing: every backup
        price an ingredient doesn't already have (same supplier, date,
        case price and units) is added, for kept ingredients too. The
        library's trigger then sets each one's cost from its latest
        price, as adding a price by hand would.'''
        ingredients, suppliers = self.maps['ingredients'], self.maps['suppliers']
        # Counted, so a backup's own repeated entries all come across
        # into a library that has none of them.
        have = collections.Counter((r[0], r[1], r[2], _num(r[3]), _num(r[4])) for r in self.con.execute(
            'SELECT ingredient_id, supplier_id, effective_date, case_price, units_per_case'
            ' FROM main.ingredient_prices;'))
        for row in self.src_rows('ingredient_prices', 'effective_date, id'):
            ing = ingredients.get(row['ingredient_id'])
            if ing is None:
                continue
            sup = suppliers.get(row['supplier_id']) if row['supplier_id'] is not None else None
            key = (ing, sup, row['effective_date'], _num(row['case_price']), _num(row['units_per_case']))
            if have[key]:
                have[key] -= 1
                continue
            # Import history stays with the library it was made in.
            self.insert('ingredient_prices', row, ingredient_id=ing, supplier_id=sup, import_batch_id=None)
            self.report.prices_added += 1

    def recipes(self):
        have = self.index('Recipes', 'Name', id_col='Id')
        self.maps['recipes'] = m = {}
        added = []
        for row in self.src_rows('Recipes', 'Id'):
            key = _norm(row['Name'])
            if key in have:
                m[row['Id']] = have[key]
                self.report.kept['recipes'].append(row['Name'])
            else:
                m[row['Id']] = have[key] = self.insert('Recipes', row, skip=('Id',))
                added.append(row)
                self.report.added['recipes'].append(row['Name'])
        ingredients, tags = self.maps['ingredients'], self.maps['tags']
        conn_cols = {c.lower() for c in self.cols('main', 'Connections')}
        for row in added:
            src_id, new_id = row['Id'], m[row['Id']]
            for conn in self.con.execute(
                    'SELECT * FROM src.Connections WHERE ParentRecipe = ? ORDER BY SortOrder, rowid;',
                    (src_id,)).fetchall():
                conn = dict(zip(self.cols('src', 'Connections'), conn))
                child_recipe = conn.get('ChildRecipe')
                child_ing = conn.get('ChildIngredient')
                if child_recipe is not None:
                    child_recipe = m.get(child_recipe)
                    if child_recipe is None or child_recipe == new_id:
                        continue
                if child_ing is not None:
                    child_ing = ingredients.get(child_ing)
                    if child_ing is None:
                        continue
                template = conn.get('from_template_tag_id')
                overrides = {'ParentRecipe': new_id, 'ChildRecipe': child_recipe, 'ChildIngredient': child_ing}
                if 'from_template_tag_id' in conn_cols:
                    overrides['from_template_tag_id'] = tags.get(template) if template is not None else None
                self.insert('Connections', conn, skip=(), **overrides)
            for (tag_id,) in self.con.execute(
                    'SELECT tag_id FROM src.recipe_tags_mapping WHERE recipe_id = ?;', (src_id,)).fetchall():
                if tag_id in tags:
                    self.con.execute('INSERT INTO main.recipe_tags_mapping (tag_id, recipe_id) VALUES (?, ?);',
                                     (tags[tag_id], new_id))
            # Adding components bumped updated_at; put back the
            # backup's (the trigger leaves an explicit change alone).
            if row.get('updated_at'):
                self.con.execute('UPDATE main.Recipes SET updated_at = ? WHERE Id = ?;',
                                 (row['updated_at'], new_id))

    def templates(self):
        '''What a new format auto-adds and its portion rules come along
        with it. A format already here keeps its own, unless it has none
        (see _empty_template). An older backup's multipliers were dropped
        when it was migrated; their effect is in its recipes' quantities.'''
        tags, ingredients = self.maps['tags'], self.maps['ingredients']
        for src_tag in self._new_formats:
            tag_id = tags[src_tag]
            for row in self.src_rows('tag_components', 'id'):
                if row['tag_id'] != src_tag or row.get('child_ingredient') not in ingredients:
                    continue
                self.insert('tag_components', row, tag_id=tag_id, child_recipe=None,
                            child_ingredient=ingredients[row['child_ingredient']])
            for row in self.src_rows('tag_portion_rules', 'id'):
                if row['tag_id'] != src_tag or row['category_tag_id'] not in tags:
                    continue
                self.con.execute('INSERT OR IGNORE INTO main.tag_portion_rules'
                                 ' (tag_id, category_tag_id, mode, amount, measure) VALUES (?, ?, ?, ?, ?);',
                                 (tag_id, tags[row['category_tag_id']], row['mode'], row['amount'],
                                  row['measure']))

    def diets(self):
        if 'diets' not in self.src_had['tables']:
            return   # seeded by migrating an old backup, not the user's
        by_key = self.index('diets', 'key')
        by_name = self.index('diets', 'name')
        allergens = self.maps['allergens']
        for row in self.src_rows('diets', 'COALESCE(sortOrder, id), id'):
            match = by_key.get(_norm(row['key'])) or by_name.get(_norm(row['name']))
            if match:
                self.report.kept['diets'].append(row['name'])
                # A diet here with no rule at all (seeded into a library
                # that had no allergens yet) takes the backup's allergens.
                ruleless = self.con.execute(
                    'SELECT nutrient IS NULL AND NOT EXISTS (SELECT 1 FROM main.diet_allergens'
                    ' WHERE diet_id = ?1) FROM main.diets WHERE id = ?1;', (match,)).fetchone()[0]
                if not ruleless:
                    continue
                new_id = match
            else:
                new_id = self.insert('diets', row, sortOrder=self.next_order('diets') + 1)
                by_key[_norm(row['key'])] = by_name[_norm(row['name'])] = new_id
                self.report.added['diets'].append(row['name'])
            for (allergen_id,) in self.con.execute(
                    'SELECT allergen_id FROM src.diet_allergens WHERE diet_id = ?;', (row['id'],)).fetchall():
                if allergen_id in allergens:
                    self.con.execute('INSERT OR IGNORE INTO main.diet_allergens (diet_id, allergen_id)'
                                     ' VALUES (?, ?);', (new_id, allergens[allergen_id]))

    def saved_views(self):
        # A view's state holds format / tag / diet names, not ids, so it
        # copies as it is.
        if 'saved_views' not in self.src_had['tables']:
            return
        have = self.index('saved_views', 'name')
        for row in self.src_rows('saved_views', 'COALESCE(sortOrder, id), id'):
            if _norm(row['name']) in have:
                self.report.kept['saved_views'].append(row['name'])
                continue
            have[_norm(row['name'])] = self.insert(
                'saved_views', row, sortOrder=self.next_order('saved_views') + 1)
            self.report.added['saved_views'].append(row['name'])

    def saved_comparisons(self):
        if 'saved_comparisons' not in self.src_had['tables']:
            return
        recipes = self.maps['recipes']
        have = self.index('saved_comparisons', 'name')
        for row in self.src_rows('saved_comparisons', 'COALESCE(sortOrder, id), id'):
            if _norm(row['name']) in have:
                self.report.kept['saved_comparisons'].append(row['name'])
                continue
            try:
                ids = [recipes[i] for i in json.loads(row['recipe_ids']) if i in recipes]
            except (TypeError, ValueError):
                ids = []
            have[_norm(row['name'])] = self.insert(
                'saved_comparisons', row, recipe_ids=json.dumps(ids),
                sortOrder=self.next_order('saved_comparisons') + 1)
            self.report.added['saved_comparisons'].append(row['name'])

    def vendor_items(self):
        '''Vendor item mappings, matched by their vendor key; the
        ingredient follows the ingredient map. Import history (batches)
        isn't merged.'''
        if 'vendor_items' not in self.src_had['tables']:
            return
        ingredients = self.maps['ingredients']
        have = {row[0] for row in self.con.execute('SELECT vendor_key FROM main.vendor_items;')}
        for row in self.src_rows('vendor_items', 'id'):
            label = ' '.join(filter(None, (row.get('description'), row.get('pack_size'))))
            if row['vendor_key'] in have:
                self.report.kept['vendor_items'].append(label)
                continue
            ing = ingredients.get(row['ingredient_id']) if row.get('ingredient_id') is not None else None
            status = row.get('status') if ing is not None or row.get('status') == 'ignored' else 'new'
            self.insert('vendor_items', row, ingredient_id=ing, status=status or 'new')
            have.add(row['vendor_key'])
            self.report.added['vendor_items'].append(label)

    def import_formats(self):
        if 'import_formats' not in self.src_had['tables']:
            return
        suppliers = self.maps['suppliers']
        have = self.index('import_formats', 'name')
        for row in self.src_rows('import_formats', 'id'):
            if _norm(row['name']) in have:
                self.report.kept['import_formats'].append(row['name'])
                continue
            try:
                settings = json.loads(row['settings'])
                aliases = settings.get('vendor_suppliers') or {}
                settings['vendor_suppliers'] = {k: suppliers[v] for k, v in aliases.items() if v in suppliers}
                text = json.dumps(settings)
            except (TypeError, ValueError, AttributeError):
                text = row['settings']
            have[_norm(row['name'])] = self.insert('import_formats', row, settings=text)
            self.report.added['import_formats'].append(row['name'])

    def run(self):
        for step in (self.suppliers, self.tags, self.allergens, self.ingredients, self.prices,
                     self.recipes, self.templates, self.diets, self.saved_views, self.saved_comparisons,
                     self.vendor_items, self.import_formats):
            step()


def _num(value):
    '''Prices compare as numbers: 12 and 12.0 are the same price.'''
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return value


def restore_merge(path, db_path=None, images_dir=None, progress=None):
    '''Add what's in the backup to the library without changing or
    deleting anything here. Matched by name (tags by kind and name,
    diets by key or name); on a match the current one stays and the
    backup's is listed as kept. Photos are copied only where no file of
    that name exists. All or nothing: on any error the library is as it
    was. Returns a MergeReport.'''
    db_path = db_path or config.DATABASE
    images_dir = images_dir or config.INGREDIENTS_PATH
    info = read_backup(path)
    report = MergeReport()
    with tempfile.TemporaryDirectory(prefix='rwmerge-') as tmp:
        incoming = _extract_db(info, tmp)
        src_had = _schema(incoming)
        src_had = {'tables': set(src_had['tables']), 'markers': set(src_had['migrations'])}
        setup.migrateDB(incoming)
        setup.migrateDB(db_path)
        _report(progress, 0, 1, 'Backing up your library first')
        report.safety = _safety_backup(db_path, images_dir, False, None)
        _report(progress, 0, 1, 'Merging')
        con = sqlite3.connect(db_path, isolation_level=None)
        try:
            con.execute('ATTACH DATABASE ? AS src;', (incoming,))
            con.execute('BEGIN IMMEDIATE;')
            try:
                _Merger(con, report, src_had).run()
                con.execute('COMMIT;')
            except BaseException:
                con.execute('ROLLBACK;')
                raise
            con.execute('DETACH DATABASE src;')
        finally:
            con.close()
    if info.has_images:
        missing = [n for n in info.image_names if not os.path.exists(os.path.join(images_dir, n))]
        if missing:
            report.images_copied = _copy_images(info, images_dir, missing, progress, overwrite=False)
    _report(progress, 1, 1, 'Done')
    return report
