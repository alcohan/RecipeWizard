'''Shared helpers for ingredient image file discovery.'''
import os

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
