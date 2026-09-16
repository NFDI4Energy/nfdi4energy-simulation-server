const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const fileListEl = document.getElementById('file-list');
const submitBtn = document.getElementById('submit-btn');

const mosaikDropZone = document.getElementById('mosaik-drop-zone');
const mosaikFileInput = document.getElementById('mosaik-file-input');
const mosaikFileListEl = document.getElementById('mosaik-file-list');
const submitMosaikBtn = document.getElementById('submit-mosaik-btn');

const villasDropZone = document.getElementById('villas-drop-zone');
const villasFileInput = document.getElementById('villas-file-input');
const villasFileListEl = document.getElementById('villas-file-list');
const submitVillasBtn = document.getElementById('submit-villas-btn');

let selectedFiles = [];
let selectedMosaikFile = null;
let selectedVillasFile = null;

document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
});

function switchTab(tab) {
    document.querySelectorAll('.tab-btn').forEach(b => {
        b.classList.toggle('active', b.dataset.tab === tab);
    });
    document.getElementById('daceds-card').classList.toggle('hidden', tab !== 'daceds');
    document.getElementById('mosaik-card').classList.toggle('hidden', tab !== 'mosaik');
    document.getElementById('villas-card').classList.toggle('hidden', tab !== 'villas');
}

// --- DaceDS Drag & Drop ---
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    addFiles(e.dataTransfer.files);
});

fileInput.addEventListener('change', () => {
    addFiles(fileInput.files);
    fileInput.value = '';
});

function addFiles(fileListObj) {
    for (const f of fileListObj) {
        if (!selectedFiles.find(s => s.name === f.name && s.size === f.size)) {
            selectedFiles.push(f);
        }
    }
    renderFileList();
}

function removeFile(index) {
    selectedFiles.splice(index, 1);
    renderFileList();
}

function formatSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function renderFileList() {
    fileListEl.innerHTML = selectedFiles.map((f, i) =>
        `<li>
            <span class="name">${f.name}</span>
            <span class="size">${formatSize(f.size)}</span>
            <button class="remove" onclick="removeFile(${i})">✕</button>
        </li>`
    ).join('');
    submitBtn.disabled = selectedFiles.length === 0;
}

// --- Mosaik Drag & Drop ---
mosaikDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    mosaikDropZone.classList.add('dragover');
});

mosaikDropZone.addEventListener('dragleave', () => {
    mosaikDropZone.classList.remove('dragover');
});

mosaikDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    mosaikDropZone.classList.remove('dragover');
    handleMosaikFiles(e.dataTransfer.files);
});

mosaikFileInput.addEventListener('change', () => {
    handleMosaikFiles(mosaikFileInput.files);
    mosaikFileInput.value = '';
});

function handleMosaikFiles(fileListObj) {
    if (fileListObj.length > 0) {
        selectedMosaikFile = fileListObj[0];
        renderMosaikFileList();
    }
}

function removeMosaikFile() {
    selectedMosaikFile = null;
    renderMosaikFileList();
}

function renderMosaikFileList() {
    if (selectedMosaikFile) {
        mosaikFileListEl.innerHTML =
            `<li>
                <span class="name">${selectedMosaikFile.name}</span>
                <span class="size">${formatSize(selectedMosaikFile.size)}</span>
                <button class="remove" onclick="removeMosaikFile()">✕</button>
            </li>`;
        submitMosaikBtn.disabled = false;
    } else {
        mosaikFileListEl.innerHTML = '';
        submitMosaikBtn.disabled = true;
    }
}


// --- VILLAS Drag & Drop ---
villasDropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    villasDropZone.classList.add('dragover');
});

villasDropZone.addEventListener('dragleave', () => {
    villasDropZone.classList.remove('dragover');
});

villasDropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    villasDropZone.classList.remove('dragover');
    handleVillasFiles(e.dataTransfer.files);
});

villasFileInput.addEventListener('change', () => {
    handleVillasFiles(villasFileInput.files);
    villasFileInput.value = '';
});

function handleVillasFiles(fileListObj) {
    if (fileListObj.length > 0) {
        selectedVillasFile = fileListObj[0];
        renderVillasFileList();
    }
}

function removeVillasFile() {
    selectedVillasFile = null;
    renderVillasFileList();
}

function renderVillasFileList() {
    if (selectedVillasFile) {
        villasFileListEl.innerHTML =
            `<li>
                <span class="name">${selectedVillasFile.name}</span>
                <span class="size">${formatSize(selectedVillasFile.size)}</span>
                <button class="remove" onclick="removeVillasFile()">✕</button>
            </li>`;
        submitVillasBtn.disabled = false;
    } else {
        villasFileListEl.innerHTML = '';
        submitVillasBtn.disabled = true;
    }
}


// --- Submit ---
const FRAMEWORKS = { daceds: 'dacedsx', mosaik: 'mosaik', villas: 'villas' };

async function submitSimulation(framework) {
    const frameworkName = FRAMEWORKS[framework];
    const endpoint = '/submit/' + frameworkName;
    let files;
    let submitBtn;

    switch (framework) {
      case 'mosaik':
        files = [selectedMosaikFile];
        submitBtn = submitMosaikBtn;
        break;
      case 'villas':
        files = [selectedVillasFile];
        submitBtn = submitVillasBtn;
        break;
      default:
        files = selectedFiles;
        submitBtn = submitBtn;
        break;
    };
      

    submitBtn.disabled = true;
    submitBtn.textContent = 'Uploading...';

    const formData = new FormData();
    files.forEach(f => formData.append('files', f));

    try {
        const res = await fetch(endpoint, { method: 'POST', body: formData });
        const data = await res.json();

        if (!res.ok) {
            alert('Error: ' + (data.detail || 'Submission failed'));
            resetBtn(submitBtn, framework);
            return;
        }

        const taskId = data.task_id;
        document.getElementById(framework + '-status-card').classList.remove('hidden');
        document.getElementById(framework + '-task-id-display').textContent = 'Task ID: ' + taskId;
        setStatus('pending', 'Queued — waiting for a worker...', framework);

        let attempts = 0;
        const poll = setInterval(async () => {
            attempts++;
            if (attempts > 900) {
                clearInterval(poll);
                setStatus('error', 'Timeout: Worker did not respond.', framework);
                resetBtn(submitBtn, framework);
                return;
            }

            const check = await fetch('/check/' + taskId);
            const status = await check.json();

            if (status.status === 'RUNNING') {
                setStatus('running', 'Simulation is running...', framework);
            } else if (status.status === 'DONE') {
                clearInterval(poll);
                setStatus('done', 'Simulation complete!', framework);
                showResults(taskId, status.downloads || [], framework);
                resetBtn(submitBtn, framework);
            } else if (status.status === 'ERROR') {
                clearInterval(poll);
                setStatus('error', 'Error: ' + (status.error || 'Unknown error'), framework);
                resetBtn(submitBtn, framework);
            }
        }, 2000);

    } catch (err) {
        alert('Network error: ' + err.message);
        resetBtn(submitBtn, framework);
    }
}

function resetBtn(btn, framework) {
    btn.disabled = false;
    switch (framework) {
      case 'mosaik':
        btn.textContent = 'Submit Mosaik Simulation';
        break;
      case 'villas':
        btn.textContent = 'Submit VILLASnode Configuration'
        break;
      default:
        btn.textContent = 'Submit Simulation';
        break;
    };
}

function setStatus(type, message, framework) {
    const bar = document.getElementById(framework + '-status-bar');
    bar.className = 'status-bar ' + type;
    document.getElementById(framework + '-status-text').textContent = message;
    document.getElementById(framework + '-status-spinner').style.display =
        (type === 'done' || type === 'error') ? 'none' : 'block';
}

function showResults(taskId, downloads, framework) {
    const resultsCard = document.getElementById(framework + '-results-card');
    const resultsList = document.getElementById(framework + '-results-list');
    resultsCard.classList.remove('hidden');

    if (downloads.length === 0) {
        resultsList.innerHTML = '<li>No result files found.</li>';
        return;
    }

    resultsList.innerHTML = downloads.map(url => {
        const filename = url.substring(url.lastIndexOf('/') + 1);
        return `<li><a href="${url}" download>${filename}</a></li>`;
    }).join('');
}

function resetForm(framework) {
    switch (framework) {
      case 'mosaik':
        selectedMosaikFile = null;
        renderMosaikFileList();
        submitMosaikBtn.disabled = true;
        submitMosaikBtn.textContent = 'Submit Mosaik Simulation';
      case 'villas':
        selectedVillasFile = null;
        renderVillasFileList();
        submitVillasBtn.disabled = true;
        submitVillasBtn.textContent = 'Submit VILLAS Configuration';
      default:
        selectedFiles = [];
        renderFileList();
        submitBtn.disabled = selectedFiles.length === 0;
        submitBtn.textContent = 'Submit Simulation';
    };
    document.getElementById(framework + '-status-card').classList.add('hidden');
    document.getElementById(framework + '-results-card').classList.add('hidden');
    document.getElementById(framework + '-status-text').textContent = '';
    document.getElementById(framework + '-task-id-display').textContent = '';
}
