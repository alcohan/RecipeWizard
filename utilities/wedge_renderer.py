'''Render a salad-style wedge preview for a recipe.

Each direct component of the recipe gets one equal-sized wedge. Ingredients
with an assigned image have their wedge filled with a zoomed center crop of
that image (composited on a pastel fallback so transparent PNG edges still
read as filled). Wedges without an image show just the pastel.

When a recipe has a "format" tag, a pastel silhouette is painted behind
the wedge so the format reads at a glance from the gallery. The shape is
driven by the tag's `shape` column — one of 'ring', 'bowl', 'wrap', 'tray',
or 'none'. The Tags Manager lets the user pick a shape per recipe tag, so
custom user tags can re-use any of the shapes.
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


def render_recipe(components, size=300, shape=None, shape_color=None):
    '''Render a wedge preview. `components` is a list of dicts with keys
    Name, Type ('ingredient'|'recipe'), and ImageFilename (may be None).
    `shape` is a silhouette name from {'ring','bowl','wrap','tray'}; any
    other value (None, 'none', '') renders no silhouette. `shape_color`
    is a hex like '#16a34a' supplying the pastel fill. Returns PNG bytes,
    or None if PIL is unavailable.

    Results are cached on every input that affects pixels, so an unchanged
    recipe never re-renders after the first call. After editing one recipe,
    the home gallery refresh only re-renders the one that changed.'''
    if Image is None:
        return None
    key = tuple((c.get('Name'), c.get('Type'), c.get('ImageFilename')) for c in components)
    shape_key = (shape or '').lower() or None
    return _render_cached(key, size, shape_key, shape_color)


@lru_cache(maxsize=512)
def _render_cached(components_key, size, shape, shape_color):
    components = [
        {'Name': name, 'Type': type_, 'ImageFilename': fname}
        for (name, type_, fname) in components_key
    ]
    return _render_uncached(components, size, shape, shape_color)


def _hex_to_rgba(hex_str, alpha):
    '''Hex string → (r, g, b, alpha) tuple. Falls back to grey on garbage.'''
    if not hex_str or not isinstance(hex_str, str) or not hex_str.startswith('#') or len(hex_str) != 7:
        return (200, 200, 200, alpha)
    try:
        return (int(hex_str[1:3], 16), int(hex_str[3:5], 16), int(hex_str[5:7], 16), alpha)
    except ValueError:
        return (200, 200, 200, alpha)


_KNOWN_SHAPES = {'ring', 'bowl', 'wrap', 'tray'}


def _paint_silhouette(canvas, shape, color_hex, render_size):
    '''Draw the format silhouette into `canvas` before the wedge is rendered
    on top. Unknown shapes are a no-op so user-added recipe tags with
    shape='none' (or anything unrecognized) render the bare wedge.'''
    if shape not in _KNOWN_SHAPES:
        return
    draw = ImageDraw.Draw(canvas)
    fill = _hex_to_rgba(color_hex, alpha=140)
    sz = render_size

    if shape == 'ring':
        # Pastel ring just outside the wedge — uses the wedge bbox extended
        # outward; the wedge will paint on top of the inside, leaving a
        # thin colored frame visible.
        margin = sz * 0.01
        draw.ellipse((margin, margin, sz - margin, sz - margin), fill=fill)
    elif shape == 'bowl':
        # Bottom half of a true circle — bowl seen from the front. The
        # circle is wider than the wedge so the rim curves visibly out to
        # the sides and below.
        diameter = sz * 1.20
        cx = sz / 2
        cy = sz * 0.55
        bbox = (cx - diameter / 2, cy - diameter / 2,
                cx + diameter / 2, cy + diameter / 2)
        draw.pieslice(bbox, start=0, end=180, fill=fill)
    elif shape == 'wrap':
        # Rounded rectangle tilted at an angle — reads as a wrap held
        # diagonally. Drawn on an oversized transparent layer so the
        # rotation doesn't crop the corners; the layer is cropped back to
        # the canvas size before compositing.
        rect_w = sz * 1.15
        rect_h = sz * 0.48
        corner_r = rect_h * 0.22  # gentle rounding, still reads as rectangular
        angle_deg = 22
        pad = int(sz * 0.30)
        big = sz + 2 * pad
        layer = Image.new('RGBA', (big, big), (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        x0 = (big - rect_w) / 2
        y0 = (big - rect_h) / 2
        layer_draw.rounded_rectangle(
            (x0, y0, x0 + rect_w, y0 + rect_h),
            radius=corner_r, fill=fill,
        )
        layer = layer.rotate(angle_deg, resample=Image.BICUBIC)
        layer = layer.crop((pad, pad, pad + sz, pad + sz))
        canvas.alpha_composite(layer)
    elif shape == 'tray':
        # Rounded-square tray — square corners stick out behind the wedge's
        # circular outline.
        margin = sz * 0.015
        draw.rounded_rectangle(
            (margin, margin, sz - margin, sz - margin),
            radius=sz * 0.07, fill=fill,
        )


def _render_uncached(components, size, shape, shape_color):
    render_size = size * SUPERSAMPLE
    canvas = Image.new('RGBA', (render_size, render_size), (255, 255, 255, 0))

    # Silhouette is painted first so the wedge layers on top of it. When a
    # silhouette is set, shrink the wedge so the silhouette's outline can
    # actually peek out around it.
    has_silhouette = (shape or '') in _KNOWN_SHAPES
    if has_silhouette:
        _paint_silhouette(canvas, shape, shape_color, render_size)

    draw = ImageDraw.Draw(canvas)

    cx, cy = render_size / 2, render_size / 2
    if has_silhouette:
        radius = render_size * 0.42  # shrunk so silhouette is visible
    else:
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
