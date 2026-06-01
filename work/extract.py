#!/usr/bin/env python3
"""Extract structured content from the dissertation main body for translation.

- Prose  -> German text (for translation)
- Headings -> level + number + German title
- Equations -> cropped image (faithful, language-neutral)
- Figures / Tables -> cropped image (region = union of vector/raster graphics) + caption
Output: work/content.json and cropped PNGs in work/img/.
"""
import fitz, json, re, os, statistics
from collections import Counter

PDF = "8baf8973-6b12-4a00-afcc-a3ef112ebfcf.pdf"
IMGDIR = "work/img"
os.makedirs(IMGDIR, exist_ok=True)
doc = fitz.open(PDF)

BODY_START, BODY_END = 38, 167
CH_DIVIDERS = {38: 1, 46: 2, 62: 3, 106: 4, 156: 5, 162: 6}
HEADER_Y, FOOTER_Y = 65, 540
ZOOM = fitz.Matrix(4, 4)
COL_X0, COL_X1 = 44.0, 378.0

CAPTION_RE = re.compile(r'^(Abbildung|Bild|Tabelle)\s+(\d+\.\d+)\s*[:.]', re.S)
EQNUM_RE = re.compile(r'^\s*\(\d+\.\d+[a-z]?\)\s*$')
CONT_WORDS = ('und', 'oder', 'bzw', 'sowie', 'beziehungsweise')

def ltext(line):
    return ''.join(s['text'] for s in line['spans'])

def math_ratio(line):
    math = tot = 0
    for s in line['spans']:
        n = len(s['text'].replace(' ', ''))
        tot += n
        f = s['font']
        if f[:2] == 'CM' or f[:4] in ('MSAM', 'MSBM', 'LASY') or f[:5] == 'LCMSS':
            math += n
    return (math / tot) if tot else 0.0

def dehyph(parts):
    out = ''
    for i, ln in enumerate(parts):
        ln = ln.strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif out[-1] == '-' and out[-2:] != '--':
            nxt = ln.split(' ', 1)[0].rstrip('.,;:')
            if nxt.lower() in CONT_WORDS:
                out = out + ' ' + ln          # real elision hyphen ("Vor- und")
            else:
                out = out[:-1] + ln           # soft hyphen
        else:
            out = out + ' ' + ln
    return out.strip()

def render(idx, rect, name):
    rect = rect & doc[idx].rect
    pix = doc[idx].get_pixmap(matrix=ZOOM, clip=rect)
    pix.save(os.path.join(IMGDIR, name))

elements = []

for idx in range(BODY_START, BODY_END + 1):
    page = doc[idx]
    d = page.get_text('dict')

    # ----- chapter divider page -----
    if idx in CH_DIVIDERS:
        title_parts, prose = [], []
        for b in d['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                y0 = line['bbox'][1]
                t = ltext(line).strip()
                if not t:
                    continue
                bold = any('Bold' in s['font'] for s in line['spans'])
                mx = max((s['size'] for s in line['spans']), default=0)
                if bold and mx > 15:
                    title_parts.append(t)
                elif HEADER_Y < y0 < FOOTER_Y and not bold:
                    prose.append((y0, t))
        tparts = [p for p in title_parts if not re.fullmatch(r'\d+', p)]
        elements.append({'type': 'heading', 'level': 1,
                         'num': str(CH_DIVIDERS[idx]),
                         'text': ' '.join(tparts).strip(), 'page': idx})
        if prose:
            prose.sort()
            txt = dehyph([t for _, t in prose])
            if len(txt) > 40:
                elements.append({'type': 'para', 'text': txt, 'page': idx,
                                 'bbox': [COL_X0, prose[0][0], COL_X1, prose[-1][0]]})
        continue

    # ----- normal page: classify lines -----
    items = []   # (y0, kind, dict)
    for b in d['blocks']:
        if b['type'] != 0:
            continue
        for line in b['lines']:
            bb = line['bbox']
            if bb[1] < HEADER_Y or bb[1] > FOOTER_Y:
                continue
            t = ltext(line)
            if not t.strip():
                continue
            sizes = [s['size'] for s in line['spans'] if s['text'].strip()]
            mx = max(sizes) if sizes else 0
            bold = any('Bold' in s['font'] for s in line['spans'] if s['text'].strip())
            mr = math_ratio(line)
            if bold and mx >= 11.5:
                kind = 'heading'
            elif EQNUM_RE.match(t) or mr > 0.5:
                kind = 'math'
            else:
                kind = 'prose'
            items.append((bb[1], kind, {'text': t, 'bbox': list(bb), 'size': mx}))
    items.sort(key=lambda z: z[0])

    # page graphics (drawings + raster) for figure/table region detection
    graphics = []
    for dr in page.get_drawings():
        graphics.append(tuple(dr['rect']))
    for im in page.get_image_info():
        bb = im['bbox']
        if bb[1] > 61:                       # skip the running-header rule at y~58
            graphics.append(tuple(bb))

    page_elems = []
    region_top = HEADER_Y                    # last heading/equation/caption bottom
    i, N = 0, len(items)
    while i < N:
        y0, kind, pl = items[i]
        if kind == 'math':
            j = i
            ymin, ymax = pl['bbox'][1], pl['bbox'][3]
            while j + 1 < N:
                nk = items[j+1][1]
                nb = items[j+1][2]['bbox']
                nt = items[j+1][2]['text'].strip()
                # absorb math lines (small gap) and short inline operators
                # (var, cos, sin, max, exp ...) that overlap the cluster vertically
                if (nk == 'math' and nb[1] <= ymax + 9) or \
                   (nk == 'prose' and len(nt) <= 5 and nb[1] <= ymax - 1):
                    ymin, ymax = min(ymin, nb[1]), max(ymax, nb[3])
                    j += 1
                else:
                    break
            eqname = f"eq_p{idx}_{int(ymin)}.png"
            render(idx, fitz.Rect(COL_X0, ymin - 3, COL_X1, ymax + 3), eqname)
            page_elems.append({'type': 'equation', 'page': idx,
                               'img': f"img/{eqname}", 'y': ymin})
            region_top = ymax
            i = j + 1
            continue
        if kind == 'heading':
            j = i
            parts, sz = [pl['text'].strip()], pl['size']
            ybot = pl['bbox'][3]
            while j + 1 < N and items[j+1][1] == 'heading' and abs(items[j+1][2]['size'] - sz) < 1.5:
                parts.append(items[j+1][2]['text'].strip())
                ybot = items[j+1][2]['bbox'][3]
                j += 1
            full = ' '.join(parts)
            m = re.match(r'^(\d+(?:\.\d+)+)\s+(.*)$', full)
            if m:
                num, title, level = m.group(1), m.group(2), m.group(1).count('.') + 1
            else:
                num, title, level = '', full, 2
            page_elems.append({'type': 'heading', 'level': level, 'num': num,
                               'text': title, 'page': idx, 'y': y0})
            region_top = ybot
            i = j + 1
            continue
        # prose run -> paragraphs by vertical gap
        j = i
        plines = [pl]
        while j + 1 < N and items[j+1][1] == 'prose':
            plines.append(items[j+1][2])
            j += 1
        gaps = [plines[k]['bbox'][1] - plines[k-1]['bbox'][3] for k in range(1, len(plines))]
        _g = [g for g in gaps if g > -5]
        med = statistics.median(_g) if _g else 0
        paras = [[plines[0]]]
        for k in range(1, len(plines)):
            gap = plines[k]['bbox'][1] - plines[k-1]['bbox'][3]
            if med and gap > med + 2.2 and gap > 2.0:
                paras.append([plines[k]])
            else:
                paras[-1].append(plines[k])
        for para in paras:
            txt = dehyph([p['text'] for p in para])
            xs0 = min(p['bbox'][0] for p in para); ys0 = min(p['bbox'][1] for p in para)
            xs1 = max(p['bbox'][2] for p in para); ys1 = max(p['bbox'][3] for p in para)
            cap = CAPTION_RE.match(txt)
            if cap:
                # --- build figure/table region from graphics between region_top and caption ---
                ctop = ys0
                gfx = [g for g in graphics if (g[1] + g[3]) / 2 > region_top - 1
                       and (g[1] + g[3]) / 2 < ctop - 1
                       and g[2] > COL_X0 - 5 and g[0] < COL_X1 + 5]
                kindf = 'figure' if cap.group(1) in ('Abbildung', 'Bild') else 'table'
                if gfx:
                    gt = min(g[1] for g in gfx)
                    gx0 = min(g[0] for g in gfx); gx1 = max(g[2] for g in gfx)
                    # include figure-internal text labels (between graphics top and caption)
                    for it in items:
                        ib = it[2]['bbox']
                        cy = (ib[1] + ib[3]) / 2
                        if gt - 4 < cy < ctop - 1 and it[1] != 'heading':
                            gx0 = min(gx0, ib[0]); gx1 = max(gx1, ib[2])
                    rect = fitz.Rect(max(COL_X0, gx0 - 6), gt - 4,
                                     min(COL_X1, gx1 + 6), ctop - 2)
                else:
                    rect = fitz.Rect(COL_X0, region_top + 1, COL_X1, ctop - 2)
                name = f"{kindf}_{cap.group(2).replace('.', '_')}.png"
                img = None
                if rect.height > 8 and rect.width > 8:
                    render(idx, rect, name)
                    img = f"img/{name}"
                page_elems.append({'type': kindf, 'num': cap.group(2),
                                   'caption': txt[cap.end():].strip(), 'img': img,
                                   'page': idx, 'y': ctop,
                                   'figtop': (rect.y0 if img else region_top)})
                region_top = ys1
            else:
                page_elems.append({'type': 'para', 'text': txt, 'page': idx,
                                   'y': ys0, 'bbox': [xs0, ys0, xs1, ys1]})
        i = j + 1

    # suppress paragraphs that fall inside a figure/table region on this page
    figrects = [(e['figtop'], e['y']) for e in page_elems if e['type'] in ('figure', 'table') and e.get('img')]
    keep = []
    for e in page_elems:
        if e['type'] == 'para':
            cy = (e['bbox'][1] + e['bbox'][3]) / 2
            if any(t <= cy <= b for t, b in figrects):
                continue
        e.pop('figtop', None)
        keep.append(e)
    keep.sort(key=lambda z: z['y'])
    elements.extend(keep)

# ----- merge cross-page / over-split continuation paragraphs -----
merged = []
for e in elements:
    if e['type'] == 'para' and merged and merged[-1]['type'] == 'para':
        prev = merged[-1]['text']
        cur = e['text']
        ends_sentence = re.search(r'[.!?:;][)"»”\']?$', prev)
        is_bullet = cur[:1] in ('•', '–', '*') or cur.startswith('- ')
        if not ends_sentence and not is_bullet and cur[:1] not in ('•',):
            if prev.endswith('-') and prev[-2:] != '--':
                nxt = cur.split(' ', 1)[0]
                if nxt.lower().rstrip('.,;:') in CONT_WORDS:
                    merged[-1]['text'] = prev + ' ' + cur
                else:
                    merged[-1]['text'] = prev[:-1] + cur
            else:
                merged[-1]['text'] = prev + ' ' + cur
            continue
    merged.append(e)

# strip helper keys
for e in merged:
    e.pop('bbox', None)
    e.pop('y', None)

with open('work/content.json', 'w') as f:
    json.dump(merged, f, ensure_ascii=False, indent=1)

c = Counter(e['type'] for e in merged)
nchars = sum(len(e.get('text', '')) + len(e.get('caption', '')) for e in merged)
print('Element counts:', dict(c))
print('Total elements:', len(merged), '| translatable chars:', nchars)
