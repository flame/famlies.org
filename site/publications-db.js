// FAMLIES PI publications database page.
// Data: config/publications.json (built by scripts/pubs/build_db.py).
// View state lives in the URL hash so filtered views can be linked to.

(function () {
    'use strict';

    const DATA_URL = 'config/publications.json';
    const PAGE = 150;           // items rendered before "Show all"

    const TYPES = [
        ['journal', 'Journal article'],
        ['conference', 'Conference paper'],
        ['book', 'Book'],
        ['chapter', 'Book chapter'],
        ['thesis', 'Dissertation / thesis'],
        ['report', 'Report / working note'],
        ['preprint', 'Preprint'],
        ['abstract', 'Abstract / talk'],
        ['other', 'Other'],
    ];
    const TYPE_LABEL = Object.fromEntries(TYPES);
    const TYPE_SHORT = {
        journal: 'Journal', conference: 'Conference', book: 'Book', chapter: 'Chapter',
        thesis: 'Dissertation', report: 'Report', preprint: 'Preprint', abstract: 'Abstract', other: 'Other',
    };

    const DEFAULTS = {
        q: '', ft: '', fa: '', fv: '', core: true, scope: 'related', people: [], mode: 'any', joint: false, types: [],
        from: '', to: '', venue: '', pdf: false,
        group: 'auto', sort: 'new', view: 'list',
    };

    let DB = null;          // {generated, people, publications}
    let PEOPLE = {};        // key -> person
    let state = { ...DEFAULTS };
    let limit = PAGE;
    let current = [];       // filtered, sorted publications

    const $ = (id) => document.getElementById(id);

    // ------------------------------------------------------------ utils

    function esc(s) {
        return String(s == null ? '' : s)
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    }

    function fold(s) {
        return String(s || '').normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase();
    }

    function safeUrl(u) {
        return /^https?:\/\//i.test(u || '') ? u : '';
    }

    function download(name, text, type) {
        const blob = new Blob([text], { type });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = name;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
    }

    function copy(text, btn) {
        const done = () => {
            const old = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = old; }, 1500);
        };
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
        } else {
            fallbackCopy(text, done);
        }
    }

    function fallbackCopy(text, done) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        try { document.execCommand('copy'); done(); } catch (e) { /* ignore */ }
        ta.remove();
    }

    // ------------------------------------------------------------ URL state

    function readHash() {
        const h = new URLSearchParams(location.hash.slice(1));
        const s = { ...DEFAULTS };
        ['q', 'ft', 'fa', 'fv'].forEach((k) => { if (h.has(k)) s[k] = h.get(k); });
        if (h.has('pi')) s.people = h.get('pi').split(',').filter((k) => PEOPLE[k]);
        if (h.get('mode') === 'all') s.mode = 'all';
        if (h.get('joint') === '1') s.joint = true;
        if (h.has('core')) s.core = h.get('core') !== '0';
        if (['only', 'related', 'all'].includes(h.get('scope'))) s.scope = h.get('scope');
        if (h.has('type')) s.types = h.get('type').split(',').filter((t) => TYPE_LABEL[t]);
        if (/^\d{4}$/.test(h.get('from') || '')) s.from = h.get('from');
        if (/^\d{4}$/.test(h.get('to') || '')) s.to = h.get('to');
        if (h.has('venue')) s.venue = h.get('venue');
        if (h.get('pdf') === '1') s.pdf = true;
        if (['auto', 'year', 'type', 'person', 'venue', 'none'].includes(h.get('group'))) s.group = h.get('group');
        if (SORTS[h.get('sort')]) s.sort = h.get('sort');
        if (h.get('view') === 'table') s.view = 'table';
        return s;
    }

    function writeHash() {
        const h = new URLSearchParams();
        ['q', 'ft', 'fa', 'fv'].forEach((k) => { if (state[k]) h.set(k, state[k]); });
        if (state.people.length) h.set('pi', state.people.join(','));
        if (state.mode !== 'any') h.set('mode', state.mode);
        if (state.joint) h.set('joint', '1');
        if (state.core !== DEFAULTS.core) h.set('core', state.core ? '1' : '0');
        if (state.scope !== DEFAULTS.scope) h.set('scope', state.scope);
        if (state.types.length) h.set('type', state.types.join(','));
        if (state.from) h.set('from', state.from);
        if (state.to) h.set('to', state.to);
        if (state.venue) h.set('venue', state.venue);
        if (state.pdf) h.set('pdf', '1');
        if (state.group !== DEFAULTS.group) h.set('group', state.group);
        if (state.sort !== DEFAULTS.sort) h.set('sort', state.sort);
        if (state.view !== DEFAULTS.view) h.set('view', state.view);
        const str = h.toString();
        history.replaceState(null, '', str ? '#' + str : location.pathname + location.search);
    }

    // ------------------------------------------------------------ filtering

    function matches(p, s, ignoreYears) {
        if (s.people.length) {
            const hit = s.mode === 'all'
                ? s.people.every((k) => p.pis.includes(k))
                : s.people.some((k) => p.pis.includes(k));
            if (!hit) return false;
        }
        if (s.joint && p._piCount < 2) return false;
        if (s.core && !p._core) return false;
        if (s.scope === 'related' && !p.famlies) return false;
        if (s.scope === 'only' && !p.grant) return false;
        if (s.types.length && !s.types.includes(p.type)) return false;
        if (s.pdf && !p.pdf) return false;
        if (s.venue && (p.venue || '') !== s.venue) return false;
        if (!ignoreYears) {
            if (s.from && (!p.year || p.year < +s.from)) return false;
            if (s.to && (!p.year || p.year > +s.to)) return false;
        }
        if (s.q && !hasAll(p._hay, s.q)) return false;
        if (s.ft && !hasAll(p._t, s.ft)) return false;
        if (s.fa && !hasAll(p._a, s.fa)) return false;
        if (s.fv && !hasAll(p._v, s.fv)) return false;
        return true;
    }

    function hasAll(hay, query) {
        return fold(query).split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
    }

    const SORTS = {
        new: (a, b) => (b.year || 0) - (a.year || 0) || a.title.localeCompare(b.title),
        old: (a, b) => (a.year || 9999) - (b.year || 9999) || a.title.localeCompare(b.title),
        cited: (a, b) => (b.citations || 0) - (a.citations || 0) || (b.year || 0) - (a.year || 0),
        'cited-asc': (a, b) => (a.citations || 0) - (b.citations || 0) || (b.year || 0) - (a.year || 0),
        title: (a, b) => a._sortTitle.localeCompare(b._sortTitle),
        venue: (a, b) => (a.venue || '~').localeCompare(b.venue || '~') || (b.year || 0) - (a.year || 0),
        type: (a, b) => a._typeRank - b._typeRank || (b.year || 0) - (a.year || 0),
    };

    // ------------------------------------------------------------ rendering

    function authorsHtml(p) {
        // Bold only the Core Team (PIs, co-PIs and FAMLIES staff).
        const names = new Set(p.pis.filter((k) => ['pi', 'staff'].includes(PEOPLE[k].group))
            .map((k) => PEOPLE[k].name));
        return p.authors.map((a) => (names.has(a) ? `<b>${esc(a)}</b>` : esc(a))).join(', ');
    }

    function venueLine(p) {
        let v = p.venue || '';
        const bits = [];
        if (p.volume) bits.push(p.issue ? `${p.volume}(${p.issue})` : p.volume);
        if (p.pages) bits.push(p.pages);
        if (bits.length && v) v += ', ' + bits.join(', ');
        return [v, p.year].filter(Boolean).join(', ');
    }

    function mainUrl(p) {
        if (p.doi) return 'https://doi.org/' + p.doi;
        return safeUrl(p.url) || safeUrl(p.pdf);
    }

    function scholarUrl(p) {
        return 'https://scholar.google.com/scholar?q=' + encodeURIComponent('"' + p.title + '"');
    }

    function apa(p) {
        const names = p.authors.map((a) => {
            const parts = a.split(/\s+/);
            if (parts.length < 2) return a;
            let i = parts.length - 1;
            while (i > 0 && /^(van|de|der|von|di|da|del|la|le)$/i.test(parts[i - 1])) i--;
            const last = parts.slice(i).join(' ');
            const init = parts.slice(0, i).map((n) => n[0].toUpperCase() + '.').join(' ');
            return init ? `${last}, ${init}` : last;
        });
        let au;
        if (names.length <= 1) au = names[0] || '';
        else if (names.length === 2) au = names.join(' & ');
        else au = names.slice(0, -1).join(', ') + ', & ' + names[names.length - 1];
        let s = `${au} (${p.year || 'n.d.'}). ${p.title}.`;
        if (p.venue) {
            s += ` ${p.venue}`;
            if (p.volume) s += `, ${p.volume}${p.issue ? `(${p.issue})` : ''}`;
            if (p.pages) s += `, ${p.pages}`;
            s += '.';
        }
        if (p.doi) s += ` https://doi.org/${p.doi}`;
        return s;
    }

    // Small buttons under each entry: PDF, DOI, arXiv, other versions, Scholar, Cite.
    function linksHtml(p, i) {
        const out = [];
        const link = (u, label, title) => out.push(
            `<a class="pp-btn" href="${esc(u)}" target="_blank" rel="noopener"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</a>`);
        const pdf = safeUrl(p.pdf);
        if (pdf) link(pdf, 'PDF');
        if (p.doi) link('https://doi.org/' + p.doi, 'DOI');
        if (p.arxiv) link('https://arxiv.org/abs/' + p.arxiv, 'arXiv');
        const url = safeUrl(p.url);
        if (url && !p.doi && url !== pdf) link(url, 'Web');
        (p.versions || []).concat(p.links || []).forEach((v) => {
            const u = safeUrl(v.url);
            if (u) link(u, v.label);
        });
        link(scholarUrl(p), 'Scholar', 'Search for this paper on Google Scholar');
        out.push(`<button type="button" class="pp-btn" data-cite="${i}" aria-expanded="false" title="BibTeX and APA citation">Cite</button>`);
        return out.join('');
    }

    // One flowing line: Authors. Title. Venue, year.
    function itemHtml(p, i, n) {
        const url = mainUrl(p);
        const title = url
            ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(p.title)}</a>`
            : esc(p.title);
        const venue = venueLine(p);
        const byImpact = state.sort === 'cited' || state.sort === 'cited-asc';
        const cites = byImpact ? ` <span class="pp-cites">(cited by ${p.citations || 0})</span>` : '';
        const end = (t) => (/[.?!]$/.test(t) ? '' : '.');
        return `
        <li value="${n}" class="pp-entry">
            <div class="pp-ref"><span class="pp-authors">${authorsHtml(p)}</span>.
                <span class="pp-title">${title}</span>${end(p.title)}
                ${venue ? `<span class="pp-venue">${esc(venue)}</span>.` : ''}${cites}</div>
            <div class="pp-links">${linksHtml(p, i)}</div>
            <div class="cite-panel" id="pp-cite-${i}" hidden></div>
        </li>`;
    }

    function citePanelHtml(p) {
        return `
            <div class="cite-tabs">
                <button type="button" class="cite-tab active" data-format="bibtex">BibTeX</button>
                <button type="button" class="cite-tab" data-format="apa">APA</button>
            </div>
            <div class="cite-content" data-format="bibtex">
                <pre>${esc(p.bibtex)}</pre>
                <button type="button" class="copy-btn" data-copy="bibtex">Copy</button>
            </div>
            <div class="cite-content" data-format="apa" hidden>
                <p>${esc(apa(p))}</p>
                <button type="button" class="copy-btn" data-copy="apa">Copy</button>
            </div>`;
    }

    function effGroup() {
        if (state.view === 'table') return 'none';
        if (state.group !== 'auto') return state.group;
        return { new: 'year', old: 'year', type: 'type', venue: 'venue' }[state.sort] || 'none';
    }

    function groupKeys(p) {
        switch (effGroup()) {
            case 'year': return [p.year ? String(p.year) : 'Undated'];
            case 'type': return [TYPE_LABEL[p.type]];
            case 'person': return p.pis.filter((k) => !state.people.length || state.people.includes(k))
                .map((k) => PEOPLE[k].name);
            case 'venue': return [p.venue || 'Venue unknown'];
            default: return [''];
        }
    }

    function groupOrder(a, b) {
        const g = effGroup();
        if (g === 'year') {
            const ya = a === 'Undated' ? -1 : +a, yb = b === 'Undated' ? -1 : +b;
            return state.sort === 'old' ? (ya < 0 ? 1 : yb < 0 ? -1 : ya - yb) : yb - ya;
        }
        if (g === 'type') {
            return TYPES.findIndex((t) => t[1] === a) - TYPES.findIndex((t) => t[1] === b);
        }
        if (g === 'person') {
            const order = DB.people.map((p) => p.name);
            return order.indexOf(a) - order.indexOf(b);
        }
        return 0;
    }

    // Newest first counts down (oldest paper is 1), as on the FLAME page.
    function number(i) {
        return state.sort === 'new' ? current.length - i : i + 1;
    }

    function renderResults() {
        const box = $('pp-results');

        if (!current.length) {
            box.innerHTML = '<p class="pp-empty">No publications match these filters.</p>';
            return;
        }
        if (state.view === 'table') {
            renderTable(box);
            return;
        }
        // Build groups, preserving sort order inside each group.
        const groups = new Map();
        current.forEach((p, i) => {
            groupKeys(p).forEach((g) => {
                if (!groups.has(g)) groups.set(g, []);
                groups.get(g).push(i);
            });
        });
        let keys = [...groups.keys()];
        if (effGroup() === 'venue') {
            keys.sort((a, b) => groups.get(b).length - groups.get(a).length || a.localeCompare(b));
        } else {
            keys.sort(groupOrder);
        }
        let shown = 0;
        const html = [];
        for (const g of keys) {
            if (shown >= limit) break;
            const idx = groups.get(g);
            const take = idx.slice(0, Math.max(0, limit - shown));
            shown += take.length;
            html.push(`<section class="pp-group">${g ? `<h2 class="pp-group-title">${esc(g)} <span>${idx.length}</span></h2>` : ''}
                <ol class="pp-list">${take.map((i) => itemHtml(current[i], i, number(i))).join('')}</ol></section>`);
        }
        const total = [...groups.values()].reduce((n, v) => n + v.length, 0);
        if (shown < total) {
            html.push(`<button type="button" class="cite-btn pp-more" id="pp-more">Show all ${total} entries</button>`);
        }
        box.innerHTML = html.join('');
    }

    function renderTable(box) {
        const cols = [
            ['year', 'Year', 'new'], ['title', 'Title', 'title'], [null, 'Authors', null],
            ['venue', 'Venue', 'venue'], ['type', 'Type', 'type'], ['cited', 'Impact', 'cited'], [null, 'Links', null],
        ];
        const head = cols.map(([k, label, sort]) => {
            let aria = '';
            const on = state.sort === sort || (k === 'year' && state.sort === 'old') || (k === 'cited' && state.sort === 'cited-asc');
            if (sort && on) {
                aria = ` aria-sort="${['old', 'cited-asc', 'title', 'venue', 'type'].includes(state.sort) ? 'ascending' : 'descending'}"`;
            }
            return `<th${sort ? ` data-sort="${sort}" tabindex="0"` : ''}${aria}>${label}</th>`;
        }).join('');
        const rows = current.slice(0, limit).map((p, i) => {
            const url = mainUrl(p);
            const links = [];
            if (safeUrl(p.pdf)) links.push(`<a href="${esc(p.pdf)}" target="_blank" rel="noopener">PDF</a>`);
            if (p.doi) links.push(`<a href="https://doi.org/${esc(p.doi)}" target="_blank" rel="noopener">DOI</a>`);
            links.push(`<a href="#" data-bib="${i}">BibTeX</a>`);
            return `<tr>
                <td class="num">${p.year || ''}</td>
                <td class="pp-title-cell">${url ? `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(p.title)}</a>` : esc(p.title)}</td>
                <td class="pp-authors">${authorsHtml(p)}</td>
                <td>${esc(p.venue || '')}</td>
                <td>${TYPE_SHORT[p.type]}</td>
                <td class="num">${p.citations || ''}</td>
                <td>${links.join(' · ')}</td>
            </tr>`;
        }).join('');
        let more = '';
        if (limit < current.length) {
            more = `<button type="button" class="cite-btn pp-more" id="pp-more">Show all ${current.length} entries</button>`;
        }
        box.innerHTML = `<div class="pp-table-wrap"><table class="pp-table"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>${more}`;
    }

    function renderHistogram() {
        const svg = $('pp-hist');
        const years = DB._years;
        const counts = new Map(years.map((y) => [y, 0]));
        DB.publications.forEach((p) => {
            if (p.year && matches(p, state, true)) counts.set(p.year, (counts.get(p.year) || 0) + 1);
        });
        const W = svg.clientWidth || 800, H = 90, top = 6, bottom = 18;
        const n = years.length;
        const max = Math.max(1, ...counts.values());
        const bw = W / n;
        const from = state.from ? +state.from : -Infinity, to = state.to ? +state.to : Infinity;
        const parts = [];
        years.forEach((y, i) => {
            const c = counts.get(y);
            const h = c ? Math.max(2, (H - top - bottom) * c / max) : 0;
            const inRange = y >= from && y <= to;
            parts.push(`<rect class="bar${inRange ? '' : ' dim'}" data-year="${y}" data-count="${c}"
                x="${(i * bw + 1).toFixed(1)}" y="${(H - bottom - h).toFixed(1)}"
                width="${Math.max(1, bw - 2).toFixed(1)}" height="${h.toFixed(1)}"></rect>`);
            // invisible hit target over full column for easy hovering
            parts.push(`<rect fill="transparent" data-year="${y}" data-count="${c}" class="hit"
                x="${(i * bw).toFixed(1)}" y="${top}" width="${bw.toFixed(1)}" height="${H - top - bottom}"></rect>`);
        });
        const step = n > 40 ? 10 : 5;
        years.forEach((y, i) => {
            if (y % step === 0) {
                parts.push(`<text x="${(i * bw + bw / 2).toFixed(1)}" y="${H - 4}" text-anchor="middle">${y}</text>`);
            }
        });
        svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
        svg.innerHTML = parts.join('');
    }

    function renderCounts() {
        // chip counts reflect the other active filters
        DB.people.forEach((person) => {
            const s = { ...state, people: [person.key], mode: 'any' };
            const n = DB.publications.filter((p) => matches(p, s)).length;
            const el = document.querySelector(`#pp-advanced [data-key="${person.key}"] .pp-n`);
            if (el) el.textContent = n;
        });
        TYPES.forEach(([t]) => {
            const s = { ...state, types: [t] };
            const n = DB.publications.filter((p) => matches(p, s)).length;
            const chip = document.querySelector(`#pp-types [data-type="${t}"]`);
            if (chip) {
                chip.querySelector('.pp-n').textContent = n;
                chip.hidden = !DB._typeTotals[t];
            }
        });
    }

    function renderSummary() {
        const n = current.length;
        const pdfs = current.filter((p) => p.pdf).length;
        const order = { new: 'newest first', old: 'oldest first', cited: 'by impact, highest first',
            'cited-asc': 'by impact, lowest first', title: 'by title', venue: 'by venue', type: 'by type' }[state.sort];
        const scope = { only: 'FAMLIES only', related: 'FAMLIES Related', all: '' }[state.scope];
        const shown = [scope, state.core && 'Core Team'].filter(Boolean).join(', ');
        $('pp-count').innerHTML = `<strong>${n}</strong> of ${DB.publications.length} publications${shown ? ` (${shown})` : ''}, ${order}` +
            (n ? ` · ${pdfs} with PDF` : '') + (activeAdvanced() ? ' · <em>advanced filters on</em>' : '');
        $('pp-bib').textContent = `Download BibTeX (${n})`;
        $('pp-csv').textContent = `Download CSV (${n})`;
        $('pp-bib').disabled = $('pp-csv').disabled = !n;
    }

    function update(opts = {}) {
        if (!opts.keepLimit) limit = PAGE;
        current = DB.publications.filter((p) => matches(p, state)).sort(SORTS[state.sort]);
        syncControls();
        renderCounts();
        if (!$('pp-advanced').hidden) renderHistogram();
        renderSummary();
        renderResults();
        writeHash();
    }

    // ------------------------------------------------------------ controls

    function buildControls() {
        const chip = (p) => `<button type="button" class="pp-chip" data-key="${p.key}" aria-pressed="false"
                title="${esc([p.name, p.role, p.institution].filter(Boolean).join(', '))}">${esc(p.name)}<span class="pp-n"></span></button>`;
        $('pp-people-pi').innerHTML = DB.people.filter((p) => p.group === 'pi' || p.group === 'staff').map(chip).join('');
        $('pp-people-collab').innerHTML = DB.people.filter((p) => p.group === 'collaborator').map(chip).join('');
        const co = DB.people.filter((p) => p.group === 'coauthor')
            .sort((a, b) => a.short.localeCompare(b.short) || a.name.localeCompare(b.name));
        $('pp-coauthor').insertAdjacentHTML('beforeend', co.map((p) =>
            `<option value="${p.key}">${esc(p.short)}, ${esc(p.name.slice(0, p.name.length - p.short.length).trim())}</option>`).join(''));
        $('pp-types').innerHTML = TYPES.map(([t, label]) =>
            `<button type="button" class="pp-chip" data-type="${t}" aria-pressed="false">${label}<span class="pp-n"></span></button>`).join('');

        const years = DB._years;
        const opt = (y) => `<option value="${y}">${y}</option>`;
        $('pp-from').innerHTML = '<option value="">Earliest</option>' + years.map(opt).join('');
        $('pp-to').innerHTML = '<option value="">Latest</option>' + years.slice().reverse().map(opt).join('');

        const venues = new Map();
        DB.publications.forEach((p) => { if (p.venue) venues.set(p.venue, (venues.get(p.venue) || 0) + 1); });
        const vs = [...venues.entries()].filter(([, c]) => c >= 2)
            .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
        $('pp-venue').innerHTML = '<option value="">All venues</option>' +
            vs.map(([v, c]) => `<option value="${esc(v)}">${esc(v.length > 60 ? v.slice(0, 57) + '…' : v)} (${c})</option>`).join('');
        // keep a venue from a shared link even if it has a single paper
        if (state.venue && !venues.has(state.venue)) state.venue = '';
        else if (state.venue && venues.get(state.venue) < 2) {
            $('pp-venue').insertAdjacentHTML('beforeend', `<option value="${esc(state.venue)}">${esc(state.venue)} (1)</option>`);
        }
    }

    function syncControls() {
        ['q', 'ft', 'fa', 'fv'].forEach((k) => {
            const el = $('pp-' + k);
            if (el !== document.activeElement && el.value.trim() !== state[k]) el.value = state[k];
        });
        const byYear = state.sort === 'new' || state.sort === 'old';
        const byImpact = state.sort === 'cited' || state.sort === 'cited-asc';
        $('pp-by-year').classList.toggle('active', byYear);
        $('pp-by-year').setAttribute('aria-pressed', byYear);
        $('pp-by-year').querySelector('.pp-arrow').textContent = state.sort === 'old' ? '↑' : '↓';
        $('pp-by-impact').classList.toggle('active', byImpact);
        $('pp-by-impact').setAttribute('aria-pressed', byImpact);
        $('pp-by-impact').querySelector('.pp-arrow').textContent = state.sort === 'cited-asc' ? '↑' : '↓';
        $('pp-people-co').innerHTML = state.people.filter((k) => PEOPLE[k].group === 'coauthor').map((k) =>
            `<button type="button" class="pp-chip" data-key="${k}" aria-pressed="true" title="Remove">${esc(PEOPLE[k].name)}<span class="pp-n"></span> ×</button>`).join('');
        $('pp-coauthor').value = '';
        document.querySelectorAll('#pp-advanced [data-key]').forEach((b) =>
            b.setAttribute('aria-pressed', state.people.includes(b.dataset.key)));
        document.querySelectorAll('#pp-types .pp-chip').forEach((b) =>
            b.setAttribute('aria-pressed', state.types.includes(b.dataset.type)));
        document.querySelectorAll('[data-mode]').forEach((b) =>
            b.classList.toggle('active', b.dataset.mode === state.mode));
        document.querySelectorAll('#pp-view [data-view]').forEach((b) =>
            b.classList.toggle('active', b.dataset.view === state.view));
        $('pp-joint').checked = state.joint;
        $('pp-pdf').checked = state.pdf;
        $('pp-from').value = state.from;
        $('pp-to').value = state.to;
        $('pp-venue').value = state.venue;
        $('pp-group').value = state.group;
        $('pp-group').disabled = state.view === 'table';
        $('pp-sort').value = state.sort;
        $('pp-core').classList.toggle('active', state.core);
        $('pp-core').setAttribute('aria-pressed', String(state.core));
        $('pp-scope').value = state.scope;
        const n = activeAdvanced();
        $('pp-adv-toggle').classList.toggle('has-filters', n > 0);
        $('pp-adv-toggle').firstChild.textContent = n ? `Advanced search (${n}) ` : 'Advanced search ';
    }

    // Number of advanced filters that narrow the results.
    function activeAdvanced() {
        return ['ft', 'fa', 'fv', 'people', 'joint', 'types', 'from', 'to', 'venue', 'pdf']
            .filter((k) => (Array.isArray(state[k]) ? state[k].length : state[k])).length;
    }

    function setAdvanced(open) {
        $('pp-advanced').hidden = !open;
        $('pp-adv-toggle').setAttribute('aria-expanded', String(open));
        $('pp-adv-toggle').querySelector('.pp-arrow').textContent = open ? '▴' : '▾';
        if (open) renderHistogram();
    }

    function toggleIn(list, v) {
        return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
    }

    function bindControls() {
        let timer;
        ['q', 'ft', 'fa', 'fv'].forEach((k) => $('pp-' + k).addEventListener('input', (e) => {
            state[k] = e.target.value.trim();   // record now; only the re-render is debounced
            clearTimeout(timer);
            timer = setTimeout(update, 150);
        }));
        $('pp-coauthor').addEventListener('change', (e) => {
            const k = e.target.value;
            if (k && !state.people.includes(k)) { state.people = [...state.people, k]; update(); }
        });
        ['pp-people-pi', 'pp-people-collab', 'pp-people-co'].forEach((id) => $(id).addEventListener('click', (e) => {
            const b = e.target.closest('.pp-chip');
            if (b) { state.people = toggleIn(state.people, b.dataset.key); update(); }
        }));
        $('pp-by-year').addEventListener('click', () => {
            state.sort = state.sort === 'new' ? 'old' : 'new';
            update();
        });
        $('pp-by-impact').addEventListener('click', () => {
            state.sort = state.sort === 'cited' ? 'cited-asc' : 'cited';
            update();
        });
        $('pp-core').addEventListener('click', () => { state.core = !state.core; update(); });
        $('pp-scope').addEventListener('change', (e) => { state.scope = e.target.value; update(); });
        $('pp-adv-toggle').addEventListener('click', () => setAdvanced($('pp-advanced').hidden));
        $('pp-adv-close').addEventListener('click', () => { setAdvanced(false); $('pp-adv-toggle').focus(); });
        $('pp-types').addEventListener('click', (e) => {
            const b = e.target.closest('.pp-chip');
            if (b) { state.types = toggleIn(state.types, b.dataset.type); update(); }
        });
        document.querySelectorAll('[data-mode]').forEach((b) =>
            b.addEventListener('click', () => { state.mode = b.dataset.mode; update(); }));
        document.querySelectorAll('#pp-view [data-view]').forEach((b) =>
            b.addEventListener('click', () => { state.view = b.dataset.view; update(); }));
        $('pp-joint').addEventListener('change', (e) => { state.joint = e.target.checked; update(); });
        $('pp-pdf').addEventListener('change', (e) => { state.pdf = e.target.checked; update(); });
        $('pp-from').addEventListener('change', (e) => {
            state.from = e.target.value;
            if (state.from && state.to && +state.to < +state.from) state.to = state.from;
            update();
        });
        $('pp-to').addEventListener('change', (e) => {
            state.to = e.target.value;
            if (state.from && state.to && +state.to < +state.from) state.from = state.to;
            update();
        });
        $('pp-venue').addEventListener('change', (e) => { state.venue = e.target.value; update(); });
        $('pp-group').addEventListener('change', (e) => { state.group = e.target.value; update(); });
        $('pp-sort').addEventListener('change', (e) => { state.sort = e.target.value; update(); });
        $('pp-reset').addEventListener('click', () => {
            const keep = { q: state.q, sort: state.sort, core: state.core, scope: state.scope };
            state = { ...DEFAULTS, ...keep };
            update();
        });

        $('pp-bib').addEventListener('click', () => {
            const text = `% FAMLIES publications (${current.length} entries), exported ${new Date().toISOString().slice(0, 10)}\n% ${location.href}\n\n` +
                current.map((p) => p.bibtex).join('\n\n') + '\n';
            download('famlies-publications.bib', text, 'application/x-bibtex');
        });
        $('pp-csv').addEventListener('click', () => {
            const q = (v) => '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"';
            const head = ['year', 'title', 'authors', 'venue', 'type', 'doi', 'url', 'pdf', 'arxiv', 'citations', 'pis', 'bibtex_key'];
            const rows = current.map((p) => [p.year, p.title, p.authors.join('; '), p.venue, p.type, p.doi,
                p.url, p.pdf, p.arxiv, p.citations || 0, p.pis.map((k) => PEOPLE[k].name).join('; '), p.key].map(q).join(','));
            download('famlies-publications.csv', '﻿' + head.join(',') + '\n' + rows.join('\n') + '\n', 'text/csv');
        });
        $('pp-copy-link').addEventListener('click', (e) => copy(location.href, e.currentTarget));

        // Results: cite panels, show more, table sorting, BibTeX in table
        $('pp-results').addEventListener('click', (e) => {
            const more = e.target.closest('#pp-more');
            if (more) { limit = Infinity; update({ keepLimit: true }); return; }

            const citeBtn = e.target.closest('[data-cite]');
            if (citeBtn) {
                const i = +citeBtn.dataset.cite;
                const panel = $('pp-cite-' + i);
                if (!panel.innerHTML.trim()) panel.innerHTML = citePanelHtml(current[i]);
                panel.hidden = !panel.hidden;
                citeBtn.setAttribute('aria-expanded', String(!panel.hidden));
                return;
            }
            const tab = e.target.closest('.cite-tab');
            if (tab) {
                const panel = tab.closest('.cite-panel');
                panel.querySelectorAll('.cite-tab').forEach((t) => t.classList.toggle('active', t === tab));
                panel.querySelectorAll('.cite-content').forEach((c) => { c.hidden = c.dataset.format !== tab.dataset.format; });
                return;
            }
            const cp = e.target.closest('[data-copy]');
            if (cp) {
                const i = +cp.closest('.cite-panel').id.replace('pp-cite-', '');
                copy(cp.dataset.copy === 'bibtex' ? current[i].bibtex : apa(current[i]), cp);
                return;
            }
            const bib = e.target.closest('[data-bib]');
            if (bib) {
                e.preventDefault();
                copy(current[+bib.dataset.bib].bibtex, bib);
                return;
            }
            const th = e.target.closest('th[data-sort]');
            if (th) {
                const s = th.dataset.sort;
                if (s === 'new') state.sort = state.sort === 'new' ? 'old' : 'new';
                else if (s === 'cited') state.sort = state.sort === 'cited' ? 'cited-asc' : 'cited';
                else state.sort = s;
                update();
            }
        });
        $('pp-results').addEventListener('keydown', (e) => {
            const th = e.target.closest('th[data-sort]');
            if (th && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); th.click(); }
        });

        // Histogram: hover tooltip, click to select a year (click again to clear)
        const svg = $('pp-hist'), tip = $('pp-hist-tip');
        svg.addEventListener('mousemove', (e) => {
            const r = e.target.closest('[data-year]');
            if (!r) { tip.hidden = true; return; }
            const box = svg.getBoundingClientRect();
            const rb = r.getBoundingClientRect();
            tip.textContent = `${r.dataset.year}: ${r.dataset.count} publication${r.dataset.count === '1' ? '' : 's'}`;
            tip.style.left = (rb.left - box.left + rb.width / 2) + 'px';
            tip.hidden = false;
        });
        svg.addEventListener('mouseleave', () => { tip.hidden = true; });
        svg.addEventListener('click', (e) => {
            const r = e.target.closest('[data-year]');
            if (!r) return;
            const y = r.dataset.year;
            if (state.from === y && state.to === y) { state.from = state.to = ''; }
            else { state.from = state.to = y; }
            update();
        });

        window.addEventListener('hashchange', () => {
            const s = readHash();
            if (JSON.stringify(s) !== JSON.stringify(state)) { state = s; update(); }
        });
        let rt;
        window.addEventListener('resize', () => {
            clearTimeout(rt);
            rt = setTimeout(() => { if (!$('pp-advanced').hidden) renderHistogram(); }, 100);
        });
    }

    // ------------------------------------------------------------ init

    function prepare(db) {
        const rank = Object.fromEntries(TYPES.map(([t], i) => [t, i]));
        db.people.forEach((p) => {
            PEOPLE[p.key] = p;
            p.short = p.short || p.name;
        });
        db._typeTotals = {};
        let lo = Infinity, hi = -Infinity;
        db.publications.forEach((p) => {
            p.pis = p.pis || [];
            p.authors = p.authors || [];
            p._hay = fold([p.title, p.authors.join(' '), p.venue, p.year, p.doi, p.arxiv, p.key, TYPE_LABEL[p.type] || p.type].join(' '));
            p._t = fold(p.title);
            p._a = fold(p.authors.join(' '));
            p._v = fold(p.venue);
            p._piCount = p.pis.filter((k) => PEOPLE[k] && PEOPLE[k].group === 'pi').length;
            p._core = p.pis.some((k) => PEOPLE[k] && (PEOPLE[k].group === 'pi' || PEOPLE[k].group === 'staff'));
            p._sortTitle = fold(p.title).replace(/^(the|a|an)\s+/, '');
            p._typeRank = rank[p.type] ?? 99;
            db._typeTotals[p.type] = (db._typeTotals[p.type] || 0) + 1;
            if (p.year) { lo = Math.min(lo, p.year); hi = Math.max(hi, p.year); }
        });
        db._years = [];
        for (let y = lo; y <= hi; y++) db._years.push(y);
        // ensure the canonical PI order matches people.json
        db.publications.forEach((p) => p.pis.sort((a, b) =>
            db.people.findIndex((x) => x.key === a) - db.people.findIndex((x) => x.key === b)));
    }

    function note() {
        const names = {
            openalex: '<a href="https://openalex.org" target="_blank" rel="noopener">OpenAlex</a>',
            flame: 'the <a href="https://www.cs.utexas.edu/~flame/web/FLAMEPublications.html" target="_blank" rel="noopener">FLAME publication list</a>',
            import: 'Google Scholar BibTeX exports',
            famlies: 'the FAMLIES working-note BibTeX files',
        };
        const used = (DB.sources || []).map((s) => names[s]).filter(Boolean);
        const list = used.length > 1 ? used.slice(0, -1).join(', ') + ' and ' + used[used.length - 1] : used.join('');
        $('pp-note').innerHTML =
            `Database generated ${esc(DB.generated)}${list ? ' from ' + list : ''}. ` +
            'Citation counts differ from those reported by Google Scholar. ' +
            'Impact is the number of citations recorded by OpenAlex. ' +
            'Names of the FAMLIES Core Team (PIs, co-PIs and Bimal Gaudel) are shown in bold.';
    }

    async function init() {
        try {
            const res = await fetch(DATA_URL, { cache: 'no-cache' });
            if (!res.ok) throw new Error(res.status + ' ' + res.statusText);
            DB = await res.json();
        } catch (err) {
            $('pp-results').innerHTML = `<p class="pp-empty">Could not load the publication database (${esc(err.message)}).</p>`;
            return;
        }
        prepare(DB);
        state = readHash();
        buildControls();
        bindControls();
        note();
        update();
        if (activeAdvanced()) setAdvanced(true);
    }

    document.addEventListener('DOMContentLoaded', init);
})();
