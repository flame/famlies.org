#!/usr/bin/env python3
"""Find publications that acknowledge a FAMLIES grant.

For every publication in the database dated on or after the grant start year
that has a PDF link, download the PDF (into cache/pdf/), extract its text with
pdftotext, and look for any of the award numbers. Also asks OpenAlex's
full-text search for the award numbers. Results go to cache/grants.json
({openalex id or title: [award numbers found]}); build_db.py marks those
publications "famlies_grant". Settings: "famlies_grants" in curation.json
(hand-confirmed papers can be listed there under "acknowledged_titles").

Run after build_db.py, then run build_db.py again.
"""
import json
import os
import re
import subprocess
import time
import urllib.request

from fetch_openalex import get, CACHE, HERE, UA

PDF_DIR = os.path.join(CACHE, 'pdf')


def pdf_text(url, name):
    path = os.path.join(PDF_DIR, re.sub(r'[^\w.-]', '_', name)[:80] + '.pdf')
    if not os.path.exists(path):
        req = urllib.request.Request(url, headers={'User-Agent': UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data.startswith(b'%PDF'):
            raise ValueError('not a PDF')
        open(path, 'wb').write(data)
        time.sleep(1)
    out = subprocess.run(['pdftotext', '-q', path, '-'], capture_output=True, text=True)
    return out.stdout


def main():
    cfg = json.load(open(os.path.join(HERE, 'curation.json')))['famlies_grants']
    awards = cfg['award_ids']
    pat = re.compile(r'\b(' + '|'.join(awards) + r')\b')
    db = json.load(open(os.path.join(HERE, '..', '..', 'site', 'config', 'publications.json')))
    os.makedirs(PDF_DIR, exist_ok=True)
    path = os.path.join(CACHE, 'grants.json')
    found = json.load(open(path)) if os.path.exists(path) else {}

    # OpenAlex full-text search (covers only works whose full text OpenAlex has)
    for a in awards:
        res = get(f'https://api.openalex.org/works?filter=fulltext.search:{a}&select=id,title&per_page=50')
        for w in res['results']:
            k = w['id'].rsplit('/', 1)[-1]
            found.setdefault(k, [])
            if a not in found[k]:
                found[k].append(a)
        time.sleep(1)

    for p in db['publications']:
        if (p.get('year') or 0) < cfg['since'] or not p.get('pdf'):
            continue
        key = p.get('openalex') or p['title']
        try:
            hits = sorted(set(pat.findall(pdf_text(p['pdf'], p['key']))))
        except Exception as e:      # paywalled, HTML landing page, ...
            print(f'  skipped ({e}): {p["title"][:60]}')
            continue
        print(f'{"FOUND " + ",".join(hits) if hits else "no    "}  {p["title"][:70]}')
        if hits:
            found[key] = sorted(set(found.get(key, []) + hits))
    json.dump(found, open(path, 'w'), indent=1)
    print(f'{len(found)} works acknowledge a FAMLIES award (incl. ones outside the database)')


if __name__ == '__main__':
    main()
