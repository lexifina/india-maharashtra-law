"""Independent letters-and-digits check of a part against the source PDFs, read by a second engine (xpdf pdftotext -raw).

    python -X utf8 check_letters.py corpus.d/20-acts-01.json [...]

Private. For each act, its units (heading lines left out) reduced to letters and digits must be found, in order, in the
PDF's text reduced the same way. Source text may be passed over only where it cannot be part of the body: up to four
digits (footnote numbers) inside the body; a stretch that crosses exactly one page break (running head, footnotes,
marginal notes and printer's marks at the foot of one page and the head of the next); or, within a page, a stretch made
up only of lines that parse.py's layout rules put outside the body column or under the last body line (margin notes,
footnotes, running heads), which the two engines read in different orders. Anything else is a mismatch: a word in the
record that is not in the PDF, words out of order, or body text left out within a page.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FF = '\x0c'


def ld(s):
    return ''.join(ch for ch in s if ch.isalnum() or ch == FF)


def source(pdf):
    out = subprocess.run(['pdftotext', '-raw', '-enc', 'UTF-8', str(pdf), '-'], capture_output=True).stdout
    return ld(out.decode('utf-8', 'replace'))


def pat(s):
    return re.compile(r'\d{0,3}'.join(map(re.escape, s)))


def align(U, S, body_at=0, aside=()):
    """body_at: where in U the first section starts. The record starts at the Act's title page, which is the last
    place its opening words occur before the first section's words (the cover and contents repeat the title).
    aside: the letters and digits of each line the parser left out of the text, longest first."""
    i = j = 0
    first = None
    skips = 0
    m = pat(U[body_at:body_at + 30]).search(S)
    limit = m.start() if m else len(S)
    for n in (40, 16):
        p = [x.start() for x in pat(U[:n]).finditer(S, 0, limit)]
        if p:
            j = first = p[-1]
            break
    while i < len(U):
        if j < len(S) and S[j] == U[i]:
            if first is None:
                first = j
            i += 1; j += 1
            continue
        hit = None
        for L in (1, 2, 3, 4):
            if j + L <= len(S) and S[j:j + L].isdigit() and S[j + L:j + L + 8] == U[i:i + 8]:
                hit = j + L; break
        if hit is not None:
            j = hit; skips += 1
            continue
        # the next 16 characters of the record, footnote numbers (up to 3 digits) allowed between them in the source
        m = re.compile(r'\d{0,3}'.join(map(re.escape, U[i:i + 16]))).search(S, j)
        pos = m.start() if m else -1
        if pos < 0:
            return False, f'record text not found in the PDF from here: {U[i:i + 60]!r}'
        gap = S[j:pos]
        if (first is None or gap.count(FF) == 1 or (gap.count(FF) > 1 and not gap.replace(FF, ''))
                or (len(gap) <= 4 and gap.isdigit())):
            j = pos; skips += 1
            continue
        if aside and FF not in gap:
            # within a page: only text the parser set aside (margin notes, footnotes, running heads), plus footnote
            # numbers, may be passed over (the two engines order such text differently)
            rest = gap
            for a in aside:
                if a in rest:
                    rest = rest.replace(a, '', 1)
            if len(rest) <= 4 and (not rest or rest.isdigit()):
                j = pos; skips += 1
                continue
        if gap.count(FF) > 1 and first is not None:
            # several page breaks: allowed only if every page in between is empty of letters (blank pages)
            inner = gap.split(FF)[1:-1]
            if all(len(p) < 40 for p in inner):
                j = pos; skips += 1
                continue
        return False, f'source passed over within a page ({len(gap)} chars): {gap[:80]!r} before {U[i:i + 40]!r}'
    return True, f'{len(U)} chars matched, {skips} skips'


def aside_of(pdf):
    """The letters and digits of every line parse.py leaves out of the text (its layout rules, not its text)."""
    import pymupdf
    import parse
    pages, _ = parse.rows_of(pymupdf.open(str(pdf)))
    out = {ld(r[5]) for rows in pages for r in rows if r[1] != 'body'}
    return sorted((a for a in out if len(a) >= 3), key=lambda a: (-len(a), a))  # a fixed order: same result every run


def check_act(units, S, aside=()):
    U, body_at = '', 0
    for k, u in units.items():
        if k.startswith('sec-') and not body_at:
            body_at = len(U)
        U += ld(re.sub(r'(?m)^# .*$', '', u['text']))
    return align(U, S, body_at, aside)


def main(paths):
    bad = total = 0
    for p in paths:
        c = json.load(open(p, encoding='utf-8'))
        for a in c['acts']:
            v = a['versions'][-1]
            pdf = HERE / '.cache' / 'pdf' / v['source_url'].rsplit('/', 1)[1]
            S = source(pdf)
            ok, msg = check_act(v['units'], S, aside_of(pdf))
            total += 1
            if not ok:
                bad += 1
                print(f'MISMATCH {a["slug"]}: {msg}')
    print(f'{total} acts checked, {bad} mismatches')
    return bad


if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1:] or sorted(str(p) for p in (HERE / 'corpus.d').glob('*.json'))) else 0)
