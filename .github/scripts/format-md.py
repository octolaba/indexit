#!/usr/bin/env python3
"""
Normalize a Markdown file to indexit's formatting rules
(AGENTS.md / CLAUDE.md §6):

  1. Drop `---` horizontal rules used as section separators.
     YAML frontmatter, fenced code, and HTML comments are left alone.
  2. Align GFM table columns to the widest cell per column, preserving
     `:---`/`---:`/`:---:` alignment markers.
  3. Remove the blank line between a paragraph and the bullet/numbered
     list that follows it. Blank line is preserved when the preceding
     block is a heading, another list, a table, a block quote, or a
     code fence — those have their own spacing rules.

Usage:
  format-md.py <file> [<file> ...]            # rewrite in place
  format-md.py --check <file> [<file> ...]    # print diff, exit non-zero if changed
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path


HEADING_RE = re.compile(r'^#{1,6}\s')
LIST_RE = re.compile(r'^(\s*)([-*+]|\d+\.)\s')
TABLE_RE = re.compile(r'^\s*\|')
FENCE_RE = re.compile(r'^\s*(```|~~~)')
HTML_COMMENT_OPEN = '<!--'
HTML_COMMENT_CLOSE = '-->'


def display_width(s: str) -> int:
    """Width as rendered in a monospace font: CJK = 2, combining = 0."""
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        if unicodedata.east_asian_width(ch) in ('W', 'F'):
            w += 2
        else:
            w += 1
    return w


def pad_to(s: str, target: int) -> str:
    return s + ' ' * max(0, target - display_width(s))


def split_row(line: str) -> tuple[str, list[str], str]:
    """Split `| a | b |` into (lead_ws, cells, trail_ws).

    Returns empty cells for non-table lines (no leading + trailing pipe).
    Escaped `\\|` stays inside its cell.
    """
    m = re.match(r'^(\s*)\|(.*)\|(\s*)$', line)
    if not m:
        return ('', [], '')
    body = m.group(2)
    cells: list[str] = []
    cur = ''
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == '\\' and i + 1 < len(body):
            cur += body[i:i + 2]
            i += 2
            continue
        if ch == '|':
            cells.append(cur)
            cur = ''
            i += 1
            continue
        cur += ch
        i += 1
    cells.append(cur)
    return (m.group(1), cells, m.group(3))


def is_separator_row(cells: list[str]) -> bool:
    if not cells:
        return False
    for c in cells:
        if not re.fullmatch(r':?-{3,}:?', c.strip()):
            return False
    return True


def align_table(rows: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Re-emit a contiguous block of `|...|` rows with aligned columns.

    Returns input unchanged when the block is not a real GFM table —
    we require the separator on row 1, anything else may be a stray
    pipe sequence and is safer to leave alone.
    """
    if len(rows) < 2:
        return rows

    parsed = [split_row(line) for _, line in rows]
    if not all(p[1] for p in parsed):
        return rows

    sep_idx = next(
        (i for i, (_, cells, _) in enumerate(parsed) if is_separator_row(cells)),
        None,
    )
    if sep_idx != 1:
        return rows

    n_cols = max(len(cells) for _, cells, _ in parsed)
    norm = [
        (lead, cells + [''] * (n_cols - len(cells)), trail)
        for lead, cells, trail in parsed
    ]

    widths = [0] * n_cols
    align: list[str] = ['l'] * n_cols
    for i, (_, cells, _) in enumerate(norm):
        if i == sep_idx:
            for j, c in enumerate(cells):
                s = c.strip()
                left = s.startswith(':')
                right = s.endswith(':')
                if left and right:
                    align[j] = 'c'
                elif right:
                    align[j] = 'r'
                else:
                    align[j] = 'l'
            continue
        for j, c in enumerate(cells):
            w = display_width(c.strip())
            if w > widths[j]:
                widths[j] = w
    # GFM requires the separator to have at least 3 dashes per column;
    # widen anything narrower so the rendered table stays legal.
    widths = [max(w, 3) for w in widths]

    out: list[tuple[int, str]] = []
    for k, (lead, cells, trail) in enumerate(norm):
        parts = []
        if k == sep_idx:
            for j in range(n_cols):
                w = widths[j]
                if align[j] == 'c':
                    parts.append(':' + '-' * (w - 2) + ':')
                elif align[j] == 'r':
                    parts.append('-' * (w - 1) + ':')
                else:
                    parts.append('-' * w)
        else:
            for j in range(n_cols):
                content = cells[j].strip()
                w = widths[j]
                if align[j] == 'r':
                    parts.append(' ' * (w - display_width(content)) + content)
                elif align[j] == 'c':
                    extra = w - display_width(content)
                    left_pad = extra // 2
                    parts.append(' ' * left_pad + content + ' ' * (extra - left_pad))
                else:
                    parts.append(pad_to(content, w))
        out.append((rows[k][0], lead + '| ' + ' | '.join(parts) + ' |'))
    return out


def protected_mask(lines: list[str]) -> list[bool]:
    """Mark lines inside fenced code blocks or HTML comments.

    These regions are never rewritten — pipes inside a code block are
    not a table, and `---` inside an HTML comment is not a separator.
    """
    mask = [False] * len(lines)
    in_code = False
    in_comment = False
    for i, line in enumerate(lines):
        if in_comment:
            mask[i] = True
            if HTML_COMMENT_CLOSE in line:
                in_comment = False
            continue
        if in_code:
            mask[i] = True
            if FENCE_RE.match(line):
                in_code = False
            continue
        if FENCE_RE.match(line):
            in_code = True
            mask[i] = True
            continue
        if line.lstrip().startswith(HTML_COMMENT_OPEN):
            in_comment = True
            mask[i] = True
            if HTML_COMMENT_CLOSE in line:
                in_comment = False
    return mask


def frontmatter_end(lines: list[str]) -> int:
    """Return the index of the closing `---` of YAML frontmatter, or -1."""
    if not lines or lines[0].strip() != '---':
        return -1
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            return i
    return -1


def normalize(text: str) -> str:
    lines = text.split('\n')
    protected = protected_mask(lines)
    fm_end = frontmatter_end(lines)

    # Pass 1: drop horizontal-rule separators outside frontmatter / code.
    pass1: list[str] = []
    pass1_protected: list[bool] = []
    for i, line in enumerate(lines):
        if i <= fm_end or protected[i]:
            pass1.append(line)
            pass1_protected.append(protected[i])
            continue
        if line.strip() == '---':
            continue
        pass1.append(line)
        pass1_protected.append(False)

    # Pass 2: align tables (skipping protected regions).
    pass2: list[str] = []
    i = 0
    while i < len(pass1):
        if pass1_protected[i] or not TABLE_RE.match(pass1[i]):
            pass2.append(pass1[i])
            i += 1
            continue
        j = i
        block: list[tuple[int, str]] = []
        while j < len(pass1) and not pass1_protected[j] and TABLE_RE.match(pass1[j]):
            block.append((j, pass1[j]))
            j += 1
        for _, l in align_table(block):
            pass2.append(l)
        i = j

    # Pass 3: drop blank line between a paragraph and the list that
    # follows. Heading→list, list→list, table→list, quote→list, and
    # code-fence→list all keep the blank — those blocks own their
    # spacing.
    protected2 = protected_mask(pass2)
    fm_end2 = frontmatter_end(pass2)
    pass3: list[str] = []
    i = 0
    while i < len(pass2):
        line = pass2[i]
        if (
            i > fm_end2
            and i + 1 < len(pass2)
            and line.strip() == ''
            and not protected2[i]
            and LIST_RE.match(pass2[i + 1])
            and not protected2[i + 1]
        ):
            k = i - 1
            while k >= 0 and pass2[k].strip() == '':
                k -= 1
            if k >= 0 and not protected2[k]:
                prev = pass2[k]
                glue = not (
                    HEADING_RE.match(prev)
                    or LIST_RE.match(prev)
                    or TABLE_RE.match(prev)
                    or prev.lstrip().startswith('>')
                    or FENCE_RE.match(prev)
                )
                if glue:
                    i += 1
                    continue
        pass3.append(line)
        i += 1

    # Collapse runs of 2+ blank lines (outside protected regions) to a
    # single blank. Markdown treats them identically, and a removed
    # `---` separator typically leaves two blanks back-to-back that
    # would otherwise read as a gap.
    protected3 = protected_mask(pass3)
    out: list[str] = []
    blank = 0
    for i, line in enumerate(pass3):
        if line.strip() == '' and not protected3[i]:
            blank += 1
            if blank <= 1:
                out.append(line)
        else:
            blank = 0
            out.append(line)
    return '\n'.join(out)


def process(path: Path, check: bool) -> bool:
    """Return True if the file is (or would be) changed."""
    text = path.read_text(encoding='utf-8')
    new = normalize(text)
    if new == text:
        return False
    if check:
        import difflib
        sys.stdout.writelines(difflib.unified_diff(
            text.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=str(path),
            tofile=str(path) + ' (formatted)',
            n=2,
        ))
    else:
        path.write_text(new, encoding='utf-8')
        print(f'rewrote: {path}', file=sys.stderr)
    return True


def main() -> int:
    args = sys.argv[1:]
    check = False
    if args and args[0] == '--check':
        check = True
        args = args[1:]
    if not args:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    changed = 0
    for arg in args:
        if process(Path(arg), check):
            changed += 1
    if check and changed:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
