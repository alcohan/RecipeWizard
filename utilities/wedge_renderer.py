'''Render a salad-style wedge preview for a recipe.

Each direct component of the recipe gets one equal-sized wedge. Ingredients
with an assigned image have their wedge filled with a zoomed center crop of
that image (composited on a pastel fallback so transparent PNG edges still
read as filled). Wedges without an image show just the pastel.
'''
from functools import lru_cache
from io import BytesIO
from math import pi, cos, sin
import os

import config

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = None
    ImageDraw = None

PALETTE = [
    (240, 220, 200),
    (220, 235, 210),
    (250, 220, 215),
    (220, 230, 245),
    (245, 235, 200),
    (230, 215, 235),
    (245, 215, 205),
    (215, 235, 230),
    (235, 225, 210),
    (225, 220, 245),
    (235, 240, 215),
    (245, 225, 230),
]

ZOOM = 0.7  # inner fraction of the square crop to keep — pushes the subject forward
SUPERSAMPLE = 3  # internal render multiplier; downsampled with LANCZOS for smoother edges


def _palette_color(key):
    return PALETTE[hash(key) % len(PALETTE)]


@lru_cache(maxsize=256)
def _zoomed_square(path, size):
    '''Load image, center-square-crop, zoom in, resize to (size, size). Returns RGBA Image or None.

    Cached: ingredients are reused across many recipes, so the gallery's
    cold render goes from "open+resize the same PNG 5x" to once.'''
    try:
        img = Image.open(path).convert('RGBA')
    except Exception as exc:
        print(f'wedge_renderer: failed to open {path}: {exc}')
        return None
    w, h = img.size
    side = min(w, h)
    img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
    if ZOOM < 1.0:
        crop_side = int(side * ZOOM)
        offset = (side - crop_side) // 2
        img = img.crop((offset, offset, offset + crop_side, offset + crop_side))
    return img.resize((size, size), Image.LANCZOS)


def render_recipe(components, size=300):
    '''Render a wedge preview. `components` is a list of dicts with keys
    Name, Type ('ingredient'|'recipe'), and ImageFilename (may be None).
    Returns PNG bytes, or None if PIL is unavailable.

    Results are cached: only Name / Type / ImageFilename affect the rendered
    image (wedge sectors are equal-sized regardless of quantity), so an
    unchanged recipe never re-renders. After editing one recipe, the home
    gallery refresh only re-renders the one that changed.'''
    if Image is None:
        return None
    key = tuple((c.get('Name'), c.get('Type'), c.get('ImageFilename')) for c in components)
    return _render_cached(key, size)


@lru_cache(maxsize=512)
def _render_cached(components_key, size):
    components = [
        {'Name': name, 'Type': type_, 'ImageFilename': fname}
        for (name, type_, fname) in components_key
    ]
    return _render_uncached(components, size)


def _render_uncached(components, size):
    render_size = size * SUPERSAMPLE
    canvas = Image.new('RGBA', (render_size, render_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(canvas)

    cx, cy = render_size / 2, render_size / 2
    radius = render_size / 2 - 6 * SUPERSAMPLE
    bbox = (cx - radius, cy - radius, cx + radius, cy + radius)
    diameter = int(bbox[2] - bbox[0])

    def emit():
        out = canvas.resize((size, size), Image.LANCZOS)
        buf = BytesIO()
        out.save(buf, format='PNG')
        return buf.getvalue()

    n = len(components)
    if n == 0:
        draw.ellipse(bbox, outline=(200, 200, 200, 255), width=2 * SUPERSAMPLE)
        return emit()

    sweep = 360 / n
    start_at_top = -90

    for i, comp in enumerate(components):
        start = start_at_top + i * sweep
        end = start + sweep
        color = _palette_color(comp.get('Name') or '')

        wedge_mask = Image.new('L', (render_size, render_size), 0)
        ImageDraw.Draw(wedge_mask).pieslice(bbox, start, end, fill=255)

        layer = Image.new('RGBA', (render_size, render_size), (255, 255, 255, 0))

        filename = comp.get('ImageFilename') if comp.get('Type') == 'ingredient' else None
        path = os.path.join(config.INGREDIENTS_PATH, filename) if filename else None

        if path and os.path.isfile(path):
            tile = Image.new('RGBA', (diameter, diameter), color + (255,))
            subject = _zoomed_square(path, diameter)
            if subject is not None:
                tile.paste(subject, (0, 0), subject)
            layer.paste(tile, (int(bbox[0]), int(bbox[1])))
        else:
            ImageDraw.Draw(layer).ellipse(bbox, fill=color + (255,))

        canvas.paste(layer, (0, 0), wedge_mask)

    # Subtle white separators between wedges
    for i in range(n):
        angle = (start_at_top + i * sweep) * pi / 180
        x_end = cx + radius * cos(angle)
        y_end = cy + radius * sin(angle)
        draw.line((cx, cy, x_end, y_end), fill=(255, 255, 255, 200), width=2 * SUPERSAMPLE)

    draw.ellipse(bbox, outline=(120, 120, 120, 255), width=2 * SUPERSAMPLE)

    return emit()
