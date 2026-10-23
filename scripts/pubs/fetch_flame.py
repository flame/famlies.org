#!/usr/bin/env python3
"""Harvest the curated FLAME publication list (UT Austin) into cache/.

Parses https://www.cs.utexas.edu/~flame/web/FLAMEPublications.html for
title, authors, venue line, links (PDFs) and the BibTeX anchor, and
https://www.cs.utexas.edu/~flame/web/BibTeX.html for the BibTeX entries.
"""
import html
import json
import os
import re
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache')
BASE = 'https://www.cs.utexas.edu/~flame/web/'
UA = 'FAMLIES-publications/1.0 (https://famlies.org)'

# Links worth keeping (papers, drafts, slides); skips author homepages.
DOC_LINK = re.compile(r'\.(pdf|ps|gz|zip)\b|arxiv|doi\.org|pdf|postscript|draft|slides|'
                      r'download|abstract|paper|report|video|movie', re.I)

SECTIONS = {
    'PhD': 'thesis', 'Books': 'book', 'Journal': 'journal',
    'Chapters': 'chapter', 'Conference': 'conference',
    'FLAWNS': 'report', 'Demos': None, 'Other': 'other',
}


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', 'replace')


def text(s):
    s = re.sub(r'<!--.*?-->', ' ', s, flags=re.S)
    s = re.sub(r'<[^>]*>', ' ', s)
    return re.sub(r'\s+', ' ', html.unescape(s)).strip()


def parse_bibtex_page(page):
    entries = {}
    for m in re.finditer(r'<pre>\s*(@\w+\s*\{\s*([^,\s]+)\s*,.*?)</pre>', page, re.S):
        entries[m.group(2)] = html.unescape(m.group(1)).strip()
    return entries


def parse_pubs_page(page):
    # Split into sections at <a name="..."> anchors that start a section.
    marks = [(m.start(), m.group(1)) for m in
             re.finditer(r'<a name="(\w+)"\s*>\s*</a>', page)
             if m.group(1) in SECTIONS]
    marks.append((len(page), None))
    items = []
    for (start, sec), (end, _) in zip(marks, marks[1:]):
        kind = SECTIONS[sec]
        if kind is None:
            continue
        chunk = page[start:end]
        year = None
        # Year headers look like <font color="GREEN"> 2021 </font>
        pieces = re.split(r'(<font color="GREEN">\s*[^<]*?\s*</font>|<li\b)', chunk)
        cur = None
        for p in pieces:
            ym = re.match(r'<font color="GREEN">\s*(\d{4})', p or '')
            if ym:
                year = int(ym.group(1))
                continue
            if p == '<li':
                cur = ''
                continue
            if cur is None or not p:
                continue
            item = parse_item(p, kind, year)
            if item:
                items.append(item)
            cur = None
    return items


def parse_item(chunk, kind, year):
    div = re.search(r'<div>(.*?)</div>', chunk, re.S)
    body = div.group(1) if div else chunk
    lines = [l for l in re.split(r'<br\s*/?>', body)]
    if len(lines) < 2:
        return None
    first = lines[0]
    a = re.search(r'<a\s+href="([^"]*)"\s*>(.*?)</a>', first, re.S)
    title = text(a.group(2) if a else first).rstrip('.')
    if not title:
        return None
    url = a.group(1).strip() if a else ''
    authors = text(lines[1]).rstrip('.')
    venue = text(' '.join(lines[2:]))
    links = []
    for m in re.finditer(r'<a\s+href="([^"]*)"\s*>(.*?)</a>', chunk, re.S):
        href, label = m.group(1).strip(), text(m.group(2))
        if 'BibTeX.html' in href or href == url or not DOC_LINK.search(href + ' ' + label):
            continue
        links.append({'url': href, 'label': label})
    bib = re.search(r'BibTeX\.html#([^"\s,]+)', chunk)
    if year is None:
        ym = re.findall(r'\b(19[89]\d|20[0-3]\d)\b', venue)
        year = int(ym[-1]) if ym else None
    venue = re.sub(r'\[.*?\]', '', venue).strip(' ,')
    return {
        'kind': kind, 'year': year, 'title': title, 'url': url,
        'authors': authors, 'venue': venue, 'links': links,
        'bibkey': bib.group(1) if bib else None,
    }


def main():
    os.makedirs(CACHE, exist_ok=True)
    items = parse_pubs_page(get(BASE + 'FLAMEPublications.html'))
    bib = parse_bibtex_page(get(BASE + 'BibTeX.html'))
    for it in items:
        it['bibtex'] = bib.get(it['bibkey']) if it['bibkey'] else None
    json.dump({'items': items, 'bibtex': bib},
              open(os.path.join(CACHE, 'flame.json'), 'w'), indent=1)
    print(f'{len(items)} items, {len(bib)} BibTeX entries, '
          f'{sum(1 for i in items if i["bibtex"])} matched')


if __name__ == '__main__':
    main()
