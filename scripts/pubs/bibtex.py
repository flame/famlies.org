"""Minimal BibTeX reader/writer (brace-balanced, no external deps)."""
import re


def parse(text):
    """Return a list of {'type', 'key', 'fields', 'raw'} for each entry."""
    entries = []
    i = 0
    while True:
        m = re.compile(r'@(\w+)\s*([{(])').search(text, i)
        if not m:
            break
        etype = m.group(1).lower()
        open_ch = m.group(2)
        close_ch = '}' if open_ch == '{' else ')'
        j, depth = m.end(), 1
        while j < len(text) and depth:
            c = text[j]
            if c == open_ch or (open_ch == '{' and c == '{'):
                depth += 1
            elif c == close_ch or (open_ch == '{' and c == '}'):
                depth -= 1
            j += 1
        body = text[m.end():j - 1]
        raw = text[m.start():j]
        i = j
        if etype in ('comment', 'preamble', 'string'):
            continue
        key, _, rest = body.partition(',')
        entries.append({'type': etype, 'key': key.strip(),
                        'fields': parse_fields(rest), 'raw': raw.strip()})
    return entries


def parse_fields(s):
    fields, i, n = {}, 0, len(s)
    while i < n:
        m = re.compile(r'\s*([\w:-]+)\s*=\s*').match(s, i)
        if not m:
            break
        name, i = m.group(1).lower(), m.end()
        if i < n and s[i] == '{':
            depth, j = 1, i + 1
            while j < n and depth:
                depth += {'{': 1, '}': -1}.get(s[j], 0)
                j += 1
            val = s[i + 1:j - 1]
        elif i < n and s[i] == '"':
            j = i + 1
            while j < n and not (s[j] == '"' and s[j - 1] != '\\'):
                j += 1
            val, j = s[i + 1:j], j + 1
        else:
            m2 = re.compile(r'[^,]*').match(s, i)
            val, j = m2.group(0).strip(), m2.end()
        fields[name] = re.sub(r'\s+', ' ', val).strip()
        k = s.find(',', j)
        i = n if k < 0 else k + 1
    return fields


ACCENTS = {
    '"': dict(zip('aouei' 'AOU', 'äöüëï' 'ÄÖÜ')),
    "'": dict(zip('aeiounc' 'AEIOU', 'áéíóúńć' 'ÁÉÍÓÚ')),
    '`': dict(zip('aeiou', 'àèìòù')),
    '~': dict(zip('nao' 'N', 'ñãõ' 'Ñ')),
    '^': dict(zip('aeiou', 'âêîôû')),
    'c': {'c': 'ç', 'C': 'Ç'},
}


def detex(s):
    """Turn a BibTeX field value into plain text."""
    if not s:
        return ''
    # {\'e}, \'{e}, \'e, {\c c}, \c{c}
    s = re.sub(r'\\[ij]\b\s*', lambda m: m.group(0)[1], s)
    s = re.sub(r'\\(["\'`~^]|c(?=[\s{]))\s*\{?(\w)\}?',
               lambda m: ACCENTS[m.group(1).strip()].get(m.group(2), m.group(2)), s)
    s = re.sub(r'\\(tt|em|it|bf|sc|rm|sf|textit|textbf|textrm|emph|texttt|url)\b\s*', '', s)
    s = s.replace('~', ' ').replace('\\&', '&').replace('--', '–')
    s = re.sub(r'\\(.)', r'\1', s)
    s = re.sub(r'[{}$]', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def split_authors(s):
    out = []
    for a in re.split(r'\s+and\s+', detex(s)):
        a = a.strip()
        if not a or a.lower() == 'others':
            continue
        if ',' in a:
            last, first = [x.strip() for x in a.split(',', 1)]
            a = f'{first} {last}'.strip()
        out.append(a)
    return out


def escape(s):
    s = s.replace('&', r'\&').replace('%', r'\%').replace('#', r'\#')
    s = s.replace('_', r'\_')
    return s


def format_entry(etype, key, fields):
    width = max(len(k) for k in fields)
    lines = [f'@{etype}{{{key},']
    for k, v in fields.items():
        lines.append(f'  {k.ljust(width)} = {{{v}}},')
    lines.append('}')
    return '\n'.join(lines)
