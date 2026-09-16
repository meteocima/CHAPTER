#!/usr/bin/env python3
"""Minimal Markdown -> LaTeX -> PDF converter.

There is no pandoc on Leonardo, but xelatex is available and handles Unicode
natively (accents, arrows, Greek letters, math symbols) through fontspec +
DejaVu, so no fragile character mapping is needed.

Supported subset -- deliberately only what the CHAPTER documents use:
headings (#..####), paragraphs, bold, italic, inline code, fenced code blocks,
bullet and numbered lists, blockquotes, horizontal rules, and pipe tables.

Usage:  uv run python tools/md2pdf.py INPUT.md [OUTPUT.pdf]
"""
import os
import re
import subprocess
import sys
import tempfile

PREAMBLE = r"""\documentclass[10pt,a4paper]{article}
\usepackage{fontspec}
\usepackage[margin=2.2cm]{geometry}
\usepackage{longtable}
\usepackage{array}
\usepackage{booktabs}
\usepackage{enumitem}
\usepackage{parskip}
\usepackage[table]{xcolor}
\usepackage[hidelinks]{hyperref}
\setmainfont{DejaVu Sans}
\setmonofont{DejaVu Sans Mono}[Scale=0.85]
\definecolor{rule}{gray}{0.75}
\setlist[itemize]{leftmargin=1.2em,topsep=2pt,itemsep=1pt}
\setlist[enumerate]{leftmargin=1.5em,topsep=2pt,itemsep=1pt}
\renewcommand{\arraystretch}{1.25}
\setlength{\LTpre}{6pt}\setlength{\LTpost}{10pt}
\setcounter{secnumdepth}{0}
\begin{document}
"""

SPECIAL = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
           '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}',
           '~': r'\textasciitilde{}', '^': r'\textasciicircum{}',
           '|': r'\textbar{}'}


def esc(text):
    return ''.join(SPECIAL.get(c, c) for c in text)


def inline(text):
    """Escape LaTeX specials, then apply code / bold / italic / links.

    Code spans are lifted out first so their content stays verbatim, but they
    are replaced by placeholders rather than emitted immediately -- otherwise
    emphasis spanning a code span (**a `b` c**) would never match.
    """
    spans = []

    def lift(m):
        spans.append(r'\texttt{' + esc(m.group(1)) + '}')
        return '\x00%d\x00' % (len(spans) - 1)

    tmp = _markup(esc(re.sub(r'`([^`]+)`', lift, text)))
    return re.sub(r'\x00(\d+)\x00', lambda m: spans[int(m.group(1))], tmp)


def _markup(t):
    t = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\\href{\2}{\1}', t)
    t = re.sub(r'\*\*(.+?)\*\*', r'\\textbf{\1}', t)
    t = re.sub(r'(?<![\w*])\*([^*]+)\*(?![\w*])', r'\\emph{\1}', t)
    return t


def split_row(line):
    """Split on unescaped pipes only; a cell may contain a literal '|' as '\\|'."""
    body = re.sub(r'^\s*\|', '', line.strip())
    body = re.sub(r'(?<!\\)\|\s*$', '', body)
    cells = re.split(r'(?<!\\)\|', body)
    return [c.strip().replace('\\|', '|') for c in cells]


def table(rows):
    """rows[0] is the header; the separator row has already been dropped."""
    ncols = len(rows[0])          # the header defines the shape
    rows = [r[:ncols] + [''] * (ncols - len(r)) for r in rows]
    width = 0.96 / ncols
    spec = '|'.join([r'>{\raggedright\arraybackslash}p{%.4f\textwidth}' % width] * ncols)
    out = [r'\begin{longtable}{|%s|}' % spec, r'\hline']
    head = ' & '.join(r'\textbf{%s}' % inline(c) for c in rows[0])
    out += [head + r' \\', r'\hline', r'\endfirsthead',
            r'\hline', head + r' \\', r'\hline', r'\endhead']
    for r in rows[1:]:
        out.append(' & '.join(inline(c) for c in r) + r' \\')
        out.append(r'\hline')
    out.append(r'\end{longtable}')
    return out


def convert(md):
    lines = md.split('\n')
    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        if stripped.startswith('```'):            # fenced code block
            i += 1
            body = []
            while i < n and not lines[i].strip().startswith('```'):
                body.append(lines[i])
                i += 1
            i += 1
            out += [r'\begin{quote}\ttfamily\footnotesize\obeylines\obeyspaces']
            out += [esc(b) if b.strip() else r'\ ' for b in body]
            out += [r'\end{quote}']
            continue

        if re.match(r'^(-{3,}|\*{3,}|_{3,})$', stripped):
            out.append(r'\vspace{2pt}{\color{rule}\hrule}\vspace{6pt}')
            i += 1
            continue

        m = re.match(r'^(#{1,4})\s+(.*)$', stripped)
        if m:
            cmd = ['section', 'subsection', 'subsubsection', 'paragraph'][len(m.group(1)) - 1]
            out.append('\\%s{%s}' % (cmd, inline(m.group(2))))
            i += 1
            continue

        if stripped.startswith('|'):              # pipe table
            rows = []
            while i < n and lines[i].strip().startswith('|'):
                r = split_row(lines[i])
                if not all(re.match(r'^:?-{2,}:?$', c) for c in r if c):
                    rows.append(r)
                i += 1
            if rows:
                out += table(rows)
            continue

        if stripped.startswith('> '):             # blockquote
            body = []
            while i < n and lines[i].strip().startswith('>'):
                body.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out += [r'\begin{quote}\small', inline(' '.join(body)), r'\end{quote}']
            continue

        if re.match(r'^[-*+]\s+', stripped) or re.match(r'^\d+[.)]\s+', stripped):
            ordered = bool(re.match(r'^\d+[.)]\s+', stripped))
            env = 'enumerate' if ordered else 'itemize'
            out.append(r'\begin{%s}' % env)
            while i < n:
                s = lines[i].strip()
                m2 = re.match(r'^(?:[-*+]|\d+[.)])\s+(.*)$', s)
                if not m2:
                    if s and lines[i].startswith(('  ', '\t')):   # continuation
                        out.append(inline(s))
                        i += 1
                        continue
                    break
                out.append(r'\item ' + inline(m2.group(1)))
                i += 1
            out.append(r'\end{%s}' % env)
            continue

        para = []                                  # plain paragraph
        while i < n and lines[i].strip() and not re.match(
                r'^\s*(#{1,4}\s|\||>|```|[-*+]\s|\d+[.)]\s|-{3,}$)', lines[i]):
            para.append(lines[i].strip())
            i += 1
        out.append(inline(' '.join(para)))
    return PREAMBLE + '\n'.join(out) + '\n\\end{document}\n'


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    args = [a for a in sys.argv[1:] if a != '--tex']
    src = args[0]
    dst = args[1] if len(args) > 1 else os.path.splitext(src)[0] + '.pdf'
    with open(src, encoding='utf-8') as f:
        tex = convert(f.read())
    if '--tex' in sys.argv:          # dump the LaTeX and stop, for debugging
        sys.stdout.write(tex)
        return

    with tempfile.TemporaryDirectory() as tmp:
        texfile = os.path.join(tmp, 'doc.tex')
        with open(texfile, 'w', encoding='utf-8') as f:
            f.write(tex)
        for _ in range(2):        # twice, so longtable column widths settle
            proc = subprocess.run(['xelatex', '-interaction=nonstopmode',
                                   '-halt-on-error', 'doc.tex'],
                                  cwd=tmp, capture_output=True, text=True)
        log = os.path.join(tmp, 'doc.log')
        logtext = open(log, encoding='utf-8', errors='replace').read() if os.path.exists(log) else ''
        pdf = os.path.join(tmp, 'doc.pdf')
        if proc.returncode != 0 or not os.path.exists(pdf):
            sys.stderr.write(proc.stdout[-4000:] + '\n')
            sys.exit('xelatex failed on %s' % src)
        # A glyph the font cannot draw is dropped silently by TeX: surface it.
        missing = sorted(set(re.findall(r'Missing character: There is no (.) ', logtext)))
        if missing:
            sys.stderr.write('WARNING: glyphs missing from the font: %s\n' % ' '.join(missing))
        with open(pdf, 'rb') as f_in, open(dst, 'wb') as f_out:
            f_out.write(f_in.read())
    m = re.search(r'Output written on .*?\((\d+) pages?', logtext)
    print('%s -> %s (%.0f kB, %s pages)'
          % (src, dst, os.path.getsize(dst) / 1024, m.group(1) if m else '?'))


if __name__ == '__main__':
    main()
