// ── State ──────────────────────────────────────
const state = {
    sessionId: null,
    chapters: [],
    templateFile: null,
    sourceFiles: [],
    reviewMode: null,
};

const API = "/api";

// ── Helpers ────────────────────────────────────
function $(sel) { return document.querySelector(sel); }
function show(stepId) {
    document.querySelectorAll(".step").forEach(s => s.classList.remove("active"));
    document.getElementById(stepId).classList.add("active");
}

function setStatus(text) {
    $("#status-badge").textContent = text;
}

async function api(method, path, body = null) {
    const opts = { method, headers: {} };
    if (body && !(body instanceof FormData)) {
        opts.headers["Content-Type"] = "application/json";
        opts.body = JSON.stringify(body);
    } else if (body) {
        opts.body = body;
    }
    const res = await fetch(API + path, opts);
    return res.json();
}

// ── Step 1: Upload ─────────────────────────────
function initUpload() {
    // Template drop zone
    const templateDrop = $("#template-drop");
    const templateInput = $("#template-input");

    templateDrop.addEventListener("click", () => templateInput.click());
    templateDrop.addEventListener("dragover", e => {
        e.preventDefault();
        templateDrop.classList.add("drag-over");
    });
    templateDrop.addEventListener("dragleave", () => templateDrop.classList.remove("drag-over"));
    templateDrop.addEventListener("drop", e => {
        e.preventDefault();
        templateDrop.classList.remove("drag-over");
        if (e.dataTransfer.files.length) {
            state.templateFile = e.dataTransfer.files[0];
            showTemplateInfo();
        }
    });
    templateInput.addEventListener("change", () => {
        if (templateInput.files.length) {
            state.templateFile = templateInput.files[0];
            showTemplateInfo();
        }
    });

    // Source drop zone
    const sourceDrop = $("#source-drop");
    const sourceInput = $("#source-input");

    sourceDrop.addEventListener("click", () => sourceInput.click());
    sourceDrop.addEventListener("dragover", e => {
        e.preventDefault();
        sourceDrop.classList.add("drag-over");
    });
    sourceDrop.addEventListener("dragleave", () => sourceDrop.classList.remove("drag-over"));
    sourceDrop.addEventListener("drop", e => {
        e.preventDefault();
        sourceDrop.classList.remove("drag-over");
        for (const f of e.dataTransfer.files) {
            state.sourceFiles.push(f);
        }
        showSourceList();
    });
    sourceInput.addEventListener("change", () => {
        for (const f of sourceInput.files) {
            state.sourceFiles.push(f);
        }
        showSourceList();
    });

    // Start button
    $("#btn-start").addEventListener("click", startSession);
}

function showTemplateInfo() {
    const f = state.templateFile;
    $("#template-info").innerHTML = `<div class="file-item"><span class="name">${f.name}</span><span class="size">${(f.size / 1024).toFixed(1)} KB</span><span class="status">已选择</span></div>`;
    checkReady();
}

function showSourceList() {
    const list = $("#source-list");
    list.innerHTML = state.sourceFiles.map(f =>
        `<div class="file-item"><span class="name">${f.name}</span><span class="size">${(f.size / 1024).toFixed(1)} KB</span><span class="status">已选择</span></div>`
    ).join("");
    checkReady();
}

function checkReady() {
    const ready = state.templateFile && state.sourceFiles.length > 0 && $("#requirement").value.trim();
    $("#btn-start").disabled = !ready;
}

async function startSession() {
    const requirement = $("#requirement").value.trim();

    // Create session
    const res = await api("POST", "/sessions", { requirement });
    state.sessionId = res.session_id;

    // Upload template
    const templatePath = await uploadFile(state.templateFile);

    // Set template
    await api("POST", `/sessions/${state.sessionId}/template`, {
        template_path: templatePath,
    });

    // Upload source files
    for (const f of state.sourceFiles) {
        await uploadFile(f);
    }

    // Update session with source paths
    show("step-confirm");
    setStatus("确认中");

    // Get confirm info
    const confirmRes = await api("POST", `/sessions/${state.sessionId}/confirm`);
    renderConfirm(confirmRes);
}

async function uploadFile(file) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("session_id", state.sessionId);

    const res = await fetch(`${API}/upload`, { method: "POST", body: fd });
    const data = await res.json();
    const info = data.files[0];
    return `uploads/${state.sessionId}/${info.filename}`;
}

function renderConfirm(data) {
    const html = `
        <div class="confirm-item">
            <div class="label">需求</div>
            <div class="value">${data.requirement}</div>
        </div>
        <div class="confirm-item">
            <div class="label">源文件 (${data.source_paths.length} 个)</div>
            <div class="value">${data.source_paths.map(p => p.split("/").pop()).join(", ")}</div>
        </div>
        <div class="confirm-item">
            <div class="label">章节 (${data.chapters.length} 个)</div>
            ${data.chapters.map(c => `<div class="value">${c.index}. ${c.title} — ${c.description}</div>`).join("")}
        </div>
    `;
    $("#confirm-content").innerHTML = html;
    state.chapters = data.chapters;
}

// ── Step 2: Confirm ────────────────────────────
function initConfirm() {
    $("#btn-confirm").addEventListener("click", async () => {
        show("step-materials");
        setStatus("提取素材");

        $("#materials-loading").style.display = "block";
        $("#materials-content").innerHTML = "";

        const res = await api("POST", `/sessions/${state.sessionId}/extract`);
        renderMaterials(res.overview);
    });
}

function renderMaterials(overview) {
    $("#materials-loading").style.display = "none";
    const html = overview.map(m => `
        <div class="material-card ${m.status === '素材不足' ? 'insufficient' : ''}">
            <div class="title">${m.index}. ${m.title}</div>
            <div class="detail">素材: ${m.chars} 字 — ${m.status}</div>
        </div>
    `).join("");
    $("#materials-content").innerHTML = html;
    $("#btn-materials-confirm").disabled = false;
}

// ── Step 3: Materials confirm ──────────────────
function initMaterials() {
    $("#btn-materials-confirm").addEventListener("click", async () => {
        await api("POST", `/sessions/${state.sessionId}/materials/confirm`);
        show("step-generate");
        setStatus("生成中");

        // Render chapter cards
        renderChapterCards();

        // Trigger generation
        await api("POST", `/sessions/${state.sessionId}/generate`);

        // Start SSE
        startSSE();
    });
}

function renderChapterCards() {
    const html = state.chapters.map(c => `
        <div class="chapter-card" id="chapter-${c.index}">
            <div class="chapter-header" onclick="toggleChapter(${c.index})">
                <div class="chapter-status pending" id="status-${c.index}">○</div>
                <div class="chapter-title">${c.index}. ${c.title}</div>
                <div class="chapter-chars" id="chars-${c.index}"></div>
            </div>
            <div class="chapter-body" id="body-${c.index}">
                <pre id="content-${c.index}"></pre>
                <div class="revise-area">
                    <input type="text" id="revise-${c.index}" placeholder="输入修改意见...">
                    <button class="btn-secondary" onclick="reviseChapter(${c.index})">修改</button>
                </div>
            </div>
        </div>
    `).join("");
    $("#chapters-panel").innerHTML = html;
}

// ── SSE ────────────────────────────────────────
function startSSE() {
    const es = new EventSource(`${API}/sessions/${state.sessionId}/stream`);
    let doneCount = 0;
    const total = state.chapters.length;

    es.addEventListener("chapter_start", e => {
        const data = JSON.parse(e.data);
        const el = document.getElementById(`status-${data.chapter}`);
        el.className = "chapter-status active";
        el.textContent = "...";
    });

    es.addEventListener("chunk", e => {
        const data = JSON.parse(e.data);
        const el = document.getElementById(`content-${data.chapter}`);
        el.textContent += data.text;
    });

    es.addEventListener("chapter_done", e => {
        const data = JSON.parse(e.data);
        doneCount++;
        const el = document.getElementById(`status-${data.chapter}`);
        el.className = "chapter-status done";
        el.textContent = "✓";
        document.getElementById(`chars-${data.chapter}`).textContent = `${data.chars} 字`;

        // Update progress
        const pct = (doneCount / total) * 100;
        $("#progress-fill").style.width = pct + "%";
        $("#progress-text").textContent = `${doneCount}/${total} 章节`;
    });

    es.addEventListener("all_done", () => {
        es.close();
        setStatus("审阅中");
        show("step-review");
        loadReview();
    });

    es.onerror = () => {
        es.close();
    };
}

// ── Chapter interaction ────────────────────────
function toggleChapter(idx) {
    const body = document.getElementById(`body-${idx}`);
    body.classList.toggle("open");
}

async function reviseChapter(idx) {
    const input = document.getElementById(`revise-${idx}`);
    const feedback = input.value.trim();
    if (!feedback) return;

    const res = await api("POST", `/sessions/${state.sessionId}/chapters/${idx}/revise`, { feedback });
    document.getElementById(`content-${idx}`).textContent = res.content;
    input.value = "";
}

// ── Step 5: Review ─────────────────────────────
async function loadReview() {
    const res = await api("GET", `/sessions/${state.sessionId}/chapters`);
    const tabs = res.chapters.map((c, i) =>
        `<button class="tab-btn ${i === 0 ? 'active' : ''}" onclick="showTab(${c.index})">${c.index}. ${c.title}</button>`
    ).join("");
    $("#review-tabs").innerHTML = tabs;

    if (res.chapters.length > 0) {
        showTab(res.chapters[0].index);
    }
}

async function showTab(idx) {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    event.target.classList.add("active");

    const res = await api("GET", `/sessions/${state.sessionId}/chapters/${idx}`);
    $("#review-content").innerHTML = `<pre>${res.content}</pre>`;
}

function initReview() {
    $("#btn-revise-global").addEventListener("click", async () => {
        const feedback = $("#global-feedback").value.trim();
        if (!feedback) return;

        const res = await api("POST", `/sessions/${state.sessionId}/revise-global`, { feedback });
        $("#review-content").innerHTML = `<pre>${res.content}</pre>`;
        $("#global-feedback").value = "";
    });

    $("#btn-download").addEventListener("click", async () => {
        const res = await api("GET", `/sessions/${state.sessionId}/output`);
        const blob = new Blob([res.content], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "output.md";
        a.click();
        URL.revokeObjectURL(url);
    });
}

// ── Init ───────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
    initUpload();
    initConfirm();
    initMaterials();
    initReview();

    $("#requirement").addEventListener("input", checkReady);
});
