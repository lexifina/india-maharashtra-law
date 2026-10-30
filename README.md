# Maharashtra: law history in git

The Acts of the State of Maharashtra (India) as a git history: one file per section, one paragraph per line, so `git blame`, `git log` and `git diff` work line by line. The text is the English text of the department's reprints.

It follows the shared design of [lexifina/global-law](https://github.com/lexifina/global-law).

## What this repository holds

**Current text only, not yet a history.** The Law and Judiciary Department publishes each Act as a reprint "as modified up to" a stated date, with no earlier consolidated text. So each Act is one commit holding its whole text as of that date, credited to the department ("oldest version available"), not to an amending Act.

| Folder | What |
| --- | --- |
| one folder per Act (by its short title, e.g. `maharashtra-housing-and-area-development-act-1976/`) | the Act as reprinted: `000-title.md`, `001-preamble.md`, one file per section, one per Schedule |
| `data/amendments.csv` | for each Act, the amending Acts its title page lists (with the commencement dates it prints) and every footnote, which says which Act inserted, substituted or deleted which words |

The Acts are added in parts of about fifty, in the order of the department's list. Rules, amending Acts and ordinances are not included. A reprint is left out until it can be read reliably: scans without a text layer, PDFs whose layout the parser does not yet handle, and any reprint whose text fails the independent check below. Where the department lists several reprints of one Act, only the newest is used.

## Source

[Law and Judiciary Department, Government of Maharashtra](https://lj.maharashtra.gov.in/en/document-category/reprint-of-the-act/): "Reprint of the Act", English PDF reprints printed by the Government Central Press. Each PDF's sha256 is recorded with its version in `data/versions.json`.

## Dates

Each Act's version is dated by the day the reprint says the text is brought up to ("As modified upto the ..."), at noon in Mumbai. That is the day the department's consolidation reaches, not the day of the last amendment.

## How it is built

Lexifina reads the sources listed here and records each act's dated versions, and the laws that made each change, in one corpus file. `tools/build.py` writes this repository from that file, and the same corpus always gives the same commit hashes; `REPRODUCE.md` gives the details and the checks. A model (Claude) wrote Lexifina's code; it wrote no legal text, and no model runs when the history is built.

The text layer of each PDF (no OCR) becomes one file per section. The cover, the table of contents, running heads, marginal notes (the section headings and citations printed in the margins) and footnote numbers are left out. The footnotes are kept in `data/amendments.csv`. The square brackets and asterisks that mark amended or omitted words stay as printed. Chapter and part headings stand above the first section under them.

## How it is checked

Every version is read back from git on the day it took effect and must match the corpus. A second, independent reading of every PDF (a different PDF engine) must contain every letter and digit of each Act in the same order, with nothing in the body left out. Results are in `REPRODUCE.md`.

## What "author" means

The author of each commit is the publisher (the Law and Judiciary Department), with an e-mail address that cannot exist; the committer is always Lexifina.

## Limits

Only the text as of each reprint's date is here: no earlier versions, and not the Acts as enacted. The reprints are not the authoritative text; the Maharashtra Government Gazette is. Marginal notes (section headings) are left out.

## Licence

See [LICENSE](LICENSE): the Acts are reproduced under the Copyright Act, 1957, s. 52(1)(q)(ii), together with this repository's own matter. Source: Law and Judiciary Department, Government of Maharashtra.
