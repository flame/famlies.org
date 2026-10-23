#!/usr/bin/env python3
"""Download all works of the FAMLIES PIs/co-PIs from OpenAlex into cache/.

Responses are cached per author ID; pass --refresh to re-download.
OpenAlex without an API key has a small shared daily budget, so the
script requests 200 works per page and only the fields we use.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, 'cache')
FIELDS = ','.join([
    'id', 'doi', 'title', 'publication_year', 'publication_date', 'type',
    'authorships', 'primary_location', 'locations', 'best_oa_location',
    'open_access', 'biblio', 'cited_by_count', 'ids', 'language', 'primary_topic', 'referenced_works', 'abstract_inverted_index',
])
UA = 'FAMLIES-publications/1.0 (https://famlies.org)'


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (401, 429, 503) and attempt < 4:
                print(f'  HTTP {e.code}: {e.read()[:200]!r}; retrying')
                time.sleep(10 * (attempt + 1))
                continue
            raise


def fetch_author(aid):
    # Page-number paging (cursor paging requires an API key).
    works, page_no = [], 1
    while True:
        q = urllib.parse.urlencode({
            'filter': f'author.id:{aid}', 'per_page': 200,
            'page': page_no, 'select': FIELDS,
        }, safe=':,')
        page = get('https://api.openalex.org/works?' + q)
        works += page['results']
        if len(works) >= page['meta']['count'] or not page['results']:
            return works
        page_no += 1
        time.sleep(1)


def main():
    refresh = '--refresh' in sys.argv
    os.makedirs(CACHE, exist_ok=True)
    people = json.load(open(os.path.join(HERE, 'people.json')))['people']
    for p in people:
        for aid in p['openalex']:
            path = os.path.join(CACHE, f'openalex_{aid}.json')
            if os.path.exists(path) and not refresh:
                print(f'{p["key"]:9s} {aid}: cached')
                continue
            works = fetch_author(aid)
            json.dump(works, open(path, 'w'))
            print(f'{p["key"]:9s} {aid}: {len(works)} works')


if __name__ == '__main__':
    main()
