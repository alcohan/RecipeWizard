'''Paint printable recipe pages with QPainter, onto a QPrinter (print,
the system print dialog, PDF) or any paint device.

One recipe is one page unless its ingredient list runs long, when the
table continues on more pages. Layout, top to bottom:
  brand bar     logo · header label + printed date · accent rule
  title block   name, format, tag and diet pills, yield / serving, the
                allergen box; the wedge top-right
  body          ingredients table; nutrition facts and the scoop key
                beside it (first page only)
A page that would spill over first tightens the rows and shrinks the
ingredient statements (FIT_STEPS); it only runs onto a second page when
even the smallest step doesn't fit.
  footer        footer text · "name · Page 1 of 2"
No cost anywhere. Data comes from db.recipe_print_data(); branding from
gui.services.print_branding.

All layout is in points (1/72 in). The painter is scaled so one unit is
a tenth of a point, which lets fonts use whole pixel sizes for any
point size; `_Page` hides that behind point-based helpers.
'''
from datetime import date

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QFontMetricsF, QImage, QPageLayout, QPainter, QPainterPath, QPen, QTextDocument,
)
from html import escape

from utilities import recipe_print
from utilities.wedge_renderer import render_recipe
from gui.widgets.wedge_view import photo_image

_U = 10.0   # painter units per point

INK = QColor('#1c1917')
MUTED = QColor('#55624c')
RULE = QColor('#ebe1cd')
DANGER = QColor('#b80700')
DANGER_BG = QColor('#ffe8e3')
FACILITY = QColor('#8a4a00')    # "made in a facility that also handles"
DIET_FG = QColor('#24502A')     # the Library's diet pills
DIET_BG = QColor('#E6EFE3')
BLACK = QColor('#000000')

MARGIN_X = 43.0
MARGIN_TOP = 34.0
MARGIN_BOTTOM = 30.0
SIDE_W = 150.0          # nutrition + scoop key column
WEDGE = 112.0           # the photo or wedge, top-right over that column
GUTTER = 16.0
FAMILY = 'Segoe UI'

# Ingredient table columns: (key, header, width or None for the flexible one)
_COLUMNS = (
    ('n', '#', 16.0),
    ('name', 'Ingredient', None),
    ('amount', 'Amount', 56.0),
    ('tool', 'Portion tool', 82.0),
    ('allergens', 'Allergens', 74.0),
)
_CELL_PAD = 4.0
# (statement point size, row padding), tried in order until the table
# fits one page; the first is the normal look.
FIT_STEPS = ((7.0, 5.0), (6.5, 4.0), (6.0, 3.5), (5.5, 3.0))

_NUTRIENT_ROWS = (
    # (label, key, unit, indent, bold)
    ('Total Fat', 'TTLFatGrams', 'g', False, True),
    ('Saturated Fat', 'SatFatGrams', 'g', True, False),
    ('Cholesterol', 'CholesterolMilligrams', 'mg', False, True),
    ('Sodium', 'SodiumMilligrams', 'mg', False, True),
    ('Total Carbohydrate', 'CarbGrams', 'g', False, True),
    ('Dietary Fiber', 'FiberGrams', 'g', True, False),
    ('Total Sugars', 'SugarGrams', 'g', True, False),
    ('Protein', 'ProteinGrams', 'g', False, True),
)


def _font(pt, weight=QFont.Normal, family=FAMILY):
    f = QFont(family)
    f.setPixelSize(max(1, round(pt * _U)))
    f.setWeight(weight)
    return f


def _mix(color, toward, amount):
    '''`color` moved `amount` (0..1) of the way to `toward`.'''
    c, t = QColor(color), QColor(toward)
    return QColor(round(c.red() + (t.red() - c.red()) * amount),
                  round(c.green() + (t.green() - c.green()) * amount),
                  round(c.blue() + (t.blue() - c.blue()) * amount))


class _Page:
    '''Point-based drawing helpers over a painter scaled to tenths of a
    point. Also usable without a painter, for measuring.'''

    def __init__(self, painter=None):
        self.p = painter

    # measuring
    def text_width(self, font, text):
        return QFontMetricsF(font).horizontalAdvance(text) / _U

    def line_height(self, font):
        return QFontMetricsF(font).height() / _U

    def wrapped_height(self, font, text, width):
        if not text:
            return 0.0
        r = QFontMetricsF(font).boundingRect(QRectF(0, 0, width * _U, 1e7),
                                             int(Qt.TextWordWrap | Qt.AlignLeft), text)
        return r.height() / _U

    # drawing
    def text(self, x, y, w, h, font, color, text, flags=Qt.AlignLeft | Qt.AlignTop):
        if self.p is None:
            return
        self.p.setFont(font)
        self.p.setPen(QPen(QColor(color)))
        self.p.drawText(QRectF(x * _U, y * _U, w * _U, h * _U), int(flags), text)

    def wrapped(self, x, y, w, font, color, text):
        h = self.wrapped_height(font, text, w)
        self.text(x, y, w, h + 1, font, color, text, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap)
        return h

    def line(self, x1, y1, x2, y2, color, width):
        if self.p is None:
            return
        self.p.setPen(QPen(QColor(color), width * _U, Qt.SolidLine, Qt.FlatCap))
        self.p.drawLine(QPointF(x1 * _U, y1 * _U), QPointF(x2 * _U, y2 * _U))

    def rounded(self, x, y, w, h, radius, fill=None, border=None, border_w=1.0):
        if self.p is None:
            return
        self.p.setPen(QPen(QColor(border), border_w * _U) if border else Qt.NoPen)
        self.p.setBrush(QBrush(QColor(fill)) if fill else Qt.NoBrush)
        self.p.drawRoundedRect(QRectF(x * _U, y * _U, w * _U, h * _U), radius * _U, radius * _U)
        self.p.setBrush(Qt.NoBrush)

    def image(self, x, y, w, h, img):
        if self.p is None:
            return
        self.p.drawImage(QRectF(x * _U, y * _U, w * _U, h * _U), img)

    def dot(self, x, y, d, tool):
        '''A scoop's color dot, striped for a slotted pattern.'''
        if self.p is None:
            return
        rect = QRectF(x * _U, y * _U, d * _U, d * _U)
        fill = QColor(tool.color or '#ffffff')
        self.p.setPen(Qt.NoPen)
        self.p.setBrush(QBrush(fill))
        self.p.drawEllipse(rect)
        if tool.pattern == 'striped':
            path = QPainterPath()
            path.addEllipse(rect)
            self.p.save()
            self.p.setClipPath(path)
            self.p.setPen(QPen(QColor('#ffffff'), 0.9 * _U))
            step = d / 4.0
            sx = x + step / 2
            while sx < x + d:
                self.p.drawLine(QPointF(sx * _U, y * _U), QPointF(sx * _U, (y + d) * _U))
                sx += step
            self.p.restore()
        self.p.setPen(QPen(QColor(0, 0, 0, 110), 0.6 * _U))
        self.p.setBrush(Qt.NoBrush)
        self.p.drawEllipse(rect)


# --- fonts -----------------------------------------------------------------

F_LABEL = _font(7.0, QFont.DemiBold)
F_SMALL = _font(7.5)
F_META = _font(9.0)
F_META_BOLD = _font(9.0, QFont.DemiBold)
F_TITLE = _font(19.0, QFont.Bold)
F_PILL = _font(8.0, QFont.DemiBold)
F_ALLERGENS = _font(11.5, QFont.Bold)
F_HEAD = _font(7.0, QFont.DemiBold)
F_NAME = _font(9.0, QFont.DemiBold)
F_AMOUNT = _font(9.5, QFont.Bold)
F_TOOL = _font(8.5, QFont.DemiBold)
F_TOOL_PLAIN = _font(8.5)
F_CELL_ALG = _font(7.5)
F_FACILITY = _font(8.5, QFont.DemiBold)
F_SECTION = _font(7.5, QFont.Bold)
F_STATEMENT = _font(7.0)
F_DISCLAIMER = _font(7.0)
F_DISCLAIMER.setItalic(True)


def _statement_doc(text, width, pt=7.0):
    '''"Ingredients: …" laid out as rich text `width` points wide.'''
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    doc.setDefaultFont(F_STATEMENT if pt == 7.0 else _font(pt))
    doc.setTextWidth(width * _U)
    doc.setHtml(f'<span style="color:{MUTED.name()}"><b style="color:{INK.name()}">Ingredients:</b> '
                f'{escape(text)}</span>')
    return doc


# --- layout ------------------------------------------------------------------

class RecipePageLayout:
    '''Where one recipe's pages break. Measures without painting, so
    the footer can say "Page 1 of 2" before anything is drawn.'''

    def __init__(self, data, page_w, page_h, disclaimer='', fit=FIT_STEPS[0]):
        self.data = data
        self.statement_pt, self.row_pad = fit
        self.disclaimer = (disclaimer or '').strip()
        self.page_w, self.page_h = page_w, page_h
        self.content_w = page_w - 2 * MARGIN_X
        self.table_w = self.content_w - SIDE_W - GUTTER
        # Without portions (recipe_print.without_portions) the Amount and
        # Portion tool columns go and the ingredient name takes their width.
        self.columns = [c for c in _COLUMNS if data.get('portions', True) or c[0] not in ('amount', 'tool')]
        flex = self.table_w - sum(w for _k, _h, w in self.columns if w)
        self.widths = {k: (w if w else flex) for k, _h, w in self.columns}
        m = _Page()
        self.statement_w = self.table_w - self.widths['n'] - 2 * _CELL_PAD
        self.statement_heights = [self._statement_height(m, row) for row in data['rows']]
        self.row_heights = [self._row_height(m, row) + sh
                            for row, sh in zip(data['rows'], self.statement_heights)]
        self.disclaimer_h = m.wrapped_height(F_DISCLAIMER, self.disclaimer, self.content_w)
        self.pages = self._paginate(m)   # list of (first row, end row) per page

    def _row_height(self, m, row):
        name_h = m.wrapped_height(F_NAME, row['name'], self.widths['name'] - 2 * _CELL_PAD)
        alg_w = self.widths['allergens'] - 2 * _CELL_PAD
        alg_h = m.wrapped_height(F_CELL_ALG, row['allergens'], alg_w)
        if row.get('facility'):
            alg_h += m.wrapped_height(F_CELL_ALG, 'facility: ' + row['facility'], alg_w)
        tool_h = m.line_height(F_TOOL) if row['tool'] else 0
        return max(name_h, alg_h, tool_h, m.line_height(F_AMOUNT)) + 2 * self.row_pad

    def _statement_height(self, m, row):
        '''Extra height under a row for its ingredient statement.'''
        if not row.get('statement'):
            return 0.0
        doc = _statement_doc(row['statement'], self.statement_w, self.statement_pt)
        return doc.size().height() / _U + self.row_pad

    def body_top_first(self, m):
        return self.title_block_bottom(m) + 10.0

    def body_top_more(self, m):
        return MARGIN_TOP + 24.0 + 12.0 + m.line_height(F_META_BOLD) + 10.0

    def footer_top(self):
        return self.page_h - MARGIN_BOTTOM - 12.0

    def disclaimer_top(self):
        return self.footer_top() - 6.0 - self.disclaimer_h

    def body_bottom(self):
        if self.disclaimer:
            return self.disclaimer_top() - 10.0
        return self.page_h - MARGIN_BOTTOM - 20.0

    def header_height(self, m):
        return m.line_height(F_SECTION) + 6.0 + m.line_height(F_HEAD) + 7.0

    def title_block_bottom(self, m):
        left_w = self.table_w     # title, pills and allergen box line up with the table
        y = MARGIN_TOP + 24.0 + 12.0
        y += m.wrapped_height(F_TITLE, self.data['name'], left_w) + 5.0
        y += self._meta_height(m, left_w) + 10.0
        y += self._allergen_box_height(m, left_w)
        return max(y, MARGIN_TOP + 24.0 + 12.0 + WEDGE)

    def _meta_items(self):
        d = self.data
        items = []
        if d['format']:
            items.append(('pill', d['format']['name'], d['format']['color'] or '#64748b'))
        for t in d['tags']:
            items.append(('tag', t['name'], t['color'] or '#64748b'))
        for name in d.get('diets') or ():
            items.append(('diet', name, DIET_FG))
        items.append(('break', ''))   # yield and serving start their own line
        items.append(('bold', f"Yield: {recipe_print.fraction_text(d['output_qty'])} {d['unit']}".strip()))
        if d['weight']:
            grams = float(d['weight'])
            items.append(('muted', f'Serving {grams:.0f} g ({grams / 28.3495:.1f} oz)'))
        return items

    def _item_width(self, m, item):
        kind, text = item[0], item[1]
        if kind == 'break':
            return 0.0
        if kind in ('pill', 'tag', 'diet'):
            return m.text_width(F_PILL, text) + 14.0
        return m.text_width(F_META_BOLD if kind == 'bold' else F_META, text)

    def meta_flow(self, m, width):
        '''[(item, x, line, width)] for the meta row, wrapping onto new
        lines as needed and at each 'break'.'''
        out, line, x = [], 0, 0.0
        for item in self._meta_items():
            if item[0] == 'break':
                if x:
                    line, x = line + 1, 0.0
                continue
            w = self._item_width(m, item)
            if x and x + w > width:
                line, x = line + 1, 0.0
            out.append((item, x, line, w))
            x += w + 8.0
        return out

    def _meta_height(self, m, width):
        flow = self.meta_flow(m, width)
        return (max(line for _i, _x, line, _w in flow) + 1) * 16.0 if flow else 0.0

    def _allergen_lines(self):
        '''(contains, facility line, free-of line); the last two may be ''.'''
        d = self.data
        facility = d.get('facility') or []
        main = ' · '.join(d['allergens']) if d['allergens'] else 'None of the tracked allergens'
        fac = ('Made in a facility that also handles: ' + ', '.join(facility)) if facility else ''
        free = ''
        if d['free_of'] and (d['allergens'] or facility):
            free = 'Free of: ' + ', '.join(d['free_of'])
        return main, fac, free

    def _allergen_box_height(self, m, width):
        main, fac, free = self._allergen_lines()
        label_w = m.text_width(F_LABEL, 'CONTAINS') + 10.0
        h = m.wrapped_height(F_ALLERGENS, main, width - 18.0 - label_w)
        if fac:
            h += 3.0 + m.wrapped_height(F_FACILITY, fac, width - 18.0)
        if free:
            h += 3.0 + m.wrapped_height(F_SMALL, free, width - 18.0)
        return h + 14.0

    def _paginate(self, m):
        pages, start = [], 0
        top = self.body_top_first(m) + self.header_height(m)
        rows = self.row_heights
        while True:
            y, end = top, start
            while end < len(rows) and y + rows[end] <= self.body_bottom():
                y += rows[end]
                end += 1
            if end == start and end < len(rows):
                end += 1   # a row taller than a page still gets printed
            pages.append((start, end))
            if end >= len(rows):
                return pages
            start = end
            top = self.body_top_more(m) + self.header_height(m)


def _fitted_layout(data, page_w, page_h, disclaimer):
    '''The first FIT_STEPS layout whose table fits one page; the normal
    one when none does (the table then continues on page 2).'''
    first = None
    for fit in FIT_STEPS:
        layout = RecipePageLayout(data, page_w, page_h, disclaimer, fit)
        if len(layout.pages) == 1:
            return layout
        first = first or layout
    return first


class RecipePagePainter:
    '''Paint one recipe's pages. `new_page()` is called between pages.'''

    def __init__(self, painter, data, branding, page_w, page_h, logo=None, printed=None):
        self.p = painter
        self.g = _Page(painter)
        self.data = data
        self.brand = branding
        self.accent = QColor(branding.get('accent') or '#082c00')
        self.logo = logo
        self.printed = printed or date.today()
        self.layout = _fitted_layout(data, page_w, page_h, branding.get('disclaimer') or '')
        self.page_w, self.page_h = page_w, page_h
        self.side_pages = self._plan_side()
        while len(self.layout.pages) < len(self.side_pages):
            end = len(data['rows'])
            self.layout.pages.append((end, end))   # a page just for side panels

    @property
    def page_count(self):
        return len(self.layout.pages)

    def paint(self, new_page):
        for i, (start, end) in enumerate(self.layout.pages):
            if i:
                new_page()
            self._brand_bar()
            if i == 0:
                self._title_block()
                top = self.layout.body_top_first(self.g)
            else:
                top = self.layout.body_top_more(self.g) - 10.0 - self.g.line_height(F_META_BOLD)
                self.g.text(MARGIN_X, top, self.layout.content_w, 20, F_META_BOLD, self.accent,
                            f"{self.data['name']} (continued)")
                top = self.layout.body_top_more(self.g)
            if i < len(self.side_pages):
                self._side_column(top, self.side_pages[i])
            if i == 0 or start < end:
                self._table(top, start, end, continued=i > 0)
            self._disclaimer()
            self._footer(i + 1)

    # --- sections ----------------------------------------------------------

    def _brand_bar(self):
        g, x, y = self.g, MARGIN_X, MARGIN_TOP
        w = self.layout.content_w
        if self.logo is not None:
            self.logo(self.p, QRectF(x * _U, y * _U, 220 * _U, 20 * _U))
        right = (self.brand.get('header') or '').upper()
        if right:
            g.text(x, y, w, 10, F_LABEL, self.accent, right, Qt.AlignRight | Qt.AlignTop)
        g.text(x, y + 10.0, w, 10, F_SMALL, MUTED,
               f"Printed {self.printed.strftime('%b')} {self.printed.day}, {self.printed.year}",
               Qt.AlignRight | Qt.AlignTop)
        g.line(x, y + 24.0, x + w, y + 24.0, self.accent, 2.0)

    def _title_block(self):
        g, L = self.g, self.layout
        x = MARGIN_X
        y = MARGIN_TOP + 24.0 + 12.0
        left_w = L.table_w        # same width as the ingredients table
        self._wedge(x + L.content_w - WEDGE, y)
        y += g.wrapped(x, y, left_w, F_TITLE, self.accent, self.data['name']) + 5.0
        # format / tags / diets, then yield and serving on their own line
        top, line_y = y, y
        for item, cx, line, w in L.meta_flow(g, left_w):
            line_y = top + line * 16.0
            kind, text = item[0], item[1]
            if kind in ('pill', 'tag', 'diet'):
                color = QColor(item[2])
                if kind == 'pill':
                    fill, border, fg = _mix(color, '#ffffff', 0.88), color, color
                elif kind == 'diet':
                    fill, border, fg = DIET_BG, DIET_BG, DIET_FG
                else:
                    fill, border, fg = QColor('#f5f5f4'), QColor('#d6d3d1'), INK
                g.rounded(x + cx, line_y + 1, w, 13.0, 6.5, fill, border, 0.8)
                g.text(x + cx, line_y + 1, w, 13.0, F_PILL, fg, text, Qt.AlignCenter)
            else:
                font = F_META_BOLD if kind == 'bold' else F_META
                g.text(x + cx, line_y + 1, w + 2, 14, font, INK if kind == 'bold' else MUTED, text,
                       Qt.AlignLeft | Qt.AlignVCenter)
        y = top + L._meta_height(g, left_w) + 10.0
        self._allergen_box(x, y, left_w)

    def _wedge(self, x, y):
        '''The recipe's photo, or its wedge when it has none.'''
        d = self.data
        if d.get('photo'):
            img = photo_image(d['photo'], 480)
            if not img.isNull():
                self.g.image(x, y, WEDGE, WEDGE, img)
                return
        shape = d['format']['shape'] if d['format'] else None
        color = d['format']['color'] if d['format'] else None
        try:
            png = render_recipe(d['wedge'], size=480, shape=shape, shape_color=color)
        except Exception as exc:   # a broken photo shouldn't stop printing
            print(f'wedge render failed: {exc}')
            png = None
        if png:
            img = QImage()
            img.loadFromData(png)
            if not img.isNull():
                self.g.image(x, y, WEDGE, WEDGE, img)

    def _allergen_box(self, x, y, w):
        g, L = self.g, self.layout
        main, fac, free = L._allergen_lines()
        has = bool(self.data['allergens'])
        h = L._allergen_box_height(g, w)
        g.rounded(x, y, w, h, 6.0, DANGER_BG if has else QColor('#f5f5f4'),
                  DANGER if has else QColor('#d6d3d1'), 1.5 if has else 1.0)
        label_w = g.text_width(F_LABEL, 'CONTAINS') + 10.0
        g.text(x + 9, y + 9.5, label_w, 10, F_LABEL, DANGER if has else MUTED, 'CONTAINS')
        cy = y + 6.0 + g.wrapped(x + 9 + label_w, y + 6.0, w - 18.0 - label_w, F_ALLERGENS,
                                 INK if has else MUTED, main)
        if fac:
            cy += 3.0 + g.wrapped(x + 9, cy + 3.0, w - 18.0, F_FACILITY, FACILITY, fac)
        if free:
            g.wrapped(x + 9, cy + 3.0, w - 18.0, F_SMALL, MUTED, free)

    def _table(self, top, start, end, continued=False):
        g, L = self.g, self.layout
        x0 = MARGIN_X
        g.text(x0, top, L.table_w, 12, F_SECTION, self.accent, 'INGREDIENTS')
        y = top + g.line_height(F_SECTION) + 6.0
        cx = x0
        for key, head, _w in L.columns:
            w = L.widths[key]
            align = Qt.AlignRight if key == 'n' else Qt.AlignLeft
            g.text(cx + _CELL_PAD, y, w - 2 * _CELL_PAD, 10, F_HEAD, MUTED, head.upper(), align | Qt.AlignTop)
            cx += w
        y += g.line_height(F_HEAD) + 3.0
        g.line(x0, y, x0 + L.table_w, y, self.accent, 1.2)
        y += 4.0
        for i in range(start, end):
            row, h = self.data['rows'][i], L.row_heights[i]
            self._row(x0, y, h, i + 1, row)
            y += h
            g.line(x0, y, x0 + L.table_w, y, RULE, 0.75)
        if not self.data['rows']:
            g.text(x0 + _CELL_PAD, y + 4, L.table_w, 14, F_META, MUTED, 'No components yet.')

    def _row(self, x, y, h, number, row):
        g, W = self.g, self.layout.widths
        cy = y + self.layout.row_pad
        mid = Qt.AlignLeft | Qt.AlignTop
        g.text(x + _CELL_PAD, cy, W['n'] - 2 * _CELL_PAD, 12, F_TOOL_PLAIN, MUTED, str(number),
               Qt.AlignRight | Qt.AlignTop)
        x += W['n']
        name_w = W['name'] - 2 * _CELL_PAD
        g.wrapped(x + _CELL_PAD, cy, name_w, F_NAME, INK, row['name'])
        tag = 'format' if row['from_template'] else ('sub-recipe' if row['type'] == 'recipe' else '')
        if tag:
            used = g.text_width(F_NAME, row['name'])
            if used + 6 + g.text_width(F_SMALL, tag) <= name_w:
                g.text(x + _CELL_PAD + used + 5, cy + 1.2, 60, 12, F_SMALL, MUTED, tag, mid)
        x += W['name']
        if 'amount' in W:
            g.text(x + _CELL_PAD, cy, W['amount'] - 2 * _CELL_PAD, 14, F_AMOUNT, INK, row['amount'], mid)
            x += W['amount']
        use = row['tool'] if 'tool' in W else None
        if use:
            tx = x + _CELL_PAD
            if use.tool is not None and use.tool.sized:
                g.dot(tx, cy + 2.0, 8.0, use.tool)
                tx += 11.0
                g.text(tx, cy, W['tool'] - (tx - x) - _CELL_PAD, 14, F_TOOL, INK, use.text, mid)
            else:
                g.text(tx, cy, W['tool'] - 2 * _CELL_PAD, 14, F_TOOL_PLAIN, MUTED, use.text, mid)
        x += W.get('tool', 0.0)
        ay = cy + 0.8
        if row['allergens']:
            ay += g.wrapped(x + _CELL_PAD, ay, W['allergens'] - 2 * _CELL_PAD, F_CELL_ALG, DANGER, row['allergens'])
        if row.get('facility'):
            g.wrapped(x + _CELL_PAD, ay, W['allergens'] - 2 * _CELL_PAD, F_CELL_ALG, FACILITY,
                      'facility: ' + row['facility'])
        if row.get('statement'):
            L = self.layout
            sh = L.statement_heights[number - 1]
            sx = MARGIN_X + W['n'] + _CELL_PAD
            sy = y + h - sh
            doc = _statement_doc(row['statement'], L.statement_w, L.statement_pt)
            self.p.save()
            self.p.translate(sx * _U, sy * _U)
            doc.drawContents(self.p)
            self.p.restore()

    def _side_items(self):
        '''The side column's panels in order, as (method, kwargs).'''
        d = self.data
        serving = f"1 {d['unit']}".strip()
        if d['weight']:
            serving += f" ({float(d['weight']):.0f} g)"
        items = [(self._nutrition, {'n': d['nutrition'], 'serving': serving,
                                    'subtitle': d.get('nutrition_title')})]
        for card in d.get('cards') or []:
            items.append((self._nutrition, {'n': card['nutrition'], 'serving': card['serving'],
                                            'subtitle': card['name'], 'small': True}))
        if d['tools_used']:
            items.append((self._scoop_key, {}))
        return items

    def _plan_side(self):
        '''Side panels per page: [[(method, kwargs), …], …]. Panels that
        don't fit beside page 1's table continue beside page 2's.'''
        real, self.g = self.g, _Page(None)
        try:
            heights = [method(0.0, 0.0, SIDE_W, **kw) for method, kw in self._side_items()]
        finally:
            self.g = real
        L, m = self.layout, _Page(None)
        pages, current = [], []
        y = L.body_top_first(m)
        for item, h in zip(self._side_items(), heights):
            if current and y + h > L.body_bottom():
                pages.append(current)
                current, y = [], L.body_top_more(m)
            current.append(item)
            y += h + 10.0
        pages.append(current)
        return pages

    def _side_column(self, top, items):
        x = MARGIN_X + self.layout.content_w - SIDE_W
        y = top
        for method, kw in items:
            y = method(x, y, SIDE_W, **kw) + 10.0

    def _nutrition(self, x, y, w, n, serving, subtitle=None, small=False):
        '''An FDA-style panel; returns its bottom edge.'''
        g = self.g
        pad = 5.0
        inner = w - 2 * pad
        f_title = _font(12.0 if small else 15.0, QFont.Black, 'Arial')
        f_sub = _font(7.5, QFont.Bold, 'Arial')
        f_row = _font(7.8, QFont.Normal, 'Arial')
        f_row_b = _font(7.8, QFont.Bold, 'Arial')
        f_cal = _font(11.0, QFont.Bold, 'Arial')
        f_cal_v = _font(14.0 if small else 17.0, QFont.Black, 'Arial')
        top = y
        cy = y + pad
        g.text(x + pad, cy, inner, 20, f_title, BLACK, 'Nutrition Facts')
        cy += g.line_height(f_title)
        if subtitle:
            cy += g.wrapped(x + pad, cy, inner, f_sub, BLACK, subtitle) + 1.0
        g.text(x + pad, cy, inner, 12, f_row_b, BLACK, 'Serving size')
        g.text(x + pad, cy, inner, 12, f_row_b, BLACK, serving, Qt.AlignRight | Qt.AlignTop)
        cy += g.line_height(f_row_b) + 2.0
        g.line(x + pad, cy + 3, x + w - pad, cy + 3, BLACK, 6.0)
        cy += 7.0
        cal_h = 18.0 if small else 22.0
        g.text(x + pad, cy, inner, cal_h, f_cal, BLACK, 'Calories', Qt.AlignLeft | Qt.AlignBottom)
        g.text(x + pad, cy, inner, cal_h, f_cal_v, BLACK, str(recipe_print.label_calories(n['Calories'])),
               Qt.AlignRight | Qt.AlignBottom)
        cy += cal_h + 1.0
        g.line(x + pad, cy + 1.5, x + w - pad, cy + 1.5, BLACK, 3.0)
        cy += 3.5
        for i, (label, key, unit, indent, bold) in enumerate(_NUTRIENT_ROWS):
            ix = x + pad + (9.0 if indent else 0)
            if bold:
                lw = g.text_width(f_row_b, label + ' ')
                g.text(ix, cy + 1.5, inner, 11, f_row_b, BLACK, label)
                g.text(ix + lw, cy + 1.5, inner, 11, f_row, BLACK, f'{recipe_print.label_amount(key, n[key])}{unit}')
            else:
                g.text(ix, cy + 1.5, inner, 11, f_row, BLACK, f'{label} {recipe_print.label_amount(key, n[key])}{unit}')
            cy += g.line_height(f_row) + 3.0
            last = i == len(_NUTRIENT_ROWS) - 1
            g.line(x + pad, cy + (3 if last else 0), x + w - pad, cy + (3 if last else 0), BLACK,
                   6.0 if last else 0.6)
        cy += 6.0 + pad
        g.rounded(x, top, w, cy - top, 0, None, BLACK, 1.1)
        return cy

    def _scoop_key(self, x, y, w):
        g = self.g
        tools = self.data['tools_used']
        line = 13.0
        h = 8.0 + g.line_height(F_SECTION) + 4.0 + line * len(tools) + 6.0
        g.rounded(x, y, w, h, 6.0, _mix(self.accent, '#ffffff', 0.93), RULE, 0.8)
        g.text(x + 8, y + 7, w - 16, 12, F_SECTION, self.accent, 'SCOOP KEY')
        cy = y + 8.0 + g.line_height(F_SECTION) + 4.0
        for tool in tools:
            g.dot(x + 8, cy + 2.0, 8.0, tool)
            g.text(x + 21, cy, w - 30, line, F_TOOL_PLAIN, INK, tool.name)
            g.text(x + 8, cy, w - 16, line, F_TOOL_PLAIN, MUTED,
                   f'{recipe_print.fraction_text(tool.size_floz)} fl oz', Qt.AlignRight | Qt.AlignTop)
            cy += line
        return y + h

    def _disclaimer(self):
        L = self.layout
        if L.disclaimer:
            self.g.wrapped(MARGIN_X, L.disclaimer_top(), L.content_w, F_DISCLAIMER, MUTED, L.disclaimer)

    def _footer(self, page_no):
        g = self.g
        y = self.layout.footer_top()
        w = self.layout.content_w
        g.line(MARGIN_X, y, MARGIN_X + w, y, RULE, 0.75)
        g.text(MARGIN_X, y + 4, w, 12, F_SMALL, MUTED, self.brand.get('footer') or '')
        right = f"{self.data['name']} · Page {page_no} of {self.page_count}"
        g.text(MARGIN_X, y + 4, w, 12, F_SMALL, MUTED, right, Qt.AlignRight | Qt.AlignTop)


# --- logo ----------------------------------------------------------------------

def logo_drawer(logo):
    '''A callable(painter, rect) that draws the logo left-aligned in
    `rect`, keeping its aspect ratio, or None if there's none or it
    can't be read. `logo` is (image bytes, extension) as stored in the
    library.'''
    if not logo or not logo[0]:
        return None
    data, ext = logo
    if (ext or '').lower() == '.svg':
        from PySide6.QtCore import QByteArray
        from PySide6.QtSvg import QSvgRenderer
        renderer = QSvgRenderer(QByteArray(data))
        if not renderer.isValid():
            return None
        size = renderer.defaultSize()
        view = renderer.viewBoxF()
        aspect = (view.width() / view.height()) if view.height() else (size.width() / max(1, size.height()))

        def draw(painter, rect):
            w = min(rect.width(), rect.height() * aspect)
            renderer.render(painter, QRectF(rect.x(), rect.y(), w, w / aspect))
        return draw
    img = QImage.fromData(data)
    if img.isNull():
        return None
    aspect = img.width() / max(1, img.height())

    def draw(painter, rect):
        w = min(rect.width(), rect.height() * aspect)
        painter.drawImage(QRectF(rect.x(), rect.y(), w, w / aspect), img)
    return draw


# --- entry point -----------------------------------------------------------

def paint_recipes(printer_or_device, recipes, branding, new_page=None, printed=None):
    '''Paint each recipe's pages onto a QPrinter (or QPdfWriter).
    `recipes` is a list of db.recipe_print_data() dicts.'''
    device = printer_or_device
    layout = device.pageLayout()
    full = layout.fullRectPoints()
    page_w, page_h = float(full.width()), float(full.height())
    painter = QPainter(device)
    try:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        # Map points to device pixels from the page's top-left corner,
        # then tenths of a point.
        paint_rect = layout.paintRectPixels(device.resolution())
        scale = device.resolution() / 72.0
        painter.translate(-paint_rect.x(), -paint_rect.y())
        painter.scale(scale / _U, scale / _U)
        logo = logo_drawer(branding.get('logo'))
        advance = new_page or device.newPage
        for i, data in enumerate(recipes):
            if i:
                advance()
            RecipePagePainter(painter, data, branding, page_w, page_h, logo, printed).paint(advance)
    finally:
        painter.end()


def render_images(recipes, branding, dpi=110, page_size=(612.0, 792.0), printed=None):
    '''Each page as a QImage (Letter by default): for previews and tests.'''
    page_w, page_h = page_size
    scale = dpi / 72.0
    images = []
    painter = QPainter()

    def start():
        img = QImage(round(page_w * scale), round(page_h * scale), QImage.Format_ARGB32)
        img.fill(QColor('#ffffff'))
        images.append(img)
        painter.begin(img)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.scale(scale / _U, scale / _U)

    def next_page():
        painter.end()
        start()

    start()
    try:
        logo = logo_drawer(branding.get('logo'))
        for i, data in enumerate(recipes):
            if i:
                next_page()
            RecipePagePainter(painter, data, branding, page_w, page_h, logo, printed).paint(next_page)
    finally:
        painter.end()
    return images


def page_layout_for(printer):
    '''Pages are laid out on the full sheet; margins are ours.'''
    printer.setFullPage(True)
    printer.setPageOrientation(QPageLayout.Portrait)
