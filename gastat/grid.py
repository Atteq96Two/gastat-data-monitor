"""Load an Excel sheet into a plain grid (merged cells expanded) and classify cells.
No positions are hardcoded anywhere: callers detect structure from the grid."""
import re, datetime as dt, unicodedata

MISSING = {"-", "--", "---", "..", "...", "—", "–", "n/a", "na", "x", "*", "ـ", "…"}
TASHKEEL = re.compile(r"[ً-ٰٟـ]")
ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
MONTHS_AR = "يناير فبراير مارس ابريل مايو يونيو يوليو اغسطس سبتمبر اكتوبر نوفمبر ديسمبر".split()
MONTHS_EN = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def norm(s):
    """Normalize a label for matching and fingerprinting (never for display)."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    s = TASHKEEL.sub("", s)
    s = re.sub("[أإآٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    s = s.replace("انثي", "انثي").replace("الاجمالي", "اجمالي")
    s = re.sub(r"[‎‏‪-‮]", "", s)
    s = re.sub(r"\s+", " ", s).strip().lower()
    s = re.sub(r"^ال(?=اجمالي)", "", s)
    return s


def clean(s):
    """Display-clean a label: strip bidi marks, collapse spaces, drop trailing footnote stars."""
    if s is None:
        return ""
    s = re.sub(r"[‎‏‪-‮]", "", str(s))
    s = re.sub(r"\s+", " ", s).strip()
    return s


def script(s):
    a, l = len(ARABIC.findall(s)), len(LATIN.findall(s))
    if a == 0 and l == 0:
        return "none"
    return "ar" if a >= l else "en"


def kind(v):
    """empty | num | date | text | missing"""
    if v is None:
        return "empty"
    if isinstance(v, bool):
        return "text"
    if isinstance(v, (int, float)):
        return "num"
    if isinstance(v, (dt.datetime, dt.date)):
        return "date"
    s = str(v).strip()
    if s == "":
        return "empty"
    if s.lower() in MISSING:
        return "missing"
    if re.fullmatch(r"[-+]?\d[\d,]*\.?\d*", s):
        return "numtext"
    return "text"


def to_num(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = str(v).strip().replace(",", "")
    return float(s)


def is_year(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and float(v).is_integer() and 1950 <= v <= 2100


class Grid:
    """cells[r][c] (0-based) with merged ranges expanded; raw[r][c] keeps only the anchor value."""

    def __init__(self, ws, max_empty_run=60, hard_cap=4000):
        rows, last, empty_run = [], -1, 0
        for i, row in enumerate(ws.iter_rows(max_row=min(ws.max_row, hard_cap), values_only=True)):
            rows.append(list(row))
            if any(v is not None and str(v).strip() != "" for v in row):
                last, empty_run = i, 0
            else:
                empty_run += 1
                if empty_run > max_empty_run:
                    break
        rows = rows[: last + 1]
        self.ncols = min(max((len(r) for r in rows), default=0), 200)
        self.cells = [[(r[c] if c < len(r) else None) for c in range(self.ncols)] for r in rows]
        self.anchor = [[(v is not None) for v in r] for r in self.cells]
        self.merges = []
        for m in ws.merged_cells.ranges:
            r0, r1, c0, c1 = m.min_row - 1, m.max_row - 1, m.min_col - 1, m.max_col - 1
            if r0 >= len(self.cells) or c0 >= self.ncols:
                continue
            v = self.cells[r0][c0]
            self.merges.append((r0, r1, c0, c1))
            for r in range(r0, min(r1, len(self.cells) - 1) + 1):
                for c in range(c0, min(c1, self.ncols - 1) + 1):
                    if (r, c) != (r0, c0):
                        self.cells[r][c] = v
                        self.anchor[r][c] = False
        self.nrows = len(self.cells)

    def k(self, r, c):
        return kind(self.cells[r][c])
