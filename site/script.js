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

// Load events on page load if on events page
document.addEventListener('DOMContentLoaded', function() {
    loadEvents();

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
