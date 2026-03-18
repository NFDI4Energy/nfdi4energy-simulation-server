const scenarioDrop = document.getElementById('scenario-drop-zone');
const scenarioInput = document.getElementById('scenario-input');
const scenarioListEl = document.getElementById('scenario-list');

const resourceDrop = document.getElementById('resource-drop-zone');
const resourceInput = document.getElementById('resource-input');
const resourceListEl = document.getElementById('resource-list');

const submitBtn = document.getElementById('submit-btn');

let scenarioFile = null;
let resourceFiles = [];

function setupDropZone(zone, input, isScenario) {
    zone.addEventListener('dragover', (e) => {
        e.preventDefault();
        zone.classList.add('dragover');
    });

    zone.addEventListener('dragleave', () => {
        zone.classList.remove('dragover');
    });

    zone.addEventListener('drop', (e) => {
        e.preventDefault();
        zone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files, isScenario);
    });

    input.addEventListener('change', () => {
        handleFiles(input.files, isScenario);
        input.value = '';
    });
}

setupDropZone(scenarioDrop, scenarioInput, true);
setupDropZone(resourceDrop, resourceInput, false);

function handleFiles(files, isScenario) {
    if (files.length === 0) return;
    
    if (isScenario) {
        // Take only the first file for scenario
        scenarioFile = files[0];
    } else {
        // Add multiple files for resources
        for (const f of files) {
            if (!resourceFiles.find(s => s.name === f.name && s.size === f.size)) {
                resourceFiles.push(f);
            }
        }
    }
    renderFiles();
}

function removeScenario() {
    scenarioFile = null;
    renderFiles();
}

function removeResource(index) {
    resourceFiles.splice(index, 1);
    renderFiles();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function renderFiles() {
    if (scenarioFile) {
        scenarioListEl.innerHTML = `<li><span class="name">${scenarioFile.name}</span> <span class="size">${formatSize(scenarioFile.size)}</span><button class="remove" onclick="removeScenario()">✕</button></li>`;
    } else {
        scenarioListEl.innerHTML = '';
    }

    resourceListEl.innerHTML = resourceFiles.map((f, i) =>
        `<li><span class="name">${f.name}</span> <span class="size">${formatSize(f.size)}</span><button class="remove" onclick="removeResource(${i})">✕</button></li>`
    ).join('');

    submitBtn.disabled = !scenarioFile;
}

// --- Submit ---
async function submitSimulation() {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Uploading...';

    const formData = new FormData();
    formData.append('scenario_file', scenarioFile);
    resourceFiles.forEach(f => formData.append('resource_files', f));

    try {
        const res = await fetch('/submit', { method: 'POST', body: formData });
        const data = await res.json();

        if (!res.ok) {
            alert('Error: ' + (data.error || 'Submission failed'));
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Simulation';
            return;
        }

        const taskId = data.task_id;

        // Show status card
        document.getElementById('upload-card').classList.add('hidden');
        document.getElementById('status-card').classList.remove('hidden');
        document.getElementById('task-id-display').textContent = 'Task ID: ' + taskId;
        setStatus('pending', 'Queued — waiting for a worker...');

        // Poll for results
        const poll = setInterval(async () => {
            const check = await fetch('/check/' + taskId);
            const status = await check.json();

            if (status.status === 'RUNNING') {
                setStatus('running', 'Simulation is running...');
            } else if (status.status === 'DONE') {
                clearInterval(poll);
                setStatus('done', 'Simulation complete!');
                showResults(taskId, status.downloads || []);
            } else if (status.status === 'ERROR') {
                clearInterval(poll);
                setStatus('error', 'Error: ' + (status.error || 'Unknown error'));
            }
        }, 2000);

    } catch (err) {
        alert('Network error: ' + err.message);
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Simulation';
    }
}

function setStatus(type, message) {
    const bar = document.getElementById('status-bar');
    bar.className = 'status-bar ' + type;
    document.getElementById('status-text').textContent = message;
    document.getElementById('status-spinner').style.display =
        (type === 'done' || type === 'error') ? 'none' : 'block';
}

function showResults(taskId, downloads) {
    const resultsCard = document.getElementById('results-card');
    const resultsList = document.getElementById('results-list');
    resultsCard.classList.remove('hidden');

    if (downloads.length === 0) {
        resultsList.innerHTML = '<li>No result files found.</li>';
        return;
    }

    resultsList.innerHTML = downloads.map(url => {
        const filename = url.split('/').pop();
        return `<li><a href="${url}" download>${filename}</a></li>`;
    }).join('');
}

function resetForm() {
    scenarioFile = null;
    resourceFiles = [];
    renderFiles();
    submitBtn.disabled = true;
    submitBtn.textContent = 'Submit Simulation';
    document.getElementById('upload-card').classList.remove('hidden');
    document.getElementById('status-card').classList.add('hidden');
    document.getElementById('results-card').classList.add('hidden');
}
