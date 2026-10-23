#!/usr/bin/env python3
"""Collect OpenAlex IDs of FLAME/BLIS/PLAPACK-related papers by anyone.

build_db.py keeps a publication only if it is itself FLAME/BLIS/PLAPACK-related
or cites such a paper. Papers by the tracked people are recognized directly;
this script adds related papers by others (found by OpenAlex search, then
confirmed with the case-sensitive keyword test in curation.json), so that
citing e.g. a BLIS paper by AMD also counts. Writes cache/core.json.
"""
import json
import os
import re
import time
import urllib.parse

from fetch_openalex import get, CACHE, HERE

SELECT = 'id,title,abstract_inverted_index'


def abstract(w):
    inv = w.get('abstract_inverted_index') or {}
    pos = sorted((i, word) for word, idx in inv.items() for i in idx)
    return ' '.join(word for _, word in pos)


def main():
    cur = json.load(open(os.path.join(HERE, 'curation.json')))['relevance']
    kw = re.compile(cur['keywords'])
    core = {}
    for q in cur['openalex_queries']:
        url = 'https://api.openalex.org/works?' + urllib.parse.urlencode({
            'filter': f'title_and_abstract.search:{q}', 'per_page': 200, 'select': SELECT,
        }, safe=':,')
        found = 0
        for w in get(url)['results']:
            text = (w.get('title') or '') + ' ' + abstract(w)
            if kw.search(text):
                core[w['id'].rsplit('/', 1)[-1]] = w.get('title') or ''
                found += 1
        print(f'{q!r}: {found} confirmed')
        time.sleep(1)
    json.dump(core, open(os.path.join(CACHE, 'core.json'), 'w'), indent=1)
    print(f'{len(core)} core papers by anyone')


if __name__ == '__main__':
    main()
