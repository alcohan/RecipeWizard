import os
import sqlite3

import db
from utilities import backup


def _png(path, color=(200, 40, 40)):
    from PIL import Image
    Image.new('RGB', (64, 48), color).save(path)


def test_recipe_image_set_get_and_duplicate(lib):
    rid = lib.recipe('Cobb')
    assert db.get_recipe_image(rid) == ''
    db.set_recipe_image(rid, 'cobb.png')
    assert db.get_recipe_image(rid) == 'cobb.png'
    copy = db.duplicate_recipe(rid)
    assert db.get_recipe_image(copy) == 'cobb.png'     # the copy shares the photo
    db.set_recipe_image(rid, '')
    assert db.get_recipe_image(rid) == ''
    assert db.get_recipe_image(copy) == 'cobb.png'


def test_print_data_carries_photo(lib):
    rid = lib.recipe('Cobb')
    assert db.recipe_print_data(rid)['photo'] == ''
    db.set_recipe_image(rid, 'cobb.png')
    assert db.recipe_print_data(rid)['photo'] == 'cobb.png'


def test_backup_carries_recipe_photos(lib, tmp_path):
    ing_dir, rec_dir = tmp_path / 'ing', tmp_path / 'rec'
    ing_dir.mkdir()
    rec_dir.mkdir()
    _png(ing_dir / 'kale.png')
    _png(rec_dir / 'cobb.png')
    rid = lib.recipe('Cobb')
    db.set_recipe_image(rid, 'cobb.png')
    kw = dict(db_path=lib.path, images_dir=str(ing_dir), recipe_images_dir=str(rec_dir),
              branding_dir=str(tmp_path / 'brand'))

    lean = str(tmp_path / 'lean.rwbackup')
    backup.create_backup(lean, include_images=False, **kw)
    assert backup.read_backup(lean).recipe_image_names == []

    full = str(tmp_path / 'full.rwbackup')
    manifest = backup.create_backup(full, include_images=True, **kw)
    assert manifest['counts']['images'] == 2 and manifest['counts']['recipe_images'] == 1
    info = backup.read_backup(full)
    assert info.image_names == ['kale.png'] and info.recipe_image_names == ['cobb.png']
    assert info.photo_count == 2

    # Merge into an empty photo folder: copied, and the recipe row keeps
    # its filename (the recipe itself is already here, so it's kept).
    other = tmp_path / 'other-rec'
    report = backup.restore_merge(full, safety=False, **dict(kw, recipe_images_dir=str(other)))
    assert (other / 'cobb.png').is_file() and report.images_copied >= 1

    # Overwrite restores the column and the file.
    db.set_recipe_image(rid, '')
    os.remove(other / 'cobb.png')
    backup.restore_overwrite(full, safety=False, **dict(kw, recipe_images_dir=str(other)))
    con = sqlite3.connect(lib.path)
    assert con.execute('SELECT ImageFilename FROM Recipes WHERE Name = ?;', ('Cobb',)).fetchone() == ('cobb.png',)
    con.close()
    assert (other / 'cobb.png').is_file()


def test_merge_adds_recipe_with_photo(lib, tmp_path):
    rid = lib.recipe('Nicoise')
    db.set_recipe_image(rid, 'nicoise.jpg')
    path = str(tmp_path / 'b.rwbackup')
    backup.create_backup(path, db_path=lib.path, images_dir=str(tmp_path))
    lib.sql('DELETE FROM Recipes;')
    backup.restore_merge(path, db_path=lib.path, images_dir=str(tmp_path),
                         recipe_images_dir=str(tmp_path / 'rec'),
                         branding_dir=str(tmp_path / 'brand'), safety=False)
    con = sqlite3.connect(lib.path)
    assert con.execute('SELECT ImageFilename FROM Recipes;').fetchall() == [('nicoise.jpg',)]
    con.close()


def test_thumbnail_cache_keeps_folders_apart(tmp_path, monkeypatch):
    import config
    from gui import thumbs
    monkeypatch.setattr(config, 'user_data_dir', lambda: str(tmp_path / 'data'))
    ing, rec = tmp_path / 'ing', tmp_path / 'rec'
    ing.mkdir()
    rec.mkdir()
    monkeypatch.setattr(config, 'INGREDIENTS_PATH', str(ing))
    _png(ing / 'same.png', (255, 0, 0))
    _png(rec / 'same.png', (0, 0, 255))
    os.utime(rec / 'same.png', (os.path.getmtime(ing / 'same.png'),) * 2)
    a = thumbs.thumbnail_image('same.png', 32)
    b = thumbs.thumbnail_image('same.png', 32, str(rec))
    assert a.pixelColor(16, 16).red() > 200
    assert b.pixelColor(16, 16).blue() > 200
