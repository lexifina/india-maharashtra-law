"""Parse Maharashtra Act reprints (English text-layer PDFs of the Law and Judiciary Department) into units.

    python -X utf8 parse.py <file.pdf>            # print the units of one reprint (for inspection)

Used by make_part.py. Reads only the PDF it is given. Rules, from the layout of the Government Central Press reprints:
- The body column is where the body-size text (the most common font size) sits; marginal notes (section headings
  and citations printed in the margins) lie outside it and are left out.
- The running head (top of each page), footnotes (small type under the last body line) and printer's marks are left
  out of the text; footnotes are returned separately as the amendment notes.
- Superscript footnote numbers (small type, digits only) are dropped; the brackets and asterisks they mark stay as
  printed.
- A paragraph starts on an indented row; a section starts on an indented row "N." with N in sequence; centred rows
  (chapter and part headings) go above the next section.
"""
import re
import sys
import warnings
from collections import Counter

warnings.filterwarnings('ignore')
import pymupdf  # noqa: E402

ROMAN = r'[IVXLC]+'
MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
                                      'september', 'october', 'november', 'december'], 1)}


def norm(s):
    s = s.replace('\xa0', ' ').replace('­', '').replace('﻿', '')
    s = s.replace('’', "'").replace('‘', "'").replace('“', '"').replace('”', '"')
    s = s.replace('–', '-').replace('—', '-').replace('−', '-')
    return re.sub(r'\s+', ' ', s).strip()


def rows_of(doc):
    """Every page's rows: (page, kind, x0, x1, y0, text) with kind body/foot/margin/head."""
    sizes = Counter()
    pages = []
    for page in doc:
        lines = []
        for b in page.get_text('dict')['blocks']:
            if b.get('type') != 0:
                continue
            for ln in b['lines']:
                spans = [s for s in ln['spans'] if s['text'].strip()]
                if not spans:
                    continue
                for s in spans:
                    sizes[round(s['size'], 1)] += len(s['text'].strip())
                lines.append((ln['bbox'], spans))
        pages.append((page.rect, lines))
    body = sizes.most_common(1)[0][0] if sizes else 11.0
    out = []
    for pi, (rect, lines) in enumerate(pages):
        H = rect.height
        top = 0.088 * H
        big = [(bb, sp) for bb, sp in lines if abs(max(s['size'] for s in sp) - body) <= 0.6 and bb[1] >= top]
        if not big:
            out.append([])
            continue
        HEADLIKE = re.compile(r'\b\d{4}\s*:\s*(?:(?:Mah|Bom|Hyd|C\.\s*P|M\.\s*P)\.?\s*)?[IVXLC]+\b|^\[\s*\d{4}\s*:')
        heads = [bb for bb, sp in lines if bb[1] < 0.13 * H and HEADLIKE.search(''.join(x['text'] for x in sp).strip())]
        if heads:
            top = max(bb[3] for bb in heads) + 2  # just under the running head
            big = [(bb, sp) for bb, sp in big if bb[1] >= top]
            if not big:
                out.append([])
                continue
        cx0 = min(bb[0] for bb, _ in big)
        cx1 = max(bb[2] for bb, _ in big)
        last_body = max(bb[3] for bb, _ in big)
        items = []
        for bb, sp in lines:
            x0, y0, x1, y1 = bb
            mx = max(s['size'] for s in sp)
            if y0 < top - 1:
                kind = 'head'
            elif x1 <= cx0 + 2 or x0 >= cx1 - 2:
                kind = 'margin'
            elif mx < body - 0.6 and y0 >= last_body - 2:
                kind = 'foot'
            else:
                kind = 'body'
            txt = ''
            for j, s in enumerate(sp):
                if kind == 'body' and s['size'] < body - 3.5 and re.fullmatch(r'\s*[\d]+\s*', s['text']):
                    continue  # a footnote number
                if j and txt and not txt.endswith(' ') and not s['text'].startswith(' ') and s['bbox'][0] - sp[j - 1]['bbox'][2] > 0.15 * s['size']:
                    txt += ' '
                txt += s['text']
            items.append((kind, x0, x1, y0, y1, txt))
        # rows: body lines sharing a baseline band, left to right
        # rows: body lines whose vertical centres lie within half a line of each other, read left to right
        body_items = sorted([i for i in items if i[0] == 'body'], key=lambda i: ((i[3] + i[4]) / 2, i[1]))
        rows = []
        for it in body_items:
            yc = (it[3] + it[4]) / 2
            if rows and abs(yc - rows[-1]['yc']) < 0.45 * body:
                rows[-1]['items'].append(it)
            else:
                rows.append({'yc': yc, 'items': [it]})
        page_rows = []
        for r in rows:
            its = sorted(r['items'], key=lambda i: i[1])
            page_rows.append((pi, 'body', its[0][1], max(i[2] for i in its), min(i[3] for i in its),
                              norm(' '.join(i[5] for i in its)), cx0, cx1))
        feet = sorted([i for i in items if i[0] == 'foot'], key=lambda i: (i[3], i[1]))
        frows = []
        for it in feet:
            if frows and abs(it[3] - frows[-1][1]) < 4:
                frows[-1][2].append(it[5])
            else:
                frows.append([it[1], it[3], [it[5]]])
        page_rows += [(pi, 'foot', f[0], 0, f[1], norm(' '.join(f[2])), cx0, cx1) for f in frows]
        # margin notes and running heads, line by line (left out of the text; the letters check may pass over them)
        page_rows += [(pi, i[0], i[1], i[2], i[3], norm(i[5]), cx0, cx1) for i in items if i[0] in ('margin', 'head')]
        # printer's signature marks at the foot of a sheet ("H 4113-4a")
        # and the printer's imprint on the last page ("GOVERNMENT CENTRAL PRESS, MUMBAI", "PRINTED AT THE GOVERNMENT PRESS")
        out.append([r for r in page_rows if r[5] and not re.fullmatch(r'\W?[a-z]?\s*H\s*\d{2,5}\s*-+\s*\d+[a-z]*\W?', r[5])
                    and not re.fullmatch(r'(GOVERNMENT (CENTRAL )?PRESS|GOVT\.? PRESS)[^a-z]{0,30}', r[5])
                    and not re.search(r'PRINTED (AT|IN|BY) (THE )?(GOVERNMENT|MANAGER)', r[5], re.I)])
    return out, body


def date_from(text):
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th)?\s+(?:day\s+of\s+)?([A-Za-z]+),?\s+(\d{4})', text)
    if m and m.group(2).lower() in MONTHS:
        return '%04d-%02d-%02d' % (int(m.group(3)), MONTHS[m.group(2).lower()], int(m.group(1)))
    return None


SEC = re.compile(r'^\[?\s*(\d{1,3})([A-Z]{0,3})\s*\.\s*(?=\S)')
CH = re.compile(r'^(CHAPTER|PART)\s+(' + ROMAN + r'(?:-?[A-Z]{1,2})?)\s*\.?$', re.I)
SCHED = re.compile(r'^\[?\s*(THE\s+)?((FIRST|SECOND|THIRD|FOURTH|FIFTH|SIXTH|SEVENTH|EIGHTH|NINTH|TENTH)\s+)?SCHEDULE\b', re.I)
END_PAGE = re.compile(r'can be obtained from|Maharashtra Government Publications', re.I)


def parse(path):
    doc = pymupdf.open(str(path))
    pages, body = rows_of(doc)
    meta = {'pages': len(doc)}
    cover = ' '.join(r[5] for r in (pages[0] if pages else []))
    for pi in range(min(3, len(pages))):
        cover = cover if pi == 0 else cover + ' ' + ' '.join(r[5] for r in pages[pi])
    m = re.search(r'(?:as|text as)\s+(?:modified|amended|on)\s+(?:up\s*to|upto)?\s*(?:the\s+)?([^)\]]{6,40})', cover, re.I)
    meta['modified_upto'] = date_from(m.group(1)) if m else None
    m = re.search(r'\b((?:MAHARASHTRA|BOMBAY|HYDERABAD|MADHYA PRADESH|C\.\s*P\.|BERAR)[A-Z .&]*?)\s+ACT\s+No\.?\s+(' + ROMAN + r'|\d+)\s+OF\s+(\d{4})', cover, re.I)
    meta['act_no'] = norm(m.group(0)) if m else None
    # the first page of the Act itself: section 1 ("1. (1) This Act may be called ...")
    s1 = None
    for pi, rows in enumerate(pages[1:], 1):
        txt = ' '.join(r[5] for r in rows if r[1] == 'body')
        if re.search(r'\bCONTENTS\b|^SECTIONS\.|\bPAGES\b', txt[:400]) and not re.search(r'may be (called|cited)', txt):
            continue
        for ri, r in enumerate(rows):
            if r[1] == 'body' and SEC.match(r[5]) and SEC.match(r[5]).group(1) == '1' and not SEC.match(r[5]).group(2):
                nxt = ' '.join(x[5] for x in rows[ri:ri + 3])
                if re.search(r'may\s+be\s+(called|cited)|short title', nxt, re.I):
                    s1 = (pi, ri); break
        if s1:
            break
    if not s1:
        raise ValueError('section 1 not found')
    # the title page: the last page up to section 1 holding the "ACT No. ... OF ...." line
    # the title page: going back from section 1, the first page with the Act number, the assent note or the long title
    TITLE_ROW = re.compile(r'ACT\s+No\.?\s+(' + ROMAN + r'|\d+)\s+OF\s+\d{4}|assent|^\[?(An|AN)\s+(Act|ACT)\b', re.I)
    tp = s1[0]
    for pi in range(s1[0], 0, -1):
        if any(TITLE_ROW.search(r[5]) for r in pages[pi] if r[1] == 'body' and (pi < s1[0] or r[4] <= pages[pi][s1[1]][4])):
            tp = pi; break
    flat = []      # body rows from the title page to the end
    feet = []
    aside = []     # every line left out of the text (footnotes, margin notes, running heads) on those pages
    for pi in range(tp, len(pages)):
        if END_PAGE.search(' '.join(r[5] for r in pages[pi])):
            break
        for r in pages[pi]:
            if r[1] == 'body':
                flat.append(r)
            elif r[1] == 'foot':
                feet.append((pi + 1, r[5]))
            if r[1] != 'body':
                aside.append(r[5])
    # the title begins at the Act number on the title page if it is there, else at the page's first row
    start_title = next((i for i, r in enumerate(flat) if r[0] == tp and re.search(r'ACT\s+No\.?\s+(' + ROMAN + r'|\d+)\s+OF\s+\d{4}', r[5], re.I)), 0)
    flat = flat[start_title:]
    i_s1 = next(i for i, r in enumerate(flat) if r[0] == s1[0] and SEC.match(r[5]) and SEC.match(r[5]).group(1) == '1')
    i_long = next((i for i in range(i_s1) if re.match(r'^\[?(An|AN)\s+(Act|ACT)\b', flat[i][5])), None)
    title_rows = flat[:i_long if i_long is not None else i_s1]
    pre_rows = flat[i_long:i_s1] if i_long is not None else []
    tt = ' '.join(r[5] for r in title_rows)
    m = re.search(r'([A-Z][A-Za-z.]*(?:\s+[A-Z][A-Za-z.]*)*\s+)?ACT\s+No\.?\s+(' + ROMAN + r'|\d+)\s+OF\s+(\d{4})', title_rows[0][5] if title_rows else '', re.I)
    meta['act_no'] = norm(m.group(0)) if m else None
    m = re.search(r'assent of the (?:Governor|President)[^.]*?on the ([^;.]*?\d{4})', tt)
    meta['assent'] = date_from(m.group(1)) if m else None
    m = re.search(r'first published in the [^,]*Gazette[^.]*?on the ([^;.)]*?\d{4})', tt)
    meta['gazette'] = date_from(m.group(1)) if m else None
    meta['amended_by'] = re.findall(r'(\d+)\s+of\s+(\d{4})\s*([^\d\s(]*)\s*(?:\((\d{1,2}-\d{1,2}-\d{4})\))?', ' '.join(
        r[5] for r in title_rows if re.search(r'^(Amended by|Mah\.|"|\d+ of \d{4})', r[5]) or re.search(r'^\W*\d+\s+of\s+\d{4}', r[5])))

    def is_centred(r):
        cx0, cx1 = r[6], r[7]
        w = cx1 - cx0
        return r[2] > cx0 + 0.08 * w and abs((r[2] + r[3]) / 2 - (cx0 + cx1) / 2) < 0.08 * w and (r[3] - r[2]) < 0.8 * w

    def para_start(r):
        return r[2] > r[6] + 5

    units = {}
    order = []

    START = re.compile(r'^\[?\s*(\(\w{1,5}\)|\d{1,3}[A-Z]{0,3}\s*\.\s|Provided|Explanation|Illustration|Exception|Note\b|CHAPTER|PART\b|Amended by|"\s*"|"?\s*\(\w{1,5}\))')

    def add(key, label, kind, rows_):
        lines = []
        prev = None
        for r in rows_:
            if (lines and prev is not None and (is_centred(prev) or is_centred(r) or lines[-1].startswith('['))
                    and not re.search(r'[.;:\]]\s*$', prev[5]) and not CH.match(prev[5])
                    and not re.search(r'\bACT\s+No\b', lines[-1], re.I)
                    and not START.match(r[5]) and not CH.match(r[5]) and not SCHED.match(r[5])):
                lines[-1] += ' ' + r[5]  # a centred title or long title running on to the next line
                prev = r
                continue
            new = (not lines or is_centred(r) or (prev is not None and is_centred(prev))
                   or bool(START.match(r[5]))
                   or (r[2] > prev[2] + 3 and re.search(r'[.;:\-]\s*$', prev[5]) is not None)
                   or r[0] == prev[0] and r[4] - prev[4] > 1.9 * 13.5 and re.search(r'[.;:\-]\s*$', prev[5]) is not None)
            if new:
                lines.append(r[5])
            else:
                lines[-1] += ' ' + r[5]
            prev = r
        units[key] = {'label': label, 'kind': kind, 'lines': ['# ' + label] + lines}
        order.append(key)

    add('000-title', 'Title', 'title', title_rows)
    if pre_rows:
        add('001-preamble', 'Preamble', 'preamble', pre_rows)
    # sections
    rest = flat[i_s1:]
    cur_rows, cur = [], None
    pending = []
    last_num = 0
    seen = []
    sched_n = 0

    def flush():
        if cur:
            add(cur[0], cur[1], cur[2], cur_rows)
    i = 0
    while i < len(rest):
        r = rest[i]
        t = r[5]
        sm = SEC.match(t)
        if sm and para_start(r) and not is_centred(r) and cur and cur[2] == 'schedule':
            sm = None
        if is_centred(r) and (CH.match(t) or SCHED.match(t)) or (pending and is_centred(r)):
            if SCHED.match(t) and (cur is None or cur[2] != 'schedule' or not pending):
                flush()
                sched_n += 1
                cur = ('s%02d-schedule' % sched_n, norm(t).strip('[]. ').title() if len(t) < 60 else 'Schedule %d' % sched_n, 'schedule')
                cur_rows = [r]
                pending = []
                i += 1
                continue
            pending.append(r)
            i += 1
            continue
        if sm and para_start(r) and not is_centred(r):
            n = int(sm.group(1))
            if (last_num <= n <= last_num + 25) and (cur is None or cur[2] != 'schedule'):
                flush()
                num = sm.group(1) + sm.group(2)
                cur = ('sec-%03d%s' % (n, ('-' + sm.group(2).lower()) if sm.group(2) else ''), 'Section ' + num, 'section')
                if cur[0] in units:
                    cur = (cur[0] + '-%d' % i, cur[1], cur[2])
                cur_rows = pending + [r]
                pending = []
                last_num = n
                seen.append(num)
                i += 1
                continue
        if pending:
            # centred rows that were not headings after all (a short centred line inside a section)
            cur_rows += pending
            pending = []
        cur_rows.append(r)
        i += 1
    cur_rows += pending
    flush()
    out = {}
    for k in order:
        u = units[k]
        out[k] = {'label': u['label'], 'kind': u['kind'], 'text': '\n'.join(u['lines']) + '\n'}
    meta['sections'] = seen
    meta['footnotes'] = feet
    meta['aside'] = aside
    meta['body_size'] = body
    return out, meta


if __name__ == '__main__':
    units, meta = parse(sys.argv[1])
    for k, u in units.items():
        print('=====', k)
        print(u['text'][:600])
    print({k: v for k, v in meta.items() if k != 'footnotes'})
    print(len(meta['footnotes']), 'footnote rows')
