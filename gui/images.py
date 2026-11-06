'''Shared helpers for photo files (ingredient and recipe photos).'''
import os
import shutil

import config

IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')


def available_images():
    '''Sorted list of image filenames in the ingredients photo folder, with
    a leading empty string so combo boxes can offer "unassigned".'''
    os.makedirs(config.INGREDIENTS_PATH, exist_ok=True)
    files = sorted(
        n for n in os.listdir(config.INGREDIENTS_PATH)
        if os.path.splitext(n)[1].lower() in IMAGE_EXTENSIONS
    )
    return [''] + files


def is_image_file(path):
    return bool(path) and os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS


def bring_in_photo(parent, path, folder):
    '''Make sure the photo at `path` is in `folder` (photos live in the
    data folder; outside ones are copied in, asking before replacing a
    file of the same name). Returns its filename there, or '' if the
    user backed out or the copy failed.'''
    from PySide6.QtWidgets import QMessageBox
    os.makedirs(folder, exist_ok=True)
    name = os.path.basename(path)
    if os.path.normcase(os.path.dirname(os.path.abspath(path))) == os.path.normcase(os.path.abspath(folder)):
        return name
    target = os.path.join(folder, name)
    if os.path.exists(target) and QMessageBox.question(
        parent, 'Replace photo?',
        f'"{name}" is already in the photos folder. Replace it?',
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
    ) != QMessageBox.Yes:
        return ''
    try:
        shutil.copy(path, target)
    except OSError as exc:
        QMessageBox.warning(parent, 'Photo not copied', str(exc))
        return ''
    return name


def choose_photo(parent, folder, title='Choose a photo'):
    '''File dialog for a photo, brought into `folder`. Returns its
    filename there, or ''.'''
    from PySide6.QtWidgets import QFileDialog
    os.makedirs(folder, exist_ok=True)
    exts = ' '.join(f'*{e}' for e in IMAGE_EXTENSIONS)
    path, _ = QFileDialog.getOpenFileName(parent, title, folder, f'Images ({exts})')
    return bring_in_photo(parent, path, folder) if path else ''
