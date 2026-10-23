#!/usr/bin/env python3
"""Download the FLAME/BLIS/PLAPACK-relevant works of the frequent coauthors.

Frequent coauthors (coauthors.json) have thousands of works between them, but
build_db.py keeps only works that mention FLAME/BLIS/PLAPACK or cite a core
paper. So instead of whole profiles this fetches, for all coauthors at once,
the works that cite a core paper (cache/core_ids.json, written by build_db.py)
or match the keyword searches in curation.json. Writes cache/coauthor_works.json.
"""
import json
import os
import time
import urllib.parse

from fetch_openalex import get, CACHE, FIELDS, HERE


def fetch_all(filt, search=None):
    works, page_no = [], 1
    while True:
        params = {'filter': filt, 'per_page': 200, 'page': page_no, 'select': FIELDS}
        if search:
            params['filter'] += f',title_and_abstract.search:{search}'
        page = get('https://api.openalex.org/works?' + urllib.parse.urlencode(params, safe=':,|'))
        works += page['results']
        if len(works) >= page['meta']['count'] or not page['results']:
            return works
        page_no += 1
        time.sleep(1)


def main():
    people = json.load(open(os.path.join(HERE, 'coauthors.json')))['people']
    rel = json.load(open(os.path.join(HERE, 'curation.json')))['relevance']
    core = json.load(open(os.path.join(CACHE, 'core_ids.json')))
    ids = [i for p in people for i in p['openalex']]
    authors = 'author.id:' + '|'.join(ids)
    found = {}
    for k in range(0, len(core), 50):
        for w in fetch_all(f'{authors},cites:' + '|'.join(core[k:k + 50])):
            found[w['id']] = w
        print(f'cites batch {k // 50 + 1}: {len(found)} works so far')
        time.sleep(1)
    for q in rel['openalex_queries']:
        for w in fetch_all(authors, q):
            found[w['id']] = w
        print(f'search {q!r}: {len(found)} works so far')
        time.sleep(1)
    json.dump(list(found.values()), open(os.path.join(CACHE, 'coauthor_works.json'), 'w'))
    print(f'{len(found)} coauthor works')


if __name__ == '__main__':
    main()
