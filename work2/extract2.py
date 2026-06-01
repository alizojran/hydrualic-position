#!/usr/bin/env python3
"""Extract structured content from the two IEEE radar papers (two-column layout).

Output: work2/content_<doc>.json and cropped PNGs in work2/img_<doc>/.
Element types: title, authors, abstract, indexterms, heading, para,
               equation(img), figure(img+caption), table(img+caption),
               note(verbatim), references(verbatim list).
"""
import fitz, json, re, os, statistics, glob
from collections import Counter

ZOOM = fitz.Matrix(4, 4)

DOCS = {
    'journal': dict(
        pdf='High-Accuracy_Range_Detection_Radar_Sensor_for_Hydraulic_Cylinders.pdf',
        mid=306, cap_max=9.2, header_y=46, footer_y=756,
        cols={'L': (47, 301), 'R': (311, 564)},
    ),
    'conf': dict(
        pdf='C2012_Ayhan_FMCWradarinoil-filledwaveguidesforrangedetectioninhydrauliccylinders.pdf',
        mid=300, cap_max=9.6, header_y=46, footer_y=800,
        cols={'L': (36, 291), 'R': (306, 561)},
    ),
}

MATH_FONTS = ('MTSYN', 'RBLMI', 'RMTMIB', 'BLEX', 'MSAM', 'MSBM', 'CMSY',
              'CMMI', 'CMEX', 'MTMI', 'MT-Extra', 'SymbolMT', 'Symbol')
EQNUM_RE = re.compile(r'^\(\d+[a-z]?\)$')
CAP_RE = re.compile(r'^(Fig\.?|Figure|TABLE|Table)\s*\.?\s*([IVX]+|\d+)\b')
SEC_RE = re.compile(r'^([IVXLM]+)\.\s+(.+)$')
SUB_RE = re.compile(r'^([A-Z])\.\s+([A-Z].+)$')
REF_RE = re.compile(r'^(REFERENCES|R\s*EFERENCES)\b', re.I)
ACK_RE = re.compile(r'^(ACKNOWLEDGMENT|ACKNOWLEDGEMENT|A\s*CKNOWLEDGMENT)', re.I)
CONT_WORDS = ('and', 'or', 'of', 'the', 'to', 'in', 'for', 'with')


def upper_ratio(t):
    al = [c for c in t if c.isalpha()]
    return sum(c.isupper() for c in al) / max(1, len(al))


def lines_of(page, cfg):
    out = []
    for b in page.get_text('dict')['blocks']:
        if b['type'] != 0:
            continue
        for ln in b['lines']:
            spans = [s for s in ln['spans'] if s['text'].strip()]
            if not spans:
                continue
            text = ''.join(s['text'] for s in ln['spans'])
            bb = ln['bbox']
            if bb[1] < cfg['header_y'] or bb[1] > cfg['footer_y']:
                continue
            if re.fullmatch(r'\d{1,4}', text.strip()):
                continue
            fonts = set(s['font'] for s in spans)
            mathchars = sum(len(s['text'].replace(' ', '')) for s in spans
                            if any(f in s['font'] for f in MATH_FONTS))
            allchars = sum(len(s['text'].replace(' ', '')) for s in spans)
            out.append(dict(
                y0=bb[1], y1=bb[3], x0=bb[0], x1=bb[2],
                size=max(s['size'] for s in spans), text=text, fonts=fonts,
                bold=any('Bold' in f for f in fonts),
                ital=all('Italic' in s['font'] for s in spans),
                mathratio=(mathchars / allchars) if allchars else 0.0,
                kind=None,
            ))
    return out


def colof(ln, cfg):
    return 'L' if (ln['x0'] + ln['x1']) / 2 < cfg['mid'] else 'R'


def is_full(ln, cfg):
    return ln['x0'] < cfg['mid'] - 30 and ln['x1'] > cfg['mid'] + 30


def order_lines(lines, cfg):
    fulls = sorted([l for l in lines if is_full(l, cfg)], key=lambda l: l['y0'])
    full_yc = [(f['y0'] + f['y1']) / 2 for f in fulls]
    band = lambda l: sum(1 for yc in full_yc if yc < l['y0'])
    keyed = []
    for l in lines:
        if is_full(l, cfg):
            keyed.append((band(l), 1, 0, l['y0'], l))
        else:
            keyed.append((band(l), 0, 0 if colof(l, cfg) == 'L' else 1, l['y0'], l))
    keyed.sort(key=lambda z: z[:4])
    return [k[4] for k in keyed]


def dehyph(parts):
    out = ''
    for ln in parts:
        ln = ln.strip()
        if not ln:
            continue
        if not out:
            out = ln
        elif out.endswith('-') and not out.endswith('--'):
            nxt = ln.split(' ', 1)[0].rstrip('.,;:').lower()
            out = (out + ' ' + ln) if nxt in CONT_WORDS else (out[:-1] + ln)
        else:
            out = out + ' ' + ln
    return out.strip()


def compute_eqbands(lines, cfg):
    bands = []
    for l in lines:
        if not EQNUM_RE.match(l['text'].strip()):
            continue
        col = colof(l, cfg)
        cx0, cx1 = cfg['cols'][col]
        if l['x1'] < cx1 - 25:
            continue
        ymin, ymax = l['y0'], l['y1']
        for m in lines:
            if colof(m, cfg) != col or m is l:
                continue
            myc = (m['y0'] + m['y1']) / 2
            indented = m['x0'] > cx0 + 14 and m['x1'] < cx1 - 1
            if l['y0'] - 11 < myc < l['y1'] + 11 and (indented or m['mathratio'] > 0.3
                                                      or EQNUM_RE.match(m['text'].strip())):
                ymin, ymax = min(ymin, m['y0']), max(ymax, m['y1'])
        bands.append((col, ymin, ymax))
    return bands


def classify(lines, eqbands, cfg):
    def in_eqband(l):
        col = colof(l, cfg)
        yc = (l['y0'] + l['y1']) / 2
        return any(c == col and a - 1 <= yc <= b + 1 for c, a, b in eqbands)
    for l in lines:
        t = l['text'].strip()
        if in_eqband(l):
            l['kind'] = 'math'
        elif REF_RE.match(t) and len(t) < 16:
            l['kind'] = 'refstart'
        elif ACK_RE.match(t) and len(t) < 22:
            l['kind'] = 'ack'
        elif CAP_RE.match(t) and l['size'] <= cfg['cap_max']:
            l['kind'] = 'cap'
        elif SEC_RE.match(t) and l['size'] >= 9.5 and not l['bold'] and upper_ratio(t) >= 0.6:
            l['kind'] = 'sec'
        elif SUB_RE.match(t) and l['size'] <= 11.5 and not l['bold'] and len(t) < 70 \
                and not t.rstrip().endswith('.'):
            words = SUB_RE.match(t).group(2).split()
            titlecase = words and sum(bool(w) and w[0].isupper() for w in words) >= 0.55 * len(words)
            l['kind'] = 'sub' if (l['ital'] or titlecase) else 'prose'
        else:
            l['kind'] = 'prose'


def front_matter(lines, cfg):
    """Extract title/authors/abstract/index-terms/footnote from page 0."""
    fm = []
    top = [l for l in lines if l['y0'] < 160]            # title sits at the very top
    maxsz = max(l['size'] for l in top)
    title = sorted([l for l in top if l['size'] >= maxsz - 1.5], key=lambda l: (l['y0'], l['x0']))
    for l in title:
        l['kind'] = 'fm'
    fm.append({'type': 'title', 'text': dehyph([l['text'] for l in title])})
    title_bot = max(l['y1'] for l in title)

    abs_start = next((l for l in sorted(lines, key=lambda l: l['y0'])
                      if re.match(r'^Abstract\b', l['text'].strip(), re.I)), None)
    abs_y = abs_start['y0'] if abs_start else 1e9

    authors = sorted([l for l in lines if l['kind'] != 'fm' and is_full(l, cfg)
                      and title_bot < l['y0'] < abs_y and l['size'] < maxsz - 1.5],
                     key=lambda l: (l['y0'], l['x0']))
    for l in authors:
        l['kind'] = 'fm'
    if authors:
        fm.append({'type': 'authors', 'text': '\n'.join(l['text'].strip() for l in authors)})

    if abs_start:
        col = colof(abs_start, cfg)
        ab, idx_start = [], None
        for l in sorted([x for x in lines if colof(x, cfg) == col and x['y0'] >= abs_start['y0'] - 1],
                        key=lambda x: x['y0']):
            if re.match(r'^Index\b', l['text'].strip(), re.I):
                idx_start = l
                break
            if l['kind'] in ('sec', 'sub', 'cap'):
                break
            ab.append(l)
            l['kind'] = 'fm'
        atext = re.sub(r'^Abstract\s*[—\-–:]*\s*', '', dehyph([x['text'] for x in ab]))
        fm.append({'type': 'abstract', 'text': atext})
        if idx_start:
            it = []
            for l in sorted([x for x in lines if colof(x, cfg) == col and x['y0'] >= idx_start['y0'] - 1],
                            key=lambda x: x['y0']):
                if l['kind'] == 'sec' or (it and l['y0'] - it[-1]['y1'] > 16):
                    break
                it.append(l)
                l['kind'] = 'fm'
            ittext = re.sub(r'^Index\s*Terms?\s*[—\-–:]*\s*', '', dehyph([x['text'] for x in it]), flags=re.I)
            fm.append({'type': 'indexterms', 'text': ittext})

    # journal footnote (manuscript / copyright), small font, lower region
    foot = sorted([l for l in lines if l['kind'] != 'fm' and l['size'] <= 8.4
                   and l['y0'] > 590], key=lambda l: l['y0'])
    if foot:
        for l in foot:
            l['kind'] = 'fm'
        fm.append({'type': 'note', 'text': dehyph([l['text'] for l in foot])})
    return fm


def fig_table_rects(lines, graphics, cfg):
    """Crop rects for every Fig/Table caption (pre-pass).

    Each graphics band is assigned to its nearest caption: a TABLE caption owns
    bands below it (table grid sits under its title); a FIGURE caption owns bands
    above it (image sits over its caption). This splits a table stacked against a
    figure while keeping multi-panel figures whole.
    """
    info = []
    for l in [x for x in lines if x['kind'] == 'cap']:
        m = CAP_RE.match(l['text'].strip())
        info.append(dict(line=l, is_tab=m.group(1).lower().startswith(('table', 'tab')),
                         col=colof(l, cfg), y0=l['y0'], y1=l['y1'], num=m.group(2)))
    rects = []
    for col in ('L', 'R'):
        cx0, cx1 = cfg['cols'][col]
        ccaps = [c for c in info if c['col'] == col]
        if not ccaps:
            continue
        gfx = sorted([g for g in graphics if cx0 - 6 < (g[0] + g[2]) / 2 < cx1 + 6],
                     key=lambda g: g[1])
        bands = []                                   # merge graphics with small vertical gaps
        for g in gfx:
            if bands and g[1] - bands[-1][3] <= 9:
                b = bands[-1]
                bands[-1] = (min(b[0], g[0]), b[1], max(b[2], g[2]), max(b[3], g[3]))
            else:
                bands.append((g[0], g[1], g[2], g[3]))
        owners = {id(c['line']): [] for c in ccaps}
        for b in bands:
            best = None
            for c in ccaps:
                if c['is_tab'] and b[1] >= c['y1'] - 2:
                    dst = b[1] - c['y1']
                elif (not c['is_tab']) and b[3] <= c['y0'] + 2:
                    dst = c['y0'] - b[3]
                else:
                    continue
                if best is None or dst < best[0]:
                    best = (dst, c)
            if best and best[0] < 400:
                owners[id(best[1]['line'])].append(b)
        for c in ccaps:
            bs = owners[id(c['line'])]
            if c['is_tab']:
                bottom = max([b[3] for b in bs], default=c['y1'] + 10)
                rect = fitz.Rect(cx0, c['y0'] - 2, cx1, bottom + 3)
            elif bs:
                gx0 = max(cx0, min(b[0] for b in bs) - 4)
                gx1 = min(cx1, max(b[2] for b in bs) + 4)
                rect = fitz.Rect(gx0, min(b[1] for b in bs) - 4, gx1, c['y0'] - 2)
            else:
                rect = fitz.Rect(cx0, c['y0'] - 40, cx1, c['y0'] - 2)
            rects.append(dict(num=c['num'], is_tab=c['is_tab'], col=col, rect=rect))
    return rects


def build(doc_key):
    cfg = DOCS[doc_key]
    imgdir = f'work2/img_{doc_key}'
    os.makedirs(imgdir, exist_ok=True)
    for old in glob.glob(os.path.join(imgdir, '*.png')):   # drop stale crops
        os.remove(old)
    d = fitz.open(cfg['pdf'])

    def render(pi, rect, name):
        rect = rect & d[pi].rect
        if rect.width < 6 or rect.height < 6:
            return None
        d[pi].get_pixmap(matrix=ZOOM, clip=rect).save(os.path.join(imgdir, name))
        return f'img_{doc_key}/{name}'

    elements, ref_buf, in_refs = [], [], False

    for pi in range(d.page_count):
        page = d[pi]
        lines = lines_of(page, cfg)
        if not lines:
            continue
        eqbands = compute_eqbands(lines, cfg)
        classify(lines, eqbands, cfg)

        if pi == 0:
            elements.extend(front_matter(lines, cfg))

        graphics = [tuple(dr['rect']) for dr in page.get_drawings()]
        graphics += [tuple(im['bbox']) for im in page.get_image_info()
                     if im['bbox'][1] > cfg['header_y']]
        rects = fig_table_rects(lines, graphics, cfg)

        # mark figure-internal text as 'infig' (suppress axis labels, legends, cells)
        for l in lines:
            if l['kind'] in ('cap', 'fm', 'math', 'sec', 'sub', 'ack', 'refstart'):
                continue
            c = ((l['x0'] + l['x1']) / 2, (l['y0'] + l['y1']) / 2)
            for r in rects:
                R = r['rect']
                # for figures the caption is below R; for tables the caption row stays
                if R.x0 - 2 <= c[0] <= R.x1 + 2 and R.y0 - 1 <= c[1] <= R.y1 + 1:
                    l['kind'] = 'infig'
                    break

        ordered = order_lines(lines, cfg)
        rect_by_num = {(r['is_tab'], r['num']): r for r in rects}
        i, N = 0, len(ordered)
        while i < N:
            l = ordered[i]
            col = colof(l, cfg)
            t = l['text'].strip()

            if in_refs:
                ref_buf.append(t)
                i += 1
                continue
            if l['kind'] in ('fm', 'infig'):
                i += 1
                continue
            if l['kind'] == 'refstart':
                in_refs = True
                i += 1
                continue
            if l['kind'] == 'ack':
                elements.append({'type': 'heading', 'level': 1, 'num': '', 'text': t})
                i += 1
                continue

            if l['kind'] == 'math':
                j = i
                ymin, ymax = l['y0'], l['y1']
                while j + 1 < N and ordered[j + 1]['kind'] == 'math' \
                        and colof(ordered[j + 1], cfg) == col and ordered[j + 1]['y0'] - ymax < 22:
                    ymax = max(ymax, ordered[j + 1]['y1']); j += 1
                cx0, cx1 = cfg['cols'][col]
                img = render(pi, fitz.Rect(cx0, ymin - 3, cx1, ymax + 3), f'eq_p{pi}_{col}_{int(ymin)}.png')
                if img:
                    elements.append({'type': 'equation', 'img': img})
                i = j + 1
                continue

            if l['kind'] in ('sec', 'sub'):
                j = i
                parts, ybot = [t], l['y1']
                while j + 1 < N:
                    nx = ordered[j + 1]
                    same = nx['kind'] == l['kind'] and colof(nx, cfg) == col and nx['y0'] - ybot < 6
                    caps_cont = (l['kind'] == 'sec' and nx['kind'] == 'prose' and colof(nx, cfg) == col
                                 and nx['y0'] - ybot < 7 and upper_ratio(nx['text']) >= 0.7
                                 and 3 <= len(nx['text'].strip()) < 50 and nx['size'] <= l['size'] + 2)
                    if not (same or caps_cont):
                        break
                    parts.append(nx['text'].strip()); ybot = nx['y1']; j += 1
                full = dehyph(parts)
                if l['kind'] == 'sec':
                    mm = SEC_RE.match(full)
                    elements.append({'type': 'heading', 'level': 1, 'num': mm.group(1), 'text': mm.group(2)})
                else:
                    mm = SUB_RE.match(full)
                    elements.append({'type': 'heading', 'level': 2, 'num': mm.group(1), 'text': mm.group(2)})
                i = j + 1
                continue

            if l['kind'] == 'cap':
                m = CAP_RE.match(t)
                is_tab = m.group(1).lower().startswith(('table', 'tab'))
                col2 = colof(l, cfg)
                # caption text = label + capcont lines below in same column
                cap_lines = [l]
                chain = l['y1']
                for mm in sorted([x for x in lines if colof(x, cfg) == col2 and x['kind'] in ('prose', 'infig')
                                  and x['size'] <= cfg['cap_max'] and x['y0'] >= l['y0'] - 2],
                                 key=lambda x: x['y0']):
                    if mm['y0'] - chain < 11:
                        cap_lines.append(mm)
                        mm['_capused'] = True
                        chain = max(chain, mm['y1'])
                    elif mm['y0'] > chain + 11:
                        break
                cap_lines.sort(key=lambda x: (round(x['y0'] / 4), x['x0']))
                captext = dehyph([x['text'] for x in cap_lines])
                mm2 = CAP_RE.match(captext)
                cap_body = captext[mm2.end():].lstrip(' .:–—').strip()
                r = rect_by_num.get((is_tab, m.group(2)))
                img = render(pi, r['rect'], f'{"table" if is_tab else "figure"}_{m.group(2)}.png') if r else None
                elements.append({'type': 'table' if is_tab else 'figure',
                                 'num': m.group(2), 'caption': cap_body, 'img': img})
                i += 1
                continue

            # prose
            j = i
            plines = [l]
            while j + 1 < N and ordered[j + 1]['kind'] == 'prose' and colof(ordered[j + 1], cfg) == col:
                plines.append(ordered[j + 1]); j += 1
            plines = [p for p in plines if not p.get('_capused')]
            if plines:
                gaps = [plines[k]['y0'] - plines[k - 1]['y1'] for k in range(1, len(plines))]
                _g = [g for g in gaps if g > -3]
                med = statistics.median(_g) if _g else 0
                paras = [[plines[0]]]
                for k in range(1, len(plines)):
                    gap = plines[k]['y0'] - plines[k - 1]['y1']
                    (paras.append([plines[k]]) if med and gap > med + 2.5 and gap > 2.0
                     else paras[-1].append(plines[k]))
                for para in paras:
                    txt = dehyph([p['text'] for p in para])
                    if len(txt) >= 2:
                        elements.append({'type': 'para', 'text': txt})
            i = j + 1

    # merge continuation paragraphs
    merged = []
    for e in elements:
        if e['type'] == 'para' and merged and merged[-1]['type'] == 'para':
            prev, cur = merged[-1]['text'], e['text']
            ends = re.search(r'[.!?:][)"\'”»]?$', prev)
            if not ends and cur[:1] not in ('•', '–', '*', '-'):
                if prev.endswith('-') and not prev.endswith('--'):
                    nxt = cur.split(' ', 1)[0].rstrip('.,;:').lower()
                    merged[-1]['text'] = (prev + ' ' + cur) if nxt in CONT_WORDS else (prev[:-1] + cur)
                else:
                    merged[-1]['text'] = prev + ' ' + cur
                continue
        merged.append(e)

    if ref_buf:
        refs, cur = [], ''
        for t in ref_buf:
            if re.match(r'^\[\d+\]', t):
                if cur:
                    refs.append(cur.strip())
                cur = t
            else:
                cur += ' ' + t
        if cur:
            refs.append(cur.strip())
        merged.append({'type': 'references', 'items': [dehyph([r]) for r in refs]})

    with open(f'work2/content_{doc_key}.json', 'w') as f:
        json.dump(merged, f, ensure_ascii=False, indent=1)
    c = Counter(e['type'] for e in merged)
    nchars = sum(len(e.get('text', '')) + len(e.get('caption', '')) for e in merged)
    noimg = [e.get('num') for e in merged if e['type'] in ('figure', 'table') and not e.get('img')]
    print(f'[{doc_key}] elements={len(merged)} {dict(c)} | chars={nchars} | no-img={noimg}')
    return merged


if __name__ == '__main__':
    for k in ('journal', 'conf'):
        build(k)
