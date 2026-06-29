let db = null;
let chartInstance = null;
let SQL = null;

// Database Initialization
async function initializeDatabase() {
    if (SQL) return;

    // Properly initialize SQL.js
    SQL = await window.initSqlJs({
        locateFile: file => `https://sql.js.org/dist/${file}`
    });
}

async function loadDatabase(event) {
    const file = event.target.files[0];
    if (!file) return;

    showLoading();

    try {
        // Initialize SQL.js if needed
        await initializeDatabase();

        const arrayBuffer = await file.arrayBuffer();
        const data = new Uint8Array(arrayBuffer);

        db = new SQL.Database(data);

        document.getElementById('db-status').textContent = `✓ Database loaded: ${file.name}`;
        document.getElementById('db-status').classList.add('loaded');
        document.getElementById('control-panel').classList.add('active');

        showSuccess(`Database loaded successfully: ${file.name}`);
        clearLoading();
    } catch (error) {
        showError(`Failed to load database: ${error.message}`);
        clearLoading();
    }
}

// UI Control Functions
function updateConditionalGroups() {
    const plotType = document.getElementById('plot-type').value;
    document.getElementById('historical-params').classList.remove('visible');
    document.getElementById('scaling-params').classList.remove('visible');
    document.getElementById('overview-params').classList.remove('visible');

    if (plotType === 'historical') {
        document.getElementById('historical-params').classList.add('visible');
    } else if (plotType === 'scaling') {
        document.getElementById('scaling-params').classList.add('visible');
    } else if (plotType === 'overview') {
        document.getElementById('overview-params').classList.add('visible');
    }
}

function clearMessages() {
    document.getElementById('error-message').classList.remove('active');
    document.getElementById('success-message').classList.remove('active');
}

function showError(message) {
    clearMessages();
    const errorDiv = document.getElementById('error-message');
    errorDiv.textContent = message;
    errorDiv.classList.add('active');
}

function showSuccess(message) {
    clearMessages();
    const successDiv = document.getElementById('success-message');
    successDiv.textContent = message;
    successDiv.classList.add('active');
}

function showLoading() {
    document.getElementById('loading').classList.add('active');
}

function clearLoading() {
    document.getElementById('loading').classList.remove('active');
}

function showParams(params, plotType) {
    const paramsDisplay = document.getElementById('params-display');
    const paramsHtml = Object.entries(params)
        .map(([key, value]) => `<strong>${key}:</strong> ${value === -1 ? '(any)' : value}`)
        .join('<br>');

    paramsDisplay.innerHTML = `<h3>Active Parameters (${plotType})</h3><p>${paramsHtml}</p>`;
    paramsDisplay.classList.add('active');
}

// Database Query Functions
function queryDatabase(query, params = []) {
    if (!db) {
        throw new Error('Database not loaded');
    }

    const stmt = db.prepare(query);
    stmt.bind(params);

    const result = [];
    while (stmt.step()) {
        const row = stmt.getAsObject();
        result.push(row);
    }
    stmt.free();

    return result;
}

function getParam(id) {
    const value = document.getElementById(id).value;
    if (value === '' || value === '-1') return -1;
    return isNaN(value) ? value : parseInt(value);
}

function queryHistoricalPlot(machine, op, dt, threads, tag, m, n, k) {
    let query = 'SELECT timestamp, gflops FROM run WHERE 1=1';
    const params = [];

    if (machine !== -1) {
        query += ' AND machine = ?';
        params.push(machine);
    }
    if (op !== -1) {
        query += ' AND op = ?';
        params.push(op);
    }
    if (dt !== -1) {
        query += ' AND dt = ?';
        params.push(dt);
    }
    if (threads !== -1) {
        query += ' AND threads = ?';
        params.push(threads);
    }
    if (tag !== -1) {
        query += ' AND tag = ?';
        params.push(tag);
    }
    if (m !== -1) {
        query += ' AND m = ?';
        params.push(m);
    }
    if (n !== -1) {
        query += ' AND n = ?';
        params.push(n);
    }
    if (k !== -1) {
        query += ' AND k = ?';
        params.push(k);
    }

    query += ' ORDER BY timestamp ASC';

    return queryDatabase(query, params);
}

function queryScalingPlot(git, machine, op, dt, threads, m, n, k) {
    let query = 'SELECT m, n, k, gflops FROM run WHERE git = ?';
    const params = [git];

    // Determine varying dimension
    let varyingDim;
    if (m === -1) varyingDim = 'm';
    else if (n === -1) varyingDim = 'n';
    else if (k === -1) varyingDim = 'k';
    else varyingDim = 'm'; // Default if all specified

    if (machine !== -1) {
        query += ' AND machine = ?';
        params.push(machine);
    }
    if (op !== -1) {
        query += ' AND op = ?';
        params.push(op);
    }
    if (dt !== -1) {
        query += ' AND dt = ?';
        params.push(dt);
    }
    if (threads !== -1) {
        query += ' AND threads = ?';
        params.push(threads);
    }
    if (m !== -1) {
        query += ' AND m = ?';
        params.push(m);
    }
    if (n !== -1) {
        query += ' AND n = ?';
        params.push(n);
    }
    if (k !== -1) {
        query += ' AND k = ?';
        params.push(k);
    }

    query += ` ORDER BY ${varyingDim} ASC`;

    const rows = queryDatabase(query, params);
    return { rows, varyingDim };
}

function queryOverviewPlot(git, machine, threads, dt, m, n, k) {
    let query = 'SELECT op, gflops FROM run WHERE git = ?';
    const params = [git];

    if (machine !== -1) {
        query += ' AND machine = ?';
        params.push(machine);
    }
    if (dt !== -1) {
        query += ' AND dt = ?';
        params.push(dt);
    }
    if (threads !== -1) {
        query += ' AND threads = ?';
        params.push(threads);
    }
    if (m !== -1) {
        query += ' AND (m = ? OR m = -1)';
        params.push(m);
    }
    if (n !== -1) {
        query += ' AND (n = ? OR n = -1)';
        params.push(n);
    }
    if (k !== -1) {
        query += ' AND (k = ? OR k = -1)';
        params.push(k);
    }

    query += ' ORDER BY op ASC';

    return queryDatabase(query, params);
}

// Charting Functions
function renderChart(data) {
    const ctx = document.getElementById('chart').getContext('2d');

    if (chartInstance) {
        chartInstance.destroy();
    }

    const chartConfig = {
        type: data.chart.type,
        data: {
            labels: data.chart.labels,
            datasets: data.chart.datasets
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top'
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 10
                    },
                    title: {
                        display: true,
                        text: 'Performance (GFLOP/s)'
                    }
                }
            }
        }
    };

    if (data.chart.type === 'line') {
        chartConfig.options.scales.y.grid = {
            drawBorder: true,
            color: 'rgba(0, 0, 0, 0.1)',
            lineWidth: 1
        };
    }

    chartInstance = new Chart(ctx, chartConfig);
    document.getElementById('chart-container').classList.add('active');
}

// Main Plot Generation Function
function generatePlot() {
    try {
        clearMessages();

        if (!db) {
            showError('Please load a database first');
            return;
        }

        showLoading();

        const plotType = document.getElementById('plot-type').value;
        const machine = getParam('machine');
        const dt = getParam('dt');
        const threads = getParam('threads');
        const m = getParam('m');
        const n = getParam('n');
        const k = getParam('k');

        const result = {
            type: plotType,
            params: { machine, dt, threads, m, n, k }
        };

        let rows;

        if (plotType === 'historical') {
            const tag = getParam('tag');
            const op = getParam('op');

            if (!tag || tag === -1) {
                throw new Error('Tag is required for Historical plots');
            }
            if (!op || op === -1) {
                throw new Error('Operation is required for Historical plots');
            }

            result.params.tag = tag;
            result.params.op = op;

            rows = queryHistoricalPlot(machine, op, dt, threads, tag, m, n, k);

            // Group by date and keep max gflops for each date
            const dataByDate = {};
            rows.forEach(row => {
                const date = new Date(row.timestamp).toISOString().split('T')[0];
                if (!dataByDate[date]) {
                    dataByDate[date] = row.gflops;
                } else {
                    dataByDate[date] = Math.max(dataByDate[date], row.gflops);
                }
            });

            const labels = Object.keys(dataByDate);
            const data = labels.map(date => dataByDate[date]);

            result.chart = {
                type: 'line',
                labels,
                datasets: [{
                    label: 'Performance (GFLOP/s)',
                    data,
                    borderColor: 'rgb(75, 192, 192)',
                    backgroundColor: 'rgba(75, 192, 192, 0.1)',
                    tension: 0.1
                }]
            };

        } else if (plotType === 'scaling') {
            const git = getParam('git-scaling');
            const op = getParam('op-scaling');

            if (!git || git === -1) {
                throw new Error('Git commit is required for Scaling plots');
            }
            if (!op || op === -1) {
                throw new Error('Operation is required for Scaling plots');
            }

            result.params.git = git;
            result.params.op = op;

            const { rows: scalingRows, varyingDim } = queryScalingPlot(git, machine, op, dt, threads, m, n, k);

            const dataByDim = {};
            scalingRows.forEach(row => {
                const dimValue = row[varyingDim];
                if (!dataByDim[dimValue]) dataByDim[dimValue] = [];
                dataByDim[dimValue].push(row.gflops);
            });

            const labels = Object.keys(dataByDim).map(Number).sort((a, b) => a - b);
            const data = labels.map(label => {
                const values = dataByDim[label];
                return Math.max(...values);
            });

            result.chart = {
                type: 'line',
                labels: labels.map(String),
                datasets: [{
                    label: `Performance vs ${varyingDim.toUpperCase()} (GFLOP/s)`,
                    data,
                    borderColor: 'rgb(153, 102, 255)',
                    backgroundColor: 'rgba(153, 102, 255, 0.1)',
                    tension: 0.1
                }]
            };

        } else if (plotType === 'overview') {
            const git = getParam('git-overview');

            if (!git || git === -1) {
                throw new Error('Git commit is required for Overview plots');
            }
            if (m === -1 || n === -1 || k === -1) {
                throw new Error('M, N, and K must all be specified for Overview plots');
            }

            result.params.git = git;

            rows = queryOverviewPlot(git, machine, threads, dt, m, n, k);

            const dataByOp = {};
            rows.forEach(row => {
                if (!dataByOp[row.op]) dataByOp[row.op] = [];
                dataByOp[row.op].push(row.gflops);
            });

            const labels = Object.keys(dataByOp).sort();
            const data = labels.map(label => {
                const values = dataByOp[label];
                return Math.max(...values);
            });

            const colors = [
                'rgb(255, 99, 132)',
                'rgb(54, 162, 235)',
                'rgb(255, 206, 86)',
                'rgb(75, 192, 192)',
                'rgb(153, 102, 255)',
                'rgb(255, 159, 64)'
            ];

            result.chart = {
                type: 'bar',
                labels,
                datasets: [{
                    label: 'Performance (GFLOP/s)',
                    data,
                    backgroundColor: colors.slice(0, labels.length)
                }]
            };
        }

        if (!result.chart.labels || result.chart.labels.length === 0) {
            throw new Error('No data found matching the specified criteria');
        }

        showParams(result.params, result.type);
        clearLoading();
        renderChart(result);

    } catch (error) {
        showError(`Error: ${error.message}`);
        clearLoading();
    }
}

// Event Listeners
document.addEventListener('DOMContentLoaded', function() {
    // Allow Enter to generate plot
    document.addEventListener('keypress', (event) => {
        if (event.key === 'Enter' && event.target.closest('.control-panel')) {
            generatePlot();
        }
    });
});
