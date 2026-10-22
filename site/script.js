/* ============================================
   FAMLIES Website - JavaScript
   ============================================ */

// Note: YAML parsing is handled by the js-yaml library (loaded via CDN in events.html)
// This allows us to support full YAML syntax without a custom parser

// Calendar state shared across nav callbacks
let calState = {};

async function loadEvents() {
    const widgetEl = document.getElementById('calendar-widget');
    const panelEl  = document.getElementById('events-panel');
    const listEl   = document.getElementById('events-list');
    if (!widgetEl || !panelEl || !listEl) return;

    try {
        const response = await fetch('config/events.yml');
        const yamlText = await response.text();
        const data = jsyaml.load(yamlText);
        const events = (data.events || []).filter(e => e.date && e.title);

        // Chronological: past events above the Today divider, future below
        events.sort((a, b) => new Date(a.date) - new Date(b.date));

        renderEventsList(listEl, events);

        const now = new Date();
        renderCalendar(widgetEl, now.getFullYear(), now.getMonth(), events, panelEl);

        // Two rAFs: first lets the browser process innerHTML, second lets it lay out
        requestAnimationFrame(() => requestAnimationFrame(() => centerOnTodayMarker(panelEl)));

    } catch (error) {
        console.error('Error loading events:', error);
        document.getElementById('events-list').innerHTML =
            '<p style="color:var(--secondary-color);padding:24px;">Unable to load events. Please check back soon.</p>';
    }
}

function renderEventsList(listEl, events) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    let html = '';
    let markerInserted = false;

    events.forEach(event => {
        const [y, m, d] = event.date.split('-').map(Number);
        const isPast = new Date(y, m - 1, d) < today;

        if (!markerInserted && !isPast) {
            html += buildTodayMarker();
            markerInserted = true;
        }
        html += buildEventCard(event, isPast);
    });

    // All events are in the past — marker goes at the end
    if (!markerInserted) html += buildTodayMarker();

    listEl.innerHTML = html;
}

function buildTodayMarker() {
    const label = new Date().toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
    return `<div class="today-marker" id="today-marker"><span>Today &mdash; ${label}</span></div>`;
}

function buildEventCard(event, isPast) {
    const [y, m, d] = event.date.split('-').map(Number);
    const monthStr = new Date(y, m - 1, d).toLocaleString('en-US', { month: 'short' }).toUpperCase();
    const dateBarClass = isPast ? 'event-date-past' : 'event-date';

    const speakersLabel = event.speakers && event.speakers.length > 1 ? 'Speakers' : 'Speaker';
    const speakersText = event.speakers && event.speakers.length > 0
        ? `<p class="event-speakers"><strong>${speakersLabel}:</strong> ${event.speakers.join(', ')}</p>`
        : '';

    const eventLinkHTML = event.event_link
        ? `<div class="event-actions"><a href="${event.event_link}" class="event-link" target="_blank">Register/Join →</a></div>`
        : '';

    const filesHTML = event.files && event.files.length > 0
        ? `<div class="event-files"><p class="event-files-label">Files:</p><ul class="event-files-list">${
            event.files.map(f => `<li><a href="${f.url}" target="_blank">${f.name}</a></li>`).join('')
          }</ul></div>`
        : '';

    return `<div class="event-card" data-event-date="${event.date}">
        <div class="${dateBarClass}">
            <div class="event-month">${monthStr}</div>
            <div class="event-day">${d}</div>
        </div>
        <div class="event-content">
            <h3>${event.title}</h3>
            <p class="event-time">${event.time_range} | ${event.location}</p>
            <p class="event-description">${event.description}</p>
            ${speakersText}${eventLinkHTML}${filesHTML}
        </div>
    </div>`;
}

function centerOnTodayMarker(panelEl) {
    const marker = panelEl.querySelector('#today-marker');
    if (!marker) return;
    const pr = panelEl.getBoundingClientRect();
    const mr = marker.getBoundingClientRect();
    const relTop = mr.top - pr.top + panelEl.scrollTop;
    panelEl.scrollTop = relTop - panelEl.clientHeight / 2 + marker.offsetHeight / 2;
}

function renderCalendar(widgetEl, year, month, events, panelEl) {
    calState = { year, month, events, panelEl, widgetEl };

    const today = new Date();
    const todayStr = [
        today.getFullYear(),
        String(today.getMonth() + 1).padStart(2, '0'),
        String(today.getDate()).padStart(2, '0')
    ].join('-');

    // Map date string → events array for title hints
    const eventsByDate = new Map();
    events.forEach(e => {
        if (!eventsByDate.has(e.date)) eventsByDate.set(e.date, []);
        eventsByDate.get(e.date).push(e);
    });

    const MONTHS = ['January','February','March','April','May','June',
                    'July','August','September','October','November','December'];
    const DAYS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

    const firstDow    = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    let gridHTML = DAYS.map(d => `<div class="cal-day-header">${d}</div>`).join('');
    for (let i = 0; i < firstDow; i++) gridHTML += `<div class="cal-day empty"></div>`;

    for (let d = 1; d <= daysInMonth; d++) {
        const ds = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
        const dayEvents = eventsByDate.get(ds) || [];
        const hasEvent  = dayEvents.length > 0;
        const isToday   = ds === todayStr;
        const cls = ['cal-day', hasEvent && 'has-event', isToday && 'is-today'].filter(Boolean).join(' ');

        const titleHint = hasEvent
            ? `<span class="cal-event-title">${dayEvents[0].title}</span>`
            : '';
        const dot = hasEvent ? `<span class="event-dot"></span>` : '';

        gridHTML += `<div class="${cls}" data-date="${ds}"><span class="cal-day-num">${d}</span>${titleHint}${dot}</div>`;
    }

    widgetEl.innerHTML = `
        <div class="calendar-header">
            <button class="cal-nav-btn" id="cal-prev">&#8249;</button>
            <div class="cal-month-title">${MONTHS[month]} ${year}</div>
            <button class="cal-nav-btn" id="cal-next">&#8250;</button>
        </div>
        <div class="calendar-grid">${gridHTML}</div>`;

    widgetEl.querySelector('#cal-prev').addEventListener('click', () => {
        let { year: y, month: mo } = calState;
        if (--mo < 0) { mo = 11; y--; }
        renderCalendar(calState.widgetEl, y, mo, calState.events, calState.panelEl);
    });

    widgetEl.querySelector('#cal-next').addEventListener('click', () => {
        let { year: y, month: mo } = calState;
        if (++mo > 11) { mo = 0; y++; }
        renderCalendar(calState.widgetEl, y, mo, calState.events, calState.panelEl);
    });

    widgetEl.querySelectorAll('.cal-day.has-event').forEach(cell => {
        cell.addEventListener('click', () => {
            const target = panelEl.querySelector(`[data-event-date="${cell.dataset.date}"]`);
            if (!target) return;
            const pr = panelEl.getBoundingClientRect();
            const tr = target.getBoundingClientRect();
            const relTop = tr.top - pr.top + panelEl.scrollTop;
            panelEl.scrollTo({ top: relTop - panelEl.clientHeight / 2 + target.offsetHeight / 2, behavior: 'smooth' });
        });
    });
}

// Parse BibTeX format
function parseBibTeX(bibContent) {
    const entries = [];
    const bibRegex = /@(\w+)\s*{\s*([^,]+),\s*([\s\S]*?)(?=@\w+\s*{|$)/g;
    let match;

    while ((match = bibRegex.exec(bibContent)) !== null) {
        const type = match[1].toLowerCase();
        const key = match[2].trim();
        const fieldsText = match[3];

        const fields = {};
        const fieldRegex = /(\w+)\s*=\s*["{]([^"}]*)["}]/g;
        let fieldMatch;

        while ((fieldMatch = fieldRegex.exec(fieldsText)) !== null) {
            const fieldName = fieldMatch[1].toLowerCase();
            const fieldValue = fieldMatch[2].trim();
            fields[fieldName] = fieldValue;
        }

        entries.push({
            key: key,
            type: type,
            fields: fields,
            raw: match[0].trim()
        });
    }

    return entries;
}

function escapeHtml(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function formatAuthorsAPA(authorStr) {
    if (!authorStr) return '';
    const particles = new Set(['van', 'de', 'von', 'di', 'del', 'der', 'la', 'le', 'du']);
    const authors = authorStr.split(' and ').map(a => {
        a = a.trim();
        const commaIdx = a.indexOf(',');
        if (commaIdx > -1) {
            const last = a.slice(0, commaIdx).trim();
            const first = a.slice(commaIdx + 1).trim();
            const initials = first.split(/\s+/).filter(Boolean)
                .map(n => n[0].toUpperCase() + '.').join(' ');
            return `${last}, ${initials}`;
        }
        const parts = a.split(/\s+/);
        if (parts.length === 1) return a;
        let familyStart = parts.length - 1;
        for (let i = 0; i < parts.length - 1; i++) {
            if (particles.has(parts[i].toLowerCase())) { familyStart = i; break; }
        }
        const family = parts.slice(familyStart).join(' ');
        const initials = parts.slice(0, familyStart).map(n => n[0].toUpperCase() + '.').join(' ');
        return initials ? `${family}, ${initials}` : family;
    });
    if (authors.length === 1) return authors[0];
    if (authors.length === 2) return authors.join(' & ');
    return authors.slice(0, -1).join(', ') + ', & ' + authors[authors.length - 1];
}

function formatAPA(entry) {
    const { fields } = entry;
    const authors = formatAuthorsAPA(fields.author || '');
    const year = fields.year || 'n.d.';
    const title = fields.title || '';
    const journal = fields.journal || fields.booktitle || '';
    const volume = fields.volume || '';
    const number = fields.number || '';
    const pages = fields.pages ? fields.pages.replace(/--/g, '–') : '';
    const doi = fields.doi || '';
    const eprint = fields.eprint || '';
    const archiveprefix = (fields.archiveprefix || '').toLowerCase();

    const parts = [];
    if (authors) parts.push(authors);
    parts.push(`(${year}).`);
    if (title) parts.push(`${title}.`);

    if (journal) {
        let journalPart = journal;
        if (volume) {
            journalPart += `, ${volume}`;
            if (number) journalPart += `(${number})`;
        }
        if (pages) journalPart += `, ${pages}`;
        journalPart += '.';
        parts.push(journalPart);
    } else if (eprint && archiveprefix.includes('arxiv')) {
        parts.push(`arXiv preprint arXiv:${eprint}.`);
    }

    if (doi) {
        parts.push(doi.startsWith('http') ? doi : `https://doi.org/${doi}`);
    } else if (!journal && fields.url && !fields.url.includes('arxiv.org') && fields.url.startsWith('http')) {
        parts.push(fields.url);
    }

    return parts.join(' ');
}

function toggleCite(id) {
    const panel = document.getElementById(id);
    if (panel) panel.hidden = !panel.hidden;
}

function switchCiteTab(id, format) {
    const panel = document.getElementById(id);
    if (!panel) return;
    panel.querySelectorAll('.cite-tab').forEach(t => t.classList.remove('active'));
    panel.querySelectorAll('.cite-content').forEach(c => { c.hidden = true; });
    const tab = panel.querySelector(`.cite-tab[data-format="${format}"]`);
    const content = panel.querySelector(`.cite-content[data-format="${format}"]`);
    if (tab) tab.classList.add('active');
    if (content) content.hidden = false;
}

function copyText(id, format) {
    const panel = document.getElementById(id);
    if (!panel) return;
    const content = panel.querySelector(`.cite-content[data-format="${format}"]`);
    const text = content ? (content.querySelector('pre') || content.querySelector('p') || content).textContent.trim() : '';
    navigator.clipboard.writeText(text).then(() => {
        const btn = content && content.querySelector('.copy-btn');
        if (btn) {
            const orig = btn.textContent;
            btn.textContent = 'Copied!';
            setTimeout(() => { btn.textContent = orig; }, 2000);
        }
    }).catch(() => {});
}

// Generate publication links (URL, DOI, arXiv)
function generatePublicationLinks(fields) {
    const links = [];

    if (fields.url) {
        const url = fields.url;
        const isArxiv = url.includes('arxiv.org');

        if (isArxiv) {
            // For arXiv URLs, add both abstract and PDF links
            const arxivMatch = url.match(/arxiv\.org\/abs\/(\d+\.\d+)/);
            if (arxivMatch) {
                const arxivId = arxivMatch[1];
                links.push({
                    text: 'arXiv Preprint',
                    url: url
                });
                links.push({
                    text: 'PDF',
                    url: `https://arxiv.org/pdf/${arxivId}.pdf`
                });
            }
        } else {
            links.push({
                text: 'View Paper',
                url: url
            });
            // Also surface arXiv preprint when eprint field is present
            if (fields.eprint && fields.archiveprefix &&
                fields.archiveprefix.toLowerCase().includes('arxiv')) {
                links.push({
                    text: 'arXiv Preprint',
                    url: `https://arxiv.org/abs/${fields.eprint}`
                });
            }
        }
    } else if (fields.doi) {
        // Generate DOI link
        const doiUrl = fields.doi.startsWith('http') ? fields.doi : `https://doi.org/${fields.doi}`;
        links.push({
            text: 'DOI',
            url: doiUrl
        });
    }

    return links;
}

// Format author names
function formatAuthors(authorStr) {
    if (!authorStr) return '';
    return authorStr.split(' and ').map(a => a.trim()).join(', ');
}

// Create publication HTML element
function createPublicationElement(entry) {
    const { fields } = entry;

    const title = fields.title || 'Untitled';
    const authors = formatAuthors(fields.author || '');
    const year = fields.year || '';
    const journal = fields.journal || fields.booktitle || fields.institution || '';
    const abstract = fields.abstract || '';

    const links = generatePublicationLinks(fields);

    let metaText = '';
    if (journal && year) {
        metaText = `${journal}, ${year}`;
    } else if (journal) {
        metaText = journal;
    } else if (year) {
        metaText = year;
    }

    const citeId = `cite-${entry.key.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
    const bibtex = escapeHtml(entry.raw || '');
    const apa = escapeHtml(formatAPA(entry));

    let linksHTML = '';
    if (links.length > 0) {
        linksHTML = '<div class="publication-links">' +
            links.map(link => `<a href="${link.url}" class="pub-link" target="_blank">${link.text}</a>`).join('') +
            `<button class="cite-btn" onclick="toggleCite('${citeId}')">Cite</button>` +
            '</div>';
    } else {
        linksHTML = `<div class="publication-links"><button class="cite-btn" onclick="toggleCite('${citeId}')">Cite</button></div>`;
    }

    const citePanel = `
        <div class="cite-panel" id="${citeId}" hidden>
            <div class="cite-tabs">
                <button class="cite-tab active" data-format="bibtex" onclick="switchCiteTab('${citeId}', 'bibtex')">BibTeX</button>
                <button class="cite-tab" data-format="apa" onclick="switchCiteTab('${citeId}', 'apa')">APA</button>
            </div>
            <div class="cite-content" data-format="bibtex">
                <pre>${bibtex}</pre>
                <button class="copy-btn" onclick="copyText('${citeId}', 'bibtex')">Copy</button>
            </div>
            <div class="cite-content" data-format="apa" hidden>
                <p>${apa}</p>
                <button class="copy-btn" onclick="copyText('${citeId}', 'apa')">Copy</button>
            </div>
        </div>`;

    const html = `
        <div class="publication-item">
            <div class="publication-header">
                <h3>${title}</h3>
                ${metaText ? `<p class="publication-meta">${metaText}</p>` : ''}
            </div>
            <div class="publication-details">
                ${authors ? `<p class="publication-authors"><strong>Authors:</strong> ${authors}</p>` : ''}
                ${abstract ? `<p class="publication-abstract">${abstract}</p>` : ''}
                ${linksHTML}
                ${citePanel}
            </div>
        </div>
    `;

    return html;
}

// Load and render publications from BibTeX files
async function loadPublications() {
    try {
        // Load FAWN publications
        const fawnResponse = await fetch('config/fawns.bib');
        const fawnText = await fawnResponse.text();
        const fawnEntries = parseBibTeX(fawnText);

        // Load related publications
        const relatedResponse = await fetch('config/related.bib');
        const relatedText = await relatedResponse.text();
        const relatedEntries = parseBibTeX(relatedText);

        // Render FAWN publications
        const fawnContainer = document.querySelector('.fawn-publications-list');
        if (fawnContainer && fawnEntries.length > 0) {
            fawnContainer.innerHTML = fawnEntries.map(createPublicationElement).join('');
        }

        // Render related publications
        const relatedContainer = document.querySelector('.related-publications-list');
        if (relatedContainer && relatedEntries.length > 0) {
            relatedContainer.innerHTML = relatedEntries.map(createPublicationElement).join('');
        }
    } catch (error) {
        console.error('Error loading publications:', error);
    }
}

// Load events on page load if on events page
document.addEventListener('DOMContentLoaded', function() {
    loadEvents();
    loadPublications();

    // Active navigation link tracking
    const currentPage = window.location.pathname.split('/').pop() || 'index.html';
    const navLinks = document.querySelectorAll('.nav-link');

    navLinks.forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPage || (currentPage === '' && href === 'index.html')) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });
});

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function(e) {
        const href = this.getAttribute('href');
        if (href !== '#' && document.querySelector(href)) {
            e.preventDefault();
            document.querySelector(href).scrollIntoView({
                behavior: 'smooth'
            });
        }
    });
});

// Optional: Add scroll animation for elements
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver(function(entries) {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Observe all content sections for fade-in animation
document.querySelectorAll('.content-section, .objective-card, .cta-card').forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(20px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});
