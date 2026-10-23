#!/usr/bin/env python3
"""Build the FAMLIES PI publication database.

Inputs
  cache/openalex_*.json   from fetch_openalex.py
  cache/flame.json        from fetch_flame.py
  imports/*.bib           any BibTeX, e.g. Google Scholar profile exports
  ../../site/config/{fawns,related}.bib
  people.json, curation.json

Outputs
  ../../site/config/publications.json
  ../../site/config/publications.bib
"""
import datetime
import glob
import html
import json
import os
import re
import unicodedata

import bibtex

HERE = os.path.dirname(os.path.abspath(__file__))
SITE_CONFIG = os.path.join(HERE, '..', '..', 'site', 'config')
OUT_JSON = os.path.join(SITE_CONFIG, 'publications.json')
OUT_BIB = os.path.join(SITE_CONFIG, 'publications.bib')
# FAMLIES working-note BibTeX files (fawns.bib, related.bib) live next to the output.
FAMLIES_BIB_DIR = SITE_CONFIG

# Lower rank = preferred as the canonical version of a merged paper.
TYPE_RANK = {'journal': 0, 'conference': 1, 'book': 2, 'chapter': 3,
             'thesis': 4, 'report': 5, 'preprint': 6, 'other': 7, 'abstract': 8}
BIB_TYPE = {'journal': 'article', 'conference': 'inproceedings', 'book': 'book',
            'chapter': 'incollection', 'thesis': 'phdthesis', 'report': 'techreport',
            'preprint': 'misc', 'other': 'misc', 'abstract': 'misc'}
ABSTRACT_VENUES = re.compile(r'Symposium on Molecular Spectroscopy|Knowledge Bank|^mss$|AGUFM', re.I)
SOURCE_RANK = {'import': 0, 'famlies': 0, 'flame': 1, 'openalex': 2}


# ---------------------------------------------------------------- helpers

def clean(s):
    s = html.unescape(s or '')
    s = re.sub(r'<[^>]+>', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def norm_title(t):
    t = unicodedata.normalize('NFKD', t or '').encode('ascii', 'ignore').decode()
    t = t.lower()
    t = re.sub(r'flame working note\s*#?\s*\d+', ' ', t)
    t = re.sub(r'lapack working note\s*\d+\s*:?', ' ', t)
    return re.sub(r'[^a-z0-9]+', '', t)


def ascii_word(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode()
    return re.sub(r'[^A-Za-z]', '', s)


def last_name(name):
    parts = name.split()
    if not parts:
        return ''
    # keep particles: "van de Geijn", "Van Zee"
    i = len(parts) - 1
    while i > 0 and parts[i - 1].lower() in ('van', 'de', 'der', 'von', 'di', 'da', 'del', 'la', 'le'):
        i -= 1
    return ' '.join(parts[i:])


def doi_of(s):
    if not s:
        return ''
    m = re.search(r'(10\.\d{4,9}/[^\s"<>{}]+)', s)
    if not m:
        return ''
    d = m.group(1).rstrip('.').lower()
    return re.sub(r'/(abstract|full|pdf|epdf)$', '', d)


def arxiv_of(s):
    m = re.search(r'arxiv\.org/(?:abs|pdf)/([\w.\-/]+?)(?:v\d+)?(?:\.pdf)?$', s or '')
    return m.group(1) if m else ''


# ---------------------------------------------------------------- people

def load_people(coauthors=True):
    people = json.load(open(os.path.join(HERE, 'people.json')))['people']
    path = os.path.join(HERE, 'coauthors.json')
    if coauthors and os.path.exists(path):
        known = {i for p in people for i in p['openalex']}
        people += [p for p in json.load(open(path))['people'] if not set(p['openalex']) & known]
    for p in people:
        p['_re'] = [re.compile(x, re.I) for x in p['name_patterns']]
        GROUP[p['key']] = p.get('group', 'pi')
    return people


GROUP = {}   # person key -> 'pi' | 'collaborator'


def fold(s):
    return unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()


def pis_in(authors, people):
    found = []
    names = authors + [fold(a) for a in authors]
    for p in people:
        if any(r.search(a) for a in names for r in p['_re']):
            found.append(p['key'])
    return found


def tidy_authors(authors, people):
    """Flip 'Last, First', use canonical PI names, drop repeats."""
    out = []
    for a in authors:
        a = a.strip().rstrip('.,') if a.endswith(',') else a.strip()
        if a.count(',') == 1:
            last, first = [x.strip() for x in a.split(',')]
            a = f'{first} {last}'
        for p in people:
            if any(r.search(a) or r.search(fold(a)) for r in p['_re']):
                a = p['name']
                break
        if a and a not in out:
            out.append(a)
    return out


# ---------------------------------------------------------------- sources

def from_openalex(people, cur):
    recs, seen = [], set()
    skip_types = set(cur['exclude_openalex_types'])
    for p in people:
        for aid in p['openalex']:
            path = os.path.join(HERE, 'cache', f'openalex_{aid}.json')
            if not os.path.exists(path):
                continue
            for w in json.load(open(path)):
                if w['type'] in skip_types:
                    continue
                r = openalex_record(w)
                r['_harvested_for'] = p['key']
                if w['id'] in seen:
                    continue
                seen.add(w['id'])
                recs.append(r)
    # Relevant works of frequent coauthors (fetch_coauthors.py)
    path = os.path.join(HERE, 'cache', 'coauthor_works.json')
    if os.path.exists(path):
        for w in json.load(open(path)):
            if w['type'] in skip_types or w['id'] in seen:
                continue
            seen.add(w['id'])
            recs.append(openalex_record(w))
    return recs


def openalex_record(w):
    pl = w.get('primary_location') or {}
    src = pl.get('source') or {}
    venue = clean(src.get('display_name') or '')
    if venue in ('Medical Entomology and Zoology',):   # OpenAlex junk venue
        venue = ''
    stype = src.get('type') or ''
    t = w['type']
    title = clean(w.get('title'))
    if t == 'preprint':
        kind = 'preprint'
    elif t in ('conference-paper', 'proceedings-article') or stype == 'conference':
        kind = 'conference'
    elif t == 'article' and stype == 'journal':
        kind = 'journal'
    elif t == 'book':
        kind = 'book'
    elif t == 'book-chapter':
        kind = 'chapter'
    elif t == 'dissertation':
        kind = 'thesis'
    elif t == 'report' or re.search(r'working note|technical report', title, re.I):
        kind = 'report'
    elif t == 'conference-abstract':
        kind = 'abstract'
    elif t == 'article' and stype == 'repository':
        kind = 'report'
    else:
        kind = 'other'
    if venue.startswith('arXiv'):
        venue = 'arXiv preprint'
    if ABSTRACT_VENUES.search(venue):
        kind = 'abstract'
    if kind == 'report' and venue.startswith('arXiv'):
        kind = 'preprint'

    authors = [clean((a.get('author') or {}).get('display_name') or a.get('raw_author_name') or '')
               for a in w.get('authorships', [])]
    author_ids = [((a.get('author') or {}).get('id') or '').rsplit('/', 1)[-1]
                  for a in w.get('authorships', [])]
    pdf, arxiv, urls = '', '', []
    locs = [w.get('best_oa_location')] + (w.get('locations') or [])
    for loc in locs:
        if not loc:
            continue
        pdf = pdf or (loc.get('pdf_url') or '')
        for u in (loc.get('landing_page_url'), loc.get('pdf_url')):
            arxiv = arxiv or arxiv_of(u or '')
    if arxiv and not pdf:
        pdf = f'https://arxiv.org/pdf/{arxiv}'
    b = w.get('biblio') or {}
    doi = doi_of(w.get('doi'))
    if doi.startswith('10.48550/arxiv.'):
        arxiv = arxiv or doi.split('arxiv.', 1)[1]
    return {
        'source': 'openalex',
        'openalex': w['id'].rsplit('/', 1)[-1],
        'title': title,
        'authors': authors,
        'author_ids': author_ids,
        'year': w.get('publication_year'),
        'date': w.get('publication_date') or '',
        'type': kind,
        'venue': venue,
        'volume': b.get('volume') or '', 'issue': b.get('issue') or '',
        'pages': '–'.join(x for x in (b.get('first_page'), b.get('last_page')) if x),
        'doi': doi,
        'url': pl.get('landing_page_url') or (f'https://doi.org/{doi}' if doi else ''),
        'pdf': pdf,
        'arxiv': arxiv,
        'citations': w.get('cited_by_count') or 0,
        'oa': bool((w.get('open_access') or {}).get('is_oa')),
        'bibtex': '',
        'field': (((w.get('primary_topic') or {}).get('field')) or {}).get('display_name'),
        'refs': [u.rsplit('/', 1)[-1] for u in w.get('referenced_works') or []],
        '_abstract': inverted_abstract(w.get('abstract_inverted_index')),
    }


def inverted_abstract(inv):
    pos = sorted((i, word) for word, idx in (inv or {}).items() for i in idx)
    return ' '.join(word for _, word in pos)


def from_flame():
    path = os.path.join(HERE, 'cache', 'flame.json')
    if not os.path.exists(path):
        return []
    recs = []
    for it in json.load(open(path))['items']:
        authors = [a.strip() for a in re.split(r',\s*(?:and\s+)?|\s+and\s+', it['authors']) if a.strip()]
        pdf = next((l['url'] for l in it['links'] if re.search(r'\.pdf\b|arxiv', l['url'], re.I)), '')
        if not pdf and re.search(r'\.pdf$', it['url'] or '', re.I):
            pdf = it['url']
        extra = [l for l in it['links'] if l['url'] != pdf]
        url = it['url'] if it['url'] and it['url'] != pdf else ''
        kind = it['kind']
        rec = {
            'source': 'flame',
            'title': it['title'], 'authors': authors, 'year': it['year'],
            'date': '', 'type': kind, 'venue': it['venue'],
            'volume': '', 'issue': '', 'pages': '',
            'doi': doi_of(it['url']) or doi_of(it.get('bibtex') or ''),
            'url': url, 'pdf': pdf, 'arxiv': arxiv_of(pdf) or arxiv_of(url),
            'citations': 0, 'oa': bool(pdf),
            'bibtex': it.get('bibtex') or '',
            'links': [{'label': l['label'], 'url': l['url']} for l in extra],
        }
        recs.append(rec)
    return recs


def from_bibfiles():
    files = [(f, 'import') for f in sorted(glob.glob(os.path.join(HERE, 'imports', '*.bib')))]
    files += [(os.path.join(FAMLIES_BIB_DIR, n), 'famlies') for n in ('fawns.bib', 'related.bib')]
    recs = []
    for path, src in files:
        if not os.path.exists(path):
            continue
        for e in bibtex.parse(open(path, encoding='utf-8', errors='replace').read()):
            f = e['fields']
            et = e['type']
            venue = bibtex.detex(f.get('journal') or f.get('booktitle') or f.get('institution')
                                 or f.get('school') or f.get('publisher') or '')
            if et == 'article':
                kind = 'preprint' if re.search(r'arxiv|preprint', venue, re.I) else 'journal'
            elif et in ('inproceedings', 'conference'):
                kind = 'conference'
            elif et == 'book':
                kind = 'book'
            elif et in ('incollection', 'inbook'):
                kind = 'chapter'
            elif et in ('phdthesis', 'mastersthesis'):
                kind = 'thesis'
            elif et == 'techreport':
                kind = 'report'
            else:
                kind = 'preprint' if re.search(r'arxiv', venue + f.get('eprint', '') + f.get('howpublished', ''), re.I) else 'other'
            y = re.search(r'\d{4}', f.get('year', ''))
            url = f.get('url', '')
            pdf = f.get('pdf', '') or (url if re.search(r'\.pdf$', url, re.I) else '')
            arxiv = f.get('eprint', '') if 'arxiv' in (f.get('archiveprefix', '') + f.get('eprinttype', '')).lower() else arxiv_of(url)
            if arxiv and not pdf:
                pdf = f'https://arxiv.org/pdf/{arxiv}'
            recs.append({
                'source': src,
                'title': bibtex.detex(f.get('title', '')),
                'authors': bibtex.split_authors(f.get('author', '') or f.get('editor', '')),
                'year': int(y.group(0)) if y else None, 'date': '',
                'type': kind, 'venue': venue,
                'volume': f.get('volume', ''), 'issue': f.get('number', ''),
                'pages': f.get('pages', '').replace('--', '–'),
                'doi': doi_of(f.get('doi', '')),
                'url': url if url != pdf else '', 'pdf': pdf, 'arxiv': arxiv,
                'citations': 0, 'oa': bool(pdf),
                'bibtex': e['raw'],
                'abstract': bibtex.detex(f.get('abstract', '')),
            })
    return recs


# ---------------------------------------------------------------- filtering

def keep(rec, people, cur):
    if not rec['title'] or len(rec['title']) < 4:
        return False
    if any(re.search(x, rec['title'], re.I) for x in cur['exclude_titles']):
        return False
    rec['authors'] = tidy_authors(rec['authors'], people)
    # OpenAlex lists advisors as dissertation coauthors, in no reliable order;
    # keep only single-author ones (the FLAME list covers the group's dissertations).
    if rec['source'] == 'openalex' and rec['type'] == 'thesis' and len(rec['authors']) > 1:
        return False
    rec['pis'] = pis_in(rec['authors'], people)
    if not rec['pis']:
        return False
    who = rec.get('_harvested_for')
    if rec['source'] == 'openalex' and who:
        rules = dict(cur.get('group_rules', {}).get(GROUP[who], {}))
        rules.update(cur['person_rules'].get(who, {}))
        fields = rules.get('fields')
        if fields and rec.get('field') and rec['field'] not in fields and who in rec['pis']:
            rec['pis'].remove(who)
        forced = any(re.search(re.escape(x), rec['title'], re.I)
                     for x in cur['include_titles'].get(who, []))
        if not forced:
            if rec['year'] and rec['year'] < rules.get('min_year', 0):
                rec['pis'].remove(who) if who in rec['pis'] else None
            if rules.get('require_pi_coauthor') and not (set(rec['pis']) - {who}):
                rec['pis'].remove(who) if who in rec['pis'] else None
        if not rec['pis']:
            return False
    return True


# ---------------------------------------------------------------- merging

def merge_groups(recs, merges=()):
    parent = list(range(len(recs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        parent[find(i)] = find(j)

    by_key = {}
    for i, r in enumerate(recs):
        nt = norm_title(r['title'])
        keys = []
        if r['doi']:
            keys.append('doi:' + r['doi'])
        if r['arxiv']:
            keys.append('arxiv:' + r['arxiv'])
        if len(nt) >= 25:
            keys.append('t:' + nt)
        elif nt:
            keys.append(f't:{nt}:{r["year"]}')
        for k in keys:
            if k in by_key:
                union(i, by_key[k])
            else:
                by_key[k] = i
    # Hand-listed groups of titles that are the same paper.
    for titles in merges:
        idx = [i for i, r in enumerate(recs)
               if any(norm_title(r['title']) == norm_title(t) for t in titles)]
        for i in idx[1:]:
            union(i, idx[0])
    # Truncated titles / added subtitles: one title a prefix of another.
    nts = sorted((norm_title(r['title']).rstrip('s'), i) for i, r in enumerate(recs))
    for (a, i), (b, j) in zip(nts, nts[1:]):
        if len(a) >= 30 and b.startswith(a) and abs((recs[i]['year'] or 0) - (recs[j]['year'] or 0)) <= 2:
            union(i, j)
    groups = {}
    for i in range(len(recs)):
        groups.setdefault(find(i), []).append(recs[i])
    return list(groups.values())


def combine(group):
    def rank(r):
        return (TYPE_RANK[r['type']], SOURCE_RANK[r['source']], -(r['citations'] or 0))
    group = sorted(group, key=rank)
    main = dict(group[0])
    pis = []
    for r in group:
        pis += [p for p in r['pis'] if p not in pis]
    main['pis'] = pis
    # FLAME venue lines carry free-form notes; use OpenAlex's structured venue when available.
    oa = next((r for r in group if r['source'] == 'openalex' and r['type'] == main['type'] and r['venue']), None)
    if main['source'] == 'flame' and oa:
        for f in ('venue', 'volume', 'issue', 'pages'):
            main[f] = oa[f]
    for f in ('doi', 'pdf', 'arxiv', 'url', 'venue', 'volume', 'issue', 'pages', 'date', 'abstract'):
        if not main.get(f):
            main[f] = next((r[f] for r in group if r.get(f)), '')
    if not main.get('year'):
        main['year'] = next((r['year'] for r in group if r['year']), None)
    # Longest author list wins (FLAME list sometimes abbreviates), except for
    # dissertations, whose only author is the student.
    if main['type'] != 'thesis' and main['source'] != 'import' and \
            len(main['authors']) < max(len(r['authors']) for r in group):
        main['authors'] = max((r['authors'] for r in group), key=len)
    main['citations'] = max(r['citations'] or 0 for r in group)
    main['oa'] = any(r['oa'] for r in group) or bool(main['pdf'])
    main['openalex'] = next((r['openalex'] for r in group if r.get('openalex')), '')
    # Curated BibTeX (Scholar/FAMLIES/FLAME) for the canonical version if one exists.
    same = [r for r in group if r['bibtex'] and r['type'] == main['type']]
    main['bibtex'] = same[0]['bibtex'] if same else main.get('bibtex', '')
    main['sources'] = sorted({r['source'] for r in group})
    main['_text'] = ' '.join(' '.join((r['title'], r['venue'], r.get('_abstract', ''), r.get('abstract', '')))
                             for r in group)
    main['_refs'] = {x for r in group for x in r.get('refs', [])}
    main['_oaids'] = {r['openalex'] for r in group if r.get('openalex')}
    # Other versions (preprint, working note, conference version, ...)
    versions, seen = [], set()
    for r in group:
        lab = version_label(r)
        link = r['pdf'] or r['url'] or (f'https://doi.org/{r["doi"]}' if r['doi'] else '')
        if not link or link in seen or r is group[0]:
            seen.add(link)
            continue
        seen.add(link)
        # The canonical record already links its arXiv preprint.
        if main['arxiv'] and (r['arxiv'] == main['arxiv'] or arxiv_of(link) == main['arxiv']):
            continue
        if any(v['label'] == lab for v in versions):
            continue
        versions.append({'label': lab, 'url': link})
    links = []
    for r in group:
        for l in r.get('links', []):
            if l['url'] not in seen:
                seen.add(l['url'])
                links.append(l)
    main['versions'] = versions
    main['links'] = links
    return main


def version_label(r):
    names = {'journal': 'Journal', 'conference': 'Conference', 'book': 'Book', 'chapter': 'Chapter',
             'thesis': 'Thesis', 'report': 'Report', 'preprint': 'Preprint', 'other': 'Version',
             'abstract': 'Abstract'}
    lab = names[r['type']]
    m = re.search(r'(FLAME|LAPACK) Working Note\s*#?\s*\d+', r['venue'] + ' ' + r['title'], re.I)
    if m:
        lab = m.group(0)
    elif r['arxiv']:
        lab = 'arXiv'
    if r['year']:
        lab += f' ({r["year"]})'
    return lab


# ---------------------------------------------------------------- relevance

def relevant(pubs, rel, people):
    """Keep FLAME/BLIS/PLAPACK-related papers and papers citing one."""
    kw = re.compile(rel['keywords'])
    forced = [re.compile(re.escape(t), re.I) for t in rel.get('keep_titles', [])]
    core_path = os.path.join(HERE, 'cache', 'core.json')
    core_ids = set(json.load(open(core_path))) if os.path.exists(core_path) else set()
    for r in pubs:
        r['_core'] = bool(set(r['sources']) & set(rel['core_sources'])) or bool(kw.search(r['_text'])) \
            or any(f.search(r['title']) for f in forced)
        if r['_core']:
            core_ids |= r['_oaids']
    json.dump(sorted(core_ids), open(os.path.join(HERE, 'cache', 'core_ids.json'), 'w'))
    exempt = {k for k, g in GROUP.items() if g in rel.get('exempt_groups', [])}
    kept = []
    for r in pubs:
        if r['_core']:
            r['relation'] = 'related'
        elif set(r['pis']) & exempt:
            r['relation'] = 'famlies'
        elif r['_refs'] & core_ids:
            r['relation'] = 'cites'
        else:
            continue
        kept.append(r)
    return kept


def mark_famlies(pubs, cfg):
    """Set r['famlies'] for the 'FAMLIES Related' button."""
    kw = re.compile(cfg['keywords'])
    guarded = [(re.compile(g['pattern']), re.compile(g['requires'])) for g in cfg.get('guarded', [])]
    core_ids = set()
    for r in pubs:
        t = r['_text']
        listed = bool(set(r['sources']) & set(cfg['sources'])) and \
            not any(x.lower() in r['title'].lower() for x in cfg.get('not_core_titles', []))
        r['_fam_core'] = listed or bool(kw.search(t)) \
            or any(p.search(t) and req.search(t) for p, req in guarded)
        if r['_fam_core']:
            core_ids |= r['_oaids']
    for r in pubs:
        r['famlies'] = r['_fam_core'] or bool(set(r['pis']) & set(cfg['people'])) \
            or bool(r['_refs'] & core_ids)


def mark_grants(pubs, cfg):
    """Set r['grant'] for papers acknowledging a FAMLIES award (check_grants.py)."""
    path = os.path.join(HERE, 'cache', 'grants.json')
    found = json.load(open(path)) if os.path.exists(path) else {}
    titles = [t.lower() for t in cfg.get('acknowledged_titles', [])]
    for r in pubs:
        r['grant'] = bool(r['_oaids'] & set(found)) or r['title'] in found \
            or any(t in r['title'].lower() for t in titles)
        if r['grant']:
            r['famlies'] = True


# ---------------------------------------------------------------- BibTeX

def make_bibtex(r, used):
    first = ascii_word(last_name(r['authors'][0])) if r['authors'] else 'Anon'
    word = next((ascii_word(w) for w in r['title'].split()
                 if len(ascii_word(w)) > 3 and w.lower() not in ('with', 'from', 'towards', 'toward', 'using')), 'paper')
    key = f'{first}{r["year"] or ""}{word}'.replace(' ', '')
    base, n = key, 1
    while key in used:
        n += 1
        key = f'{base}{chr(ord("a") + n - 2)}'
    used.add(key)
    et = BIB_TYPE[r['type']]
    f = {'author': ' and '.join(r['authors']), 'title': '{' + bibtex.escape(r['title']) + '}'}
    v = bibtex.escape(r['venue'])
    if r['type'] == 'journal':
        f['journal'] = v
    elif r['type'] in ('conference', 'chapter'):
        f['booktitle'] = v
    elif r['type'] == 'thesis':
        f['school'] = v
    elif r['type'] == 'report':
        f['institution'] = v
    elif r['type'] == 'book':
        f['publisher'] = v
    elif v and not r['arxiv']:
        f['howpublished'] = v
    for k, src in (('volume', 'volume'), ('number', 'issue'), ('pages', 'pages')):
        if r.get(src):
            f[k] = r[src].replace('–', '--')
    if r['year']:
        f['year'] = str(r['year'])
    if r['doi']:
        f['doi'] = r['doi']
    if r['arxiv']:
        f['eprint'] = r['arxiv']
        f['archiveprefix'] = 'arXiv'
    if r['url'] and not r['doi']:
        f['url'] = r['url']
    f = {k: v for k, v in f.items() if v}
    return key, bibtex.format_entry(et, key, f)


# ---------------------------------------------------------------- main

def main():
    people = load_people()
    cur = json.load(open(os.path.join(HERE, 'curation.json')))
    raw = from_openalex(people, cur) + from_flame() + from_bibfiles()
    kept = [r for r in raw if keep(r, people, cur)]
    pubs = [combine(g) for g in merge_groups(kept, cur.get('merge', []))]
    for r in pubs:
        if r['type'] == 'thesis':
            r['pis'] = pis_in(r['authors'], people)
    n_all = len(pubs)
    pubs = relevant(pubs, cur['relevance'], people)
    mark_famlies(pubs, cur['famlies_related'])
    mark_grants(pubs, cur['famlies_grants'])

    used = set()
    for r in pubs:
        if r['bibtex']:
            m = re.match(r'@\w+\s*\{\s*([^,\s]+)', r['bibtex'])
            r['key'] = m.group(1) if m else ''
            if r['key'] in used:
                r['bibtex'] = ''
            else:
                used.add(r['key'])
        if not r['bibtex']:
            r['key'], r['bibtex'] = make_bibtex(r, used)

    pubs.sort(key=lambda r: (-(r['year'] or 0), r['title'].lower()))
    out = []
    for r in pubs:
        out.append({k: r[k] for k in (
            'key', 'title', 'authors', 'year', 'type', 'venue', 'volume', 'issue', 'pages',
            'doi', 'url', 'pdf', 'arxiv', 'citations', 'oa', 'pis', 'sources',
            'versions', 'links', 'bibtex', 'openalex', 'relation', 'famlies', 'grant') if r.get(k) not in (None, '', [], False)}
                   | ({'abstract': r['abstract']} if r.get('abstract') else {}))
    db = {
        'generated': datetime.date.today().isoformat(),
        'sources': sorted({src for r in out for src in r['sources']}),
        'people': [{k: p[k] for k in ('key', 'name', 'short', 'group', 'role', 'institution', 'orcid', 'scholar')}
                   for p in people],
        'publications': out,
    }
    json.dump(db, open(OUT_JSON, 'w'), ensure_ascii=False, separators=(',', ':'))
    with open(OUT_BIB, 'w') as fh:
        fh.write(f'% FAMLIES PI/co-PI publications, generated {db["generated"]}\n\n')
        fh.write('\n\n'.join(r['bibtex'] for r in out) + '\n')
    counts = {p['name']: sum(p['key'] in r['pis'] for r in out) for p in people}
    print(f'FAMLIES related: {sum(1 for r in out if r.get("famlies"))}, '
          f'acknowledging a FAMLIES award: {[r["title"][:50] for r in out if r.get("grant")]}')
    print(f'{len(raw)} raw records -> {len(kept)} kept -> {n_all} publications -> '
          f'{len(out)} FLAME/BLIS/PLAPACK-related or citing ('
          f'{sum(r["relation"] == "related" for r in out)} related, '
          f'{sum(r["relation"] == "cites" for r in out)} citing)')
    print('per person:', counts)


if __name__ == '__main__':
    main()
