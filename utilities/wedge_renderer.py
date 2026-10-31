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


_KNOWN_SHAPES = {'ring', 'bowl', 'wrap', 'tray', 'jar', 'box', 'cone', 'plate'}

# Brand inks for silhouettes — per the design, silhouettes are always
# painted in brand colors regardless of the recipe's tag color:
# Parmesan fill, Kale stroke. Category color lives in the slices, not
# the format cue, so the format reads as "the shape" rather than
# "the shape in some color".
_SILHOUETTE_FILL = (255, 241, 218, 255)   # #fff1da parmesan
_SILHOUETTE_STROKE = (8, 44, 0, 255)      # #082c00 kale


def _paint_silhouette(canvas, shape, _color_hex_ignored, render_size):
    '''Draw the format silhouette into `canvas` before the wedge is rendered
    on top. Unknown shapes are a no-op so user-added recipe tags with
    shape='none' (or anything unrecognized) render the bare wedge.

    `color_hex` is accepted for backward compatibility with earlier
    callers but ignored — silhouettes are always brand-painted now.'''
    if shape not in _KNOWN_SHAPES:
        return
    draw = ImageDraw.Draw(canvas)
    fill = _SILHOUETTE_FILL
    stroke = _SILHOUETTE_STROKE
    stroke_w = max(2, render_size // 60)   # ~1.4 at 100-unit viewBox
    sz = render_size

    if shape == 'ring':
        # Thin outer ring stroked in Kale — the design's Salad silhouette.
        margin = sz * 0.01
        draw.ellipse(
            (margin, margin, sz - margin, sz - margin),
            fill=fill, outline=stroke, width=stroke_w,
        )
        # Inner ring hint, half-weight stroke.
        inset = sz * 0.09
        draw.ellipse(
            (inset, inset, sz - inset, sz - inset),
            outline=stroke, width=max(1, stroke_w // 2),
        )
    elif shape == 'bowl':
        # Full bowl: a wide "D" with a tiny foot. The upper rim is a
        # straight line, the lower bowl is a semicircle. Painted with
        # fill + kale stroke to match the design.
        rim_y = sz * 0.44
        foot_y = sz * 0.91
        foot_half_w = sz * 0.11
        foot_h = sz * 0.06
        bowl_bbox = (sz * 0.03, rim_y - sz * 0.01, sz * 0.97, foot_y)
        draw.pieslice(bowl_bbox, start=0, end=180, fill=fill, outline=stroke,
                      width=stroke_w)
        # The pieslice draws a chord — add the straight rim line explicitly
        # over any gap and the little base.
        draw.line((sz * 0.03, rim_y, sz * 0.97, rim_y), fill=stroke,
                  width=stroke_w)
        # Little trapezoid base below.
        draw.polygon(
            [(sz / 2 - foot_half_w, foot_y),
             (sz / 2 + foot_half_w, foot_y),
             (sz / 2 + foot_half_w * 0.6, foot_y + foot_h),
             (sz / 2 - foot_half_w * 0.6, foot_y + foot_h)],
            fill=fill, outline=stroke,
        )
    elif shape == 'wrap':
        # New Wrap silhouette (design-updated): a horizontal rounded
        # rectangle in a lighter cream, with a vertical fold curve on
        # the right and a small center highlight circle. Reads clearly
        # as a wrapped tortilla without needing rotation.
        rect_w = sz * 0.96
        rect_h = sz * 0.56
        corner_r = rect_h * 0.25
        x0 = (sz - rect_w) / 2
        y0 = (sz - rect_h) / 2
        wrap_fill = (251, 230, 196, 255)   # #fbe6c4 — one step warmer than parmesan
        draw.rounded_rectangle(
            (x0, y0, x0 + rect_w, y0 + rect_h),
            radius=corner_r, fill=wrap_fill, outline=stroke, width=stroke_w,
        )
        # Fold curve on the right third — gently bowed vertical line.
        # Approximate the SVG quadratic Q with a few interpolated points.
        import math
        fold_x_start = x0 + rect_w * 0.83
        fold_x_mid = x0 + rect_w * 0.73
        fold_x_end = x0 + rect_w * 0.83
        pts = []
        for t_pct in range(0, 101, 5):
            t = t_pct / 100
            # Quadratic Bezier between (fold_x_start, y_top), control
            # (fold_x_mid, y_mid), end (fold_x_end, y_bot).
            x = (1 - t) ** 2 * fold_x_start + 2 * (1 - t) * t * fold_x_mid + t ** 2 * fold_x_end
            y = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * (y0 + rect_h / 2) + t ** 2 * (y0 + rect_h)
            pts.append((x, y))
        for a, b in zip(pts, pts[1:]):
            draw.line([a, b], fill=stroke, width=max(1, stroke_w - 1))
        # Center circle — the design shows a small circle at the fold
        # midpoint for visual rhythm.
        cx = x0 + rect_w * 0.71
        cy = y0 + rect_h / 2
        r = rect_h * 0.10
        draw.ellipse((cx - r, cy - r, cx + r, cy + r),
                     fill=fill, outline=stroke, width=stroke_w)
    elif shape == 'tray':
        # Rounded-square tray with little side-handle nubs sticking out
        # on the left and right, matching the design's Catering shape.
        margin = sz * 0.05
        draw.rounded_rectangle(
            (margin, sz * 0.10, sz - margin, sz * 0.90),
            radius=sz * 0.07, fill=fill, outline=stroke, width=stroke_w,
        )
        # Inner rectangle hint — thinner stroke.
        inset = sz * 0.10
        draw.rounded_rectangle(
            (inset, sz * 0.15, sz - inset, sz * 0.85),
            radius=sz * 0.04, outline=stroke, width=max(1, stroke_w // 2),
        )
        # Side handles.
        handle_h = sz * 0.20
        handle_w = sz * 0.035
        handle_y0 = sz * 0.40
        handle_y1 = handle_y0 + handle_h
        draw.rectangle(
            (margin - handle_w - 2, handle_y0, margin, handle_y1),
            fill=fill, outline=stroke, width=max(1, stroke_w - 1),
        )
        draw.rectangle(
            (sz - margin, handle_y0, sz - margin + handle_w + 2, handle_y1),
            fill=fill, outline=stroke, width=max(1, stroke_w - 1),
        )
    elif shape == 'jar':
        # Tall narrow rounded rectangle — reads as a catering jar / mason
        # jar / smoothie cup. Verticality is what distinguishes it from
        # 'tray' and 'box'; the wedge covers the middle and the jar
        # extends well above and below.
        rect_w = sz * 0.55
        rect_h = sz * 0.96
        corner_r = rect_w * 0.22
        cx, cy = sz / 2, sz / 2
        x0 = cx - rect_w / 2
        y0 = cy - rect_h / 2
        draw.rounded_rectangle(
            (x0, y0, x0 + rect_w, y0 + rect_h),
            radius=corner_r, fill=fill,
        )
    elif shape == 'box':
        # Sharp-cornered square — bento / takeout box silhouette. The
        # corners distinguish it from 'tray', which has the same overall
        # footprint but rounded corners.
        margin = sz * 0.04
        draw.rectangle(
            (margin, margin, sz - margin, sz - margin), fill=fill,
        )
    elif shape == 'cone':
        # Downward-pointing triangle — taco / cone / hand-held silhouette.
        # Apex at the bottom-center, base across the top so it reads as
        # something held narrow-end-down.
        apex = (sz / 2, sz * 0.97)
        top_left = (sz * 0.04, sz * 0.18)
        top_right = (sz * 0.96, sz * 0.18)
        draw.polygon([top_left, top_right, apex], fill=fill)
    elif shape == 'plate':
        # Plate viewed from a slight angle — a wide horizontal ellipse
        # bigger than the canvas, biased downward so the bottom rim is
        # visible beneath the wedge. Distinguishable from 'ring' (which
        # is concentric and uniform) by its horizontal stretch + offset.
        cx, cy = sz / 2, sz * 0.55
        width = sz * 1.20
        height = sz * 0.90
        bbox = (cx - width / 2, cy - height / 2,
                cx + width / 2, cy + height / 2)
        draw.ellipse(bbox, fill=fill)


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
