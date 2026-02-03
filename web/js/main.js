let currentMods = [];
let currentPage = 0;
let currentQuery = '';
let selectedMods = new Set();
let currentView = 'marketplace';

/**
 * Selection Management
 */
function toggleModSelection(modId, isChecked, view) {
    modId = Number(modId);
    if (isChecked) {
        selectedMods.add(modId);
    } else {
        selectedMods.delete(modId);
    }
    updateBatchActionsVisibility(view);
}

function updateBatchActionsVisibility(view) {
    const bar = document.getElementById(`${view}-batch-actions`);
    const countEl = document.getElementById(`${view}-selected-count`);

    if (!bar) return;

    if (selectedMods.size > 0) {
        bar.style.display = 'flex';
        countEl.innerText = `${selectedMods.size} selecionado${selectedMods.size > 1 ? 's' : ''}`;
    } else {
        bar.style.display = 'none';
    }
}

function clearSelection() {
    selectedMods.clear();
    // Uncheck all checkboxes and remove selected class
    document.querySelectorAll('.mod-card-checkbox').forEach(cb => cb.checked = false);
    document.querySelectorAll('.mod-card.selected').forEach(card => card.classList.remove('selected'));

    // Hide all bars
    ['library', 'pack'].forEach(view => {
        const bar = document.getElementById(`${view}-batch-actions`);
        if (bar) bar.style.display = 'none';
    });
}

/**
 * Custom Modal System - Replaces alert, confirm, prompt
 * @param {string} type - 'alert', 'confirm', 'prompt'
 * @param {string} title - Modal Title
 * @param {string} message - Content message
 * @param {string} defaultValue - For 'prompt' default text
 */
function showAppModal(type, title, message, defaultValue = "") {
    return new Promise((resolve) => {
        const overlay = document.getElementById('app-modal-overlay');
        const modal = document.getElementById('app-modal');
        const titleEl = document.getElementById('app-modal-title');
        const msgEl = document.getElementById('app-modal-message');
        const inputEl = document.getElementById('app-modal-input');
        const actionsEl = document.getElementById('app-modal-actions');

        titleEl.innerText = title;
        msgEl.innerText = message;
        inputEl.style.display = type === 'prompt' ? 'block' : 'none';
        inputEl.value = defaultValue;
        actionsEl.innerHTML = '';

        const close = (val) => {
            overlay.style.display = 'none';
            modal.classList.remove('active');
            resolve(val);
        };

        if (type === 'alert') {
            const btn = document.createElement('button');
            btn.className = 'app-modal-btn app-modal-btn-confirm';
            btn.innerText = 'OK';
            btn.onclick = () => close(true);
            actionsEl.appendChild(btn);
        } else if (type === 'confirm' || type === 'prompt') {
            const btnCancel = document.createElement('button');
            btnCancel.className = 'app-modal-btn app-modal-btn-cancel';
            btnCancel.innerText = 'Cancelar';
            btnCancel.onclick = () => close(type === 'prompt' ? null : false);
            actionsEl.appendChild(btnCancel);

            const btnOk = document.createElement('button');
            btnOk.className = 'app-modal-btn app-modal-btn-confirm';
            btnOk.innerText = 'Confirmar';
            btnOk.onclick = () => close(type === 'prompt' ? inputEl.value : true);
            actionsEl.appendChild(btnOk);
        }

        overlay.style.display = 'flex';
        setTimeout(() => modal.classList.add('active'), 10);
        if (type === 'prompt') inputEl.focus();
    });
}

// Proxies for easy usage (Async only)
async function alertApp(msg, title = "Aviso") { return await showAppModal('alert', title, msg); }
async function confirmApp(msg, title = "Confirmação") { return await showAppModal('confirm', title, msg); }
async function promptApp(msg, def = "", title = "Entrada") { return await showAppModal('prompt', title, msg, def); }

// Esperar API do PyWebView

window.addEventListener('pywebviewready', async () => {
    // Config
    try {
        let config = {};
        if (window.pywebview.api.get_config_py) {
            config = await window.pywebview.api.get_config_py();
        } else if (window.pywebview.api.load_config_py) {
            config = await window.pywebview.api.load_config_py();
        }

        document.getElementById('api-key-input').value = config.api_key || '';
        document.getElementById('game-dir-input').value = config.game_dir || '';
        document.getElementById('manage-saves-input').checked = config.manage_saves || false;

        // Gemini
        document.getElementById('gemini-key-input').value = config.gemini_api_key || '';
        if (config.gemini_model) document.getElementById('gemini-model-select').value = config.gemini_model;

        // Translation (New)
        if (config.translation_lang) document.getElementById('setting-trans-lang').value = config.translation_lang;
        if (config.auto_translate !== undefined) document.getElementById('setting-trans-auto').checked = config.auto_translate;

        window.appConfig = config; // Cache global
        activePackName = config.active_modpack;

        // Check key
        if (!config.api_key) {
            switchView('settings');
            console.log("Bem vindo! Configure sua API Key.");
        } else {
            runSearch();
        }

        // Check for updates on startup
        checkUpdates();

    } catch (e) {
        console.error("Erro inicialização", e);
    }
});

// --- Search & Marketplace ---
async function handleSearch(e) {
    if (e.key === 'Enter') runSearch();
}

async function runSearch() {
    currentPage = 0; // Reset pagination on new search
    currentQuery = document.getElementById('search-input').value;
    await fetchMods(currentPage);
}

async function changePage(delta) {
    currentPage += delta;
    if (currentPage < 0) currentPage = 0;
    await fetchMods(currentPage);
}

async function fetchMods(page) {
    const grid = document.getElementById('mod-grid');
    const sort = parseInt(document.getElementById('sort-select').value);

    // Update Controls
    const ind = document.getElementById('page-indicator');
    if (ind) ind.innerText = `Página ${page + 1}`;

    const btnPrev = document.getElementById('btn-prev');
    if (btnPrev) btnPrev.disabled = (page === 0);

    grid.innerHTML = '<div style="width:100%; text-align:center; padding:40px"><div class="loading-spinner"></div> Buscando...</div>';

    const offset = page * 20;

    try {
        // Call Python API
        const mods = await window.pywebview.api.search_mods_py(currentQuery, sort, offset);

        if (mods.error) {
            grid.innerHTML = `<div style="color:var(--error-color)">Erro: ${mods.error}</div>`;
            return;
        }

        const btnNext = document.getElementById('btn-next');
        if (mods.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:40px; color:var(--text-secondary)">Nenhum mod encontrado nesta página.</div>';
            if (btnNext) btnNext.disabled = true;
            return;
        }

        if (btnNext) btnNext.disabled = (mods.length < 20);

        currentMods = mods;
        renderMods(currentMods);
    } catch (e) {
        grid.innerHTML = `<div style="color:var(--error-color)">Erro de comunicação: ${e}</div>`;
    }
}

/**
 * Updates all instances of a mod's download button across the UI
 */
function updateModButtonsState(modId, isInstalled) {
    modId = Number(modId);

    // Update global state cache
    const mod = currentMods.find(m => m.id === modId);
    if (mod) mod.isInstalled = isInstalled;

    // Update Marketplace Grid Buttons
    const gridButtons = document.querySelectorAll(`.btn-install[data-mod-id="${modId}"]`);
    gridButtons.forEach(btn => {
        if (isInstalled) {
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Instalado';
            btn.style.background = '#10b981';
            btn.style.cursor = 'default';
            btn.style.opacity = '0.8';
            btn.disabled = true;
            btn.onclick = null;
        }
    });

    // Update Details Page Button
    const detailBtn = document.getElementById('detail-btn-install');
    if (detailBtn && detailBtn.dataset.modId == modId) {
        if (isInstalled) {
            detailBtn.innerHTML = '<i class="fa-solid fa-check"></i> Instalado';
            detailBtn.style.background = '#10b981';
            detailBtn.style.cursor = 'default';
            detailBtn.disabled = true;
            detailBtn.onclick = null;
        }
    }
}

function renderMods(mods) {
    const modGrid = document.getElementById('mod-grid');
    modGrid.innerHTML = '';
    if (!mods || mods.length === 0) {
        modGrid.innerHTML = '<div style="color:var(--text-secondary); padding:20px">Nada encontrado.</div>'; return;
    }

    mods.forEach(mod => {
        // Safe access
        const thumb = mod.logo?.url || 'assets/placeholder.png';
        const downloads = new Intl.NumberFormat('pt-BR').format(mod.downloadCount);

        const card = document.createElement('div');
        card.className = 'mod-card';
        // Make whole card clickable for details
        card.innerHTML = `
            <div class="card-image" style="background-image: url('${thumb}'); cursor:pointer" onclick="openModDetails(${mod.id})"></div>
            <div class="card-content">
                <div class="card-title-row">
                    <div class="card-title" style="cursor:pointer" onclick="openModDetails(${mod.id})">${mod.name}</div>
                </div>
                <div class="card-meta">Down: ${downloads}</div>
                ${mod.isInstalled ?
                `<button class="btn-install" data-mod-id="${mod.id}" disabled style="background:#10b981; cursor:default; opacity:0.8"><i class="fa-solid fa-check"></i> Instalado</button>` :
                `<button class="btn-install" data-mod-id="${mod.id}" onclick="installMod(${mod.id}, this)"><i class="fa-solid fa-download"></i> Baixar</button>`
            }
            </div>
        `;
        modGrid.appendChild(card);
    });
}

async function openModDetails(modId) {
    modId = Number(modId);
    // Try to find in current search results
    let mod = currentMods.find(m => m.id === modId);
    let extendedInfo = null;

    if (!mod) {
        // Not in current list (e.g. from Sidebar or Link). Fetch from API.
        // We use extended info because it now returns 'info' as well.
        // Show a loading indicator if needed, but for now we just wait.
        try {
            extendedInfo = await window.pywebview.api.get_mod_extended_info_py(modId);
            if (extendedInfo && extendedInfo.info) {
                mod = extendedInfo.info;
                // Cache for metadata persistence (e.g. for installMod)
                if (!currentMods.find(m => m.id === mod.id)) {
                    currentMods.push(mod);
                }
            } else {
                console.error("Mod needs fetch but failed");
                return;
            }
        } catch (e) {
            console.error("Error fetching mod details:", e);
            return;
        }
    }

    switchView('moddetails');

    // 1. Populate Header
    document.getElementById('detail-title').innerText = mod.name;
    document.getElementById('detail-summary').innerText = mod.summary;
    document.getElementById('detail-downloads').innerText = `${new Intl.NumberFormat('pt-BR').format(mod.downloadCount)} Downloads`;
    document.getElementById('detail-date').innerText = `Atualizado: ${new Date(mod.dateModified).toLocaleDateString()}`;

    const icon = document.getElementById('detail-icon');
    icon.style.backgroundImage = `url('${mod.logo?.url || 'assets/placeholder.png'}')`;

    // Setup Install Button in Details
    const btn = document.getElementById('detail-btn-install');
    const newBtn = btn.cloneNode(true);
    btn.parentNode.replaceChild(newBtn, btn);

    if (mod.isInstalled) {
        newBtn.innerHTML = '<i class="fa-solid fa-check"></i> Instalado';
        newBtn.style.background = '#10b981';
        newBtn.disabled = true;
        newBtn.style.cursor = 'default';
        newBtn.onclick = null;
    } else {
        newBtn.innerHTML = '<i class="fa-solid fa-download"></i> Baixar';
        // Check local library logic vs backend isInstalled logic. 
        // Note: fetch above included isInstalled. currentMods included isInstalled.
        newBtn.style.background = 'var(--gradient-btn)';
        newBtn.disabled = false;
        newBtn.style.cursor = 'pointer';
        newBtn.dataset.modId = mod.id;
        newBtn.onclick = () => installMod(mod.id, newBtn);
    }

    // 2. Load Description
    const descContainer = document.getElementById('detail-description');
    descContainer.innerHTML = '<div style="padding:20px; text-align:center"><i class="fa-solid fa-spinner fa-spin"></i> Carregando descrição...</div>';
    delete descContainer.dataset.originalHtml; // Reset translation cache for the new mod

    try {
        const html = await window.pywebview.api.get_mod_description_py(mod.id);
        descContainer.innerHTML = html;
        // Basic CSS fixes for injected content
        descContainer.querySelectorAll('img').forEach(img => {
            img.style.maxWidth = '100%';
            img.style.height = 'auto';
        });

        // Add Translate Button Header
        const descHeader = descContainer.previousElementSibling; // The h3 header
        if (descHeader && descHeader.tagName === 'H3') {
            // Setup layout
            descHeader.style.display = 'flex';
            descHeader.style.justifyContent = 'space-between';
            descHeader.style.alignItems = 'center';

            // Remove existing button to reset state
            const existingBtn = descHeader.querySelector('.btn-translate');
            if (existingBtn) existingBtn.remove();

            const transBtn = document.createElement('button');
            transBtn.className = 'btn-translate';
            transBtn.innerHTML = '<i class="fa-solid fa-language"></i> Traduzir';
            transBtn.style.background = 'transparent';
            transBtn.style.border = '1px solid var(--primary-color)';
            transBtn.style.color = 'var(--primary-color)';
            transBtn.style.padding = '4px 10px';
            transBtn.style.borderRadius = '6px';
            transBtn.style.cursor = 'pointer';
            transBtn.style.fontSize = '0.8rem';

            transBtn.onclick = () => translateDescription(descContainer, transBtn);

            descHeader.appendChild(transBtn);

            // Auto Translate Trigger
            if (window.appConfig && window.appConfig.auto_translate) {
                // Show loading in the main container immediately
                descContainer.innerHTML = `
                    <div style="display:flex; flex-direction:column; align-items:center; justify-content:center; padding:40px; color:var(--text-secondary)">
                        <i class="fa-solid fa-language fa-spin" style="font-size:3rem; margin-bottom:15px; color:var(--primary-color)"></i>
                        <div style="font-size:1.1rem">Traduzindo descrição...</div>
                    </div>
                `;
                // Pass original 'html' so translation works on source, not on the spinner HTML
                translateDescription(descContainer, transBtn, html);
            }
        }

    } catch (e) {
        descContainer.innerHTML = "Erro ao carregar descrição.";
    }

    // 3. Load Extended Info (Sidebar)
    const sidebar = document.getElementById('detail-sidebar');
    if (sidebar) {
        // If we fetched it already (extendedInfo variable), use it. otherwise fetch now.
        if (extendedInfo) {
            renderSidebar(extendedInfo, sidebar);
        } else {
            sidebar.innerHTML = '<div style="text-align:center; padding:20px; color:var(--text-secondary)"><i class="fa-solid fa-spinner fa-spin"></i> Carregando info...</div>';
            try {
                const info = await window.pywebview.api.get_mod_extended_info_py(mod.id);
                renderSidebar(info, sidebar);
            } catch (e) {
                sidebar.innerHTML = "Info indisponível.";
            }
        }
    }
}

function renderSidebar(info, sidebarContainer) {
    sidebarContainer.innerHTML = '';

    // Similar Mods
    if (info.similar && info.similar.length > 0) {
        const simDiv = document.createElement('div');
        simDiv.style.background = 'var(--bg-card)';
        simDiv.style.padding = '20px';
        simDiv.style.borderRadius = '12px';
        simDiv.innerHTML = '<h4 style="margin-top:0; margin-bottom:15px; color:#a78bfa">Similares</h4>';

        info.similar.forEach(s => {
            const thumb = s.logo?.url || 'assets/placeholder.png';
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '10px';
            row.style.marginBottom = '10px';
            row.style.cursor = 'pointer';
            row.onclick = () => openModDetails(s.id);

            row.innerHTML = `
                <div style="width:40px; height:40px; background:url('${thumb}') center/cover; border-radius:6px; flex-shrink:0;"></div>
                <div style="overflow:hidden">
                    <div style="font-size:0.9rem; font-weight:bold; white-space:nowrap; overflow:hidden; text-overflow:ellipsis">${s.name}</div>
                    <div style="font-size:0.7rem; color:var(--text-secondary)">${new Intl.NumberFormat('pt-BR').format(s.downloadCount)} down</div>
                </div>
            `;
            simDiv.appendChild(row);
        });
        sidebarContainer.appendChild(simDiv);
    }

    // Dependencies
    if (info.dependencies && info.dependencies.length > 0) {
        const depDiv = document.createElement('div');
        depDiv.style.background = 'var(--bg-card)';
        depDiv.style.padding = '20px';
        depDiv.style.borderRadius = '12px';
        depDiv.innerHTML = '<h4 style="margin-top:0; margin-bottom:15px; color:#ef4444">Dependências</h4>';

        info.dependencies.forEach(d => {
            const thumb = d.logo?.url || 'assets/placeholder.png';
            const row = document.createElement('div');
            row.style.display = 'flex';
            row.style.gap = '10px';
            row.style.marginBottom = '10px';
            row.style.alignItems = 'center';
            const isInst = d.isInstalled;

            row.innerHTML = `
                <div style="width:30px; height:30px; background:url('${thumb}') center/cover; border-radius:6px; flex-shrink:0;"></div>
                <div style="flex-grow:1; font-size:0.85rem; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${d.name}</div>
                ${isInst ? '<i class="fa-solid fa-check" style="color:#10b981"></i>' : '<i class="fa-solid fa-triangle-exclamation" style="color:#ef4444" title="Necessário"></i>'}
            `;
            row.style.cursor = 'pointer';
            row.onclick = () => openModDetails(d.id);

            depDiv.appendChild(row);
        });
        sidebarContainer.appendChild(depDiv);
    }
}

async function installMod(modId, btn) {
    const original = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i>';
    btn.disabled = true;

    // Find metadata
    const modObj = currentMods.find(m => m.id === modId);
    let metadata = null;
    if (modObj) {
        metadata = {
            name: modObj.name,
            slug: modObj.slug,
            logo: modObj.logo,
            summary: modObj.summary,
            links: modObj.links // Include links for manual URL if needed
        };
    }

    try {
        const res = await window.pywebview.api.install_mod_py(modId, metadata);
        if (res.status === 'success') {
            updateModButtonsState(modId, true);
            console.log(res.message);
        } else if (res.status === 'manual_required') {
            await startManualDownloadAssistant(res, btn, original);
        } else {
            await alertApp("Erro: " + res.message);
            btn.disabled = false;
            btn.innerHTML = original;
        }
    } catch (e) {
        console.error(e);
        btn.innerHTML = 'Erro';
        btn.disabled = false;
    }
}

function startManualDownloadAssistant(data, btn, originalText) {
    return new Promise(async (resolve) => {
        const isDirectLink = data.url && data.url.includes('/download/');
        const message = isDirectLink
            ? `Este mod exige download manual.\n\nNEXCore encontrou a versão mais recente e vai te levar direto para a página de download do arquivo.\n\nDeseja continuar?`
            : `Este mod exige download manual pelo site.\n\nDeseja que o NEXCore abra a página e tente identificar o arquivo quando você baixar?`;

        const wantManual = await confirmApp(message, `Download Manual: ${data.mod_id}`);

        if (!wantManual) {
            btn.disabled = false;
            btn.innerHTML = originalText;
            return resolve(false);
        }

        // Open URL
        window.pywebview.api.open_external_link_py(data.url);

        // Change button to waiting state
        btn.innerHTML = '<i class="fa-solid fa-clock"></i> Aguardando...';
        btn.style.background = '#f59e0b'; // Amber
        btn.disabled = true;

        // Polling logic
        let attempts = 0;

        const introMsg = isDirectLink
            ? "Página de download aberta! O download deve começar em instantes no seu navegador. O NEXCore irá detectar o arquivo automaticamente na sua pasta Downloads."
            : "Página aberta! Clique em 'Download' no site. O NEXCore irá detectar o arquivo automaticamente na sua pasta Downloads.";

        await alertApp(introMsg, "Assistente Iniciado");

        const timer = setInterval(async () => {
            attempts++;
            if (attempts > 30) { // 30 * 2s = 60s
                clearInterval(timer);
                await alertApp("Tempo limite atingido. Não conseguimos detectar o download automaticamente.", "Aviso");
                btn.disabled = false;
                btn.innerHTML = originalText;
                btn.style.background = 'var(--gradient-btn)';
                return resolve(false);
            }

            const path = await window.pywebview.api.scan_downloads_for_mod_py(data.mod_id, data.file_name);
            if (path) {
                clearInterval(timer);
                btn.innerHTML = '<i class="fa-solid fa-file-import"></i> Importando...';
                const res = await window.pywebview.api.ingest_manual_download_py(data.mod_id, path, data.file_name);
                if (res.status === 'success') {
                    if (window.updateModButtonsState) updateModButtonsState(data.mod_id, true);
                    await alertApp("Mod identificado e importado com sucesso!", "Sucesso");
                    resolve(true);
                } else {
                    await alertApp("Erro ao importar: " + res.message);
                    btn.disabled = false;
                    btn.innerHTML = originalText;
                    btn.style.background = 'var(--gradient-btn)';
                    resolve(false);
                }
            }
        }, 2000);
    });
}

/**
 * Progress Modal Management
 */
function showProgressModal(title, status = "Iniciando...") {
    document.getElementById('progress-modal-title').innerText = title;
    document.getElementById('progress-modal-status').innerText = status;
    document.getElementById('progress-modal-overlay').style.display = 'flex';
}

function updateProgress(status) {
    const el = document.getElementById('progress-modal-status');
    if (el) el.innerText = status;
}

function hideProgressModal() {
    document.getElementById('progress-modal-overlay').style.display = 'none';
}

// Make globally accessible for Python callbacks
window.updateProgress = updateProgress;

async function loadModpacks() {
    const list = document.getElementById('modpack-list');
    list.innerHTML = 'Carregando...';
    try {
        const packs = await window.pywebview.api.load_modpacks_py();
        const config = await window.pywebview.api.get_config_py();
        activePackName = config.active_modpack;

        list.innerHTML = '';
        packs.forEach(pack => {
            const isActive = pack.name === activePackName;
            const item = document.createElement('div');
            item.className = 'modpack-item';
            item.style.border = isActive ? '1px solid #10b981' : 'none';

            item.innerHTML = `
                <div>
                    <strong style="font-size: 1.1rem">${pack.name}</strong>
                    ${isActive ? '<span style="color:#10b981; font-size:0.8rem; margin-left:10px">● ATIVO</span>' : ''}
                    <div style="font-size: 0.9rem; color: var(--text-secondary)">${pack.mods.length} mods</div>
                </div>
                <div style="display:flex; gap:10px">
                    <button class="btn-install" style="background:var(--bg-card); border:1px solid #4b5563; padding: 6px 12px;" onclick="openPackDetails('${pack.name}')">
                        <i class="fa-solid fa-pen"></i> Gerenciar
                    </button>
                    <button class="btn-install" style="background:var(--bg-card); border:1px solid #4b5563; padding: 6px 12px;" onclick="exportPackCF('${pack.name}')" title="Exportar para CurseForge">
                        <i class="fa-solid fa-file-export"></i>
                    </button>
                    <button class="btn-install" style="background: ${isActive ? '#2d3748' : 'var(--gradient-btn)'}; padding: 6px 12px; font-size: 0.9rem" 
                            onclick="activatePack('${pack.name}')" ${isActive ? 'disabled' : ''}>
                        ${isActive ? 'Jogando' : 'Ativar'}
                    </button>
                    <button class="btn-install" style="background: #ef4444; padding: 6px 12px;" onclick="deletePack('${pack.name}')">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            `;
            list.appendChild(item);
        });
    } catch (e) {
        list.innerHTML = 'Erro ao carregar packs: ' + e;
    }
}

async function exportPackCF(name) {
    showProgressModal("Exportando Modpack", "Abrindo diálogo de salvamento...");
    try {
        const res = await window.pywebview.api.export_modpack_cf_py(name);
        hideProgressModal();
        if (res.status === 'success') {
            await alertApp(res.message, "Sucesso");
        } else if (res.status !== 'cancelled') {
            alertApp(res.message, "Erro");
        }
    } catch (e) {
        hideProgressModal();
        alertApp("Erro ao exportar: " + e);
    }
}

async function importPackCF() {
    showProgressModal("Importando Modpack", "Aguardando seleção de arquivo...");
    try {
        const res = await window.pywebview.api.import_modpack_cf_py();
        hideProgressModal();

        if (res.status === 'success') {
            // Check for manual downloads needed
            if (res.manual_mods && res.manual_mods.length > 0) {
                await alertApp(`O pacote principal foi criado, mas ${res.manual_mods.length} mods precisam de download manual por restrição do CurseForge. O assistente será aberto agora.`);

                for (const manualMod of res.manual_mods) {
                    // Fix dummy button to avoid TypeError: Cannot set property 'background' of undefined
                    const dummyBtn = {
                        innerHTML: '',
                        disabled: false,
                        style: {}
                    };
                    await startManualDownloadAssistant(manualMod, dummyBtn, "Manual");
                }
            }

            await alertApp("Importação finalizada com sucesso!", "Modpack Criado");
            loadModpacks();
        } else if (res.status !== 'cancelled') {
            alertApp(res.message, "Erro");
        }
    } catch (e) {
        hideProgressModal();
        alertApp("Erro ao importar: " + e);
    }
}
async function openPackDetails(name) {
    switchView('packdetails');
    switchPackTab('mods');
    document.getElementById('pack-details-title').innerText = name;
    document.getElementById('pack-mods-list').innerHTML = 'Carregando...';

    const details = await window.pywebview.api.get_modpack_details_py(name);
    if (details.error) {
        await alertApp(details.error);
        switchView('modpacks');
        return;
    }
    renderPackDetails(details);
}

function switchPackTab(tab) {
    const sections = ['mods', 'saves', 'console', 'logs'];

    sections.forEach(s => {
        const section = document.getElementById(`pack-${s}-section`);
        const tabBtn = document.getElementById(`tab-pack-${s}`);

        if (s === tab) {
            if (section) section.style.display = 'block';
            if (tabBtn) tabBtn.classList.add('action-active');
        } else {
            if (section) section.style.display = 'none';
            if (tabBtn) tabBtn.classList.remove('action-active');
        }
    });

    if (tab === 'saves') {
        loadSaves(window.currentPackName);
    } else if (tab === 'logs') {
        loadPackLogs(window.currentPackName);
    }
}

/**
 * Console Streaming
 */
window.appendConsoleLine = function (line) {
    const terminal = document.getElementById('pack-console-terminal');
    if (!terminal) return;

    const div = document.createElement('div');
    // Basic color coding for errors/warns
    if (line.toLowerCase().includes('error') || line.toLowerCase().includes('severe')) {
        div.style.color = '#ef4444';
    } else if (line.toLowerCase().includes('warn')) {
        div.style.color = '#fbbf24';
    } else if (line.toLowerCase().includes('info')) {
        div.style.color = '#60a5fa';
    }

    div.innerText = line;
    terminal.appendChild(div);

    // Auto-scroll if near bottom
    if (terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 50) {
        terminal.scrollTop = terminal.scrollHeight;
    }

    // Buffer limit: Keep last 1000 lines
    if (terminal.childNodes.length > 1000) {
        terminal.removeChild(terminal.firstChild);
    }
};

async function loadPackLogs(packName) {
    const sidebar = document.getElementById('pack-logs-sidebar');
    const content = document.getElementById('pack-logs-content');
    sidebar.innerHTML = '<div style="padding:10px"><i class="fa-solid fa-spinner fa-spin"></i> Listando logs...</div>';

    try {
        const logs = await window.pywebview.api.get_pack_logs_py(packName);
        sidebar.innerHTML = '';

        if (logs.length === 0) {
            sidebar.innerHTML = '<div style="padding:10px; color:var(--text-secondary)">Nenhum log encontrado.</div>';
            return;
        }

        logs.forEach(log => {
            const item = document.createElement('div');
            item.style.padding = '8px 12px';
            item.style.cursor = 'pointer';
            item.style.borderRadius = '4px';
            item.style.marginBottom = '4px';
            item.style.fontSize = '0.85rem';
            item.style.border = '1px solid transparent';
            item.className = 'log-item';

            // Format name for display (remove save folder prefix if present)
            const displayName = log.file.split('_').slice(-2).join('_');
            item.innerHTML = `
                <div style="font-weight:500">${displayName || log.file}</div>
                <div style="font-size:0.75rem; color:var(--text-secondary)">${log.save}</div>
            `;

            item.onclick = async () => {
                document.querySelectorAll('.log-item').forEach(el => {
                    el.style.background = 'transparent';
                    el.style.borderColor = 'transparent';
                });
                item.style.background = 'rgba(255,255,255,0.05)';
                item.style.borderColor = 'var(--accent-primary)';

                content.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Lendo arquivo...';
                const logData = await window.pywebview.api.read_log_file_py(packName, log.save, log.file);
                content.innerText = logData;
                content.scrollTop = 0;
            };
            sidebar.appendChild(item);
        });
    } catch (e) {
        sidebar.innerHTML = 'Erro ao carregar logs.';
        console.error(e);
    }
}

async function loadSaves(packName) {
    const grid = document.getElementById('pack-saves-list');
    grid.innerHTML = '<div style="padding:20px"><i class="fa-solid fa-spinner fa-spin"></i> Carregando mundos...</div>';

    try {
        const saves = await window.pywebview.api.get_saves_for_pack_py(packName);
        renderSaves(saves);
    } catch (e) {
        console.error("Error loading saves:", e);
        grid.innerHTML = '<div style="padding:20px; color:var(--text-secondary)">Erro ao carregar mundos.</div>';
    }
}

function renderSaves(saves) {
    const grid = document.getElementById('pack-saves-list');
    grid.innerHTML = '';

    if (saves.length === 0) {
        grid.innerHTML = '<div style="padding:20px; color:var(--text-secondary)">Nenhum mundo encontrado para este modpack.</div>';
        return;
    }

    saves.forEach(save => {
        const card = document.createElement('div');
        card.className = 'mod-card';
        const thumb = save.has_preview
            ? `/save-preview/${encodeURIComponent(window.currentPackName)}/${encodeURIComponent(save.folder_name)}/preview.png`
            : 'assets/placeholder.png';

        // Escape the save object for the onclick attribute
        const saveJson = JSON.stringify(save).replace(/'/g, "\\'").replace(/"/g, "&quot;");

        card.innerHTML = `
            <div class="card-image" style="background-image: url('${thumb}')"></div>
            <div class="card-content">
                <div class="card-title-row">
                    <div class="card-title">${save.world.name}</div>
                </div>
                <div class="card-meta">
                    <div>Modo: ${save.world.gamemode}</div>
                    <div>Seed: ${save.world.seed || 'Aleatória'}</div>
                </div>
                <div style="display:flex; gap:10px; margin-top:10px">
                    <button class="btn-install" style="flex:1" onclick="openSaveEditor(${saveJson})">
                        <i class="fa-solid fa-pen-to-square"></i> Editar
                    </button>
                    <button class="btn-install" style="background:#ef4444; width:auto" onclick="deleteSave('${window.currentPackName}', '${save.folder_name}')">
                        <i class="fa-solid fa-trash"></i>
                    </button>
                </div>
            </div>
        `;
        grid.appendChild(card);
    });
}

/**
 * Save Editor Logic
 */
let editingSave = null;

async function openSaveEditor(saveData = null) {
    editingSave = saveData;
    const modal = document.getElementById('save-editor-modal');
    const title = document.getElementById('save-editor-title');

    // Fill basic fields
    document.getElementById('save-name-input').value = saveData ? saveData.world.name : "Novo Mundo";
    document.getElementById('save-seed-input').value = saveData ? saveData.world.seed : "";
    document.getElementById('save-gamemode-select').value = saveData ? saveData.world.gamemode : "Survival";
    document.getElementById('save-pvp-input').checked = saveData ? saveData.world.pvp : false;
    document.getElementById('save-fall-damage-input').checked = saveData ? (saveData.world.fall_damage !== false) : true;

    title.innerText = saveData ? "Editar Mundo" : "Criar Novo Mundo";

    // Load Mods Checklist
    const list = document.getElementById('save-mods-checklist');
    list.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Carregando...';

    try {
        const packDetails = await window.pywebview.api.get_modpack_details_py(window.currentPackName);
        list.innerHTML = '';

        packDetails.mods.forEach(mod => {
            const modKey = mod.internal_id || mod.name;
            const isEnabled = saveData ? (saveData.mods[modKey]?.Enabled !== false) : true;

            const item = document.createElement('div');
            item.style.display = 'flex';
            item.style.alignItems = 'center';
            item.style.gap = '10px';
            item.innerHTML = `
                <input type="checkbox" class="save-mod-toggle" data-mod-id="${modKey}" ${isEnabled ? 'checked' : ''} style="width:16px; height:16px;">
                <span style="font-size:0.9rem">${mod.name}</span>
            `;
            list.appendChild(item);
        });
    } catch (e) {
        list.innerHTML = 'Erro ao carregar mods do pacote.';
    }

    modal.style.display = 'flex';
}

function closeSaveEditor() {
    document.getElementById('save-editor-modal').style.display = 'none';
}

async function confirmSaveConfig() {
    const config = {
        name: document.getElementById('save-name-input').value,
        seed: document.getElementById('save-seed-input').value,
        gamemode: document.getElementById('save-gamemode-select').value,
        pvp: document.getElementById('save-pvp-input').checked,
        fall_damage: document.getElementById('save-fall-damage-input').checked,
        mods: {}
    };

    // Collect mods
    document.querySelectorAll('.save-mod-toggle').forEach(cb => {
        config.mods[cb.dataset.modId] = { Enabled: cb.checked };
    });

    try {
        let res;
        if (editingSave) {
            res = await window.pywebview.api.update_save_py(window.currentPackName, editingSave.folder_name, config);
        } else {
            res = await window.pywebview.api.create_save_py(window.currentPackName, config);
        }

        if (res.status === 'success') {
            closeSaveEditor();
            loadSaves(window.currentPackName);
        } else {
            await alertApp("Erro ao salvar: " + res.message);
        }
    } catch (e) {
        await alertApp("Erro de comunicação: " + e);
    }
}

async function deleteSave(packName, folderName) {
    if (!(await confirmApp("Excluir este mundo permanentemente?"))) return;
    const res = await window.pywebview.api.delete_save_py(packName, folderName);
    if (res.status === 'success') {
        loadSaves(packName);
    } else {
        await alertApp("Erro ao deletar: " + res.message);
    }
}

function renderPackDetails(details) {
    const grid = document.getElementById('pack-mods-list');
    grid.innerHTML = '';

    // Cache the pack name for selection logic
    window.currentPackName = details.name;

    if (details.mods.length === 0) {
        grid.innerHTML = '<div style="padding:20px; color:var(--text-secondary)">Nenhum mod neste pacote.</div>';
        return;
    }

    details.mods.forEach(mod => {
        const thumb = mod.logo?.url || 'assets/placeholder.png';
        const card = document.createElement('div');
        card.className = 'mod-card' + (selectedMods.has(Number(mod.id)) ? ' selected' : '');

        card.onclick = (e) => {
            if (e.target.closest('.btn-install') || e.target.classList.contains('mod-card-checkbox')) return;

            if (selectedMods.size > 0) {
                const cb = card.querySelector('.mod-card-checkbox');
                cb.checked = !cb.checked;
                toggleModSelection(mod.id, cb.checked, 'pack');
                card.classList.toggle('selected', cb.checked);
            } else {
                openModDetails(mod.id);
            }
        };

        card.innerHTML = `
            <div class="card-image" style="background-image: url('${thumb}')">
                <input type="checkbox" class="mod-card-checkbox" 
                       ${selectedMods.has(Number(mod.id)) ? 'checked' : ''}
                       onclick="event.stopPropagation(); toggleModSelection(${mod.id}, this.checked, 'pack'); this.closest('.mod-card').classList.toggle('selected', this.checked)">
            </div>
            <div class="card-content">
                <div class="card-title-row"><div class="card-title">${mod.name}</div></div>
                <div class="card-meta" style="font-size:0.8rem">${mod.summary ? mod.summary.substring(0, 50) + '...' : ''}</div>
                <button class="btn-install" style="background: #ef4444; margin-top:10px" 
                        onclick="removeModFromPack('${details.name}', ${mod.id})">
                    <i class="fa-solid fa-trash"></i> Remover
                </button>
            </div>
        `;
        grid.appendChild(card);
    });
}

async function removeModFromPack(packName, modId) {
    if (!(await confirmApp("Remover este mod do pacote?"))) return;
    await window.pywebview.api.remove_mod_from_pack_py(packName, modId);
    openPackDetails(packName); // Reload
}

async function createNewModpack() {
    const name = await promptApp("Nome do Modpack:");
    if (!name) return;
    await window.pywebview.api.save_modpack_py(name, []);
    loadModpacks();
}

async function deletePack(name) {
    if (!(await confirmApp(`Tem certeza que deseja apagar o modpack "${name}"? Os saves dele também serão apagados.`))) return;
    await window.pywebview.api.delete_modpack_py(name);
    loadModpacks();
}

async function activatePack(name) {
    // Selection is now instant, sync happens at launch
    try {
        const res = await window.pywebview.api.activate_modpack_py(name);
        if (res.status === 'success') {
            await alertApp(`Pacote ${name} selecionado! Os arquivos serão sincronizados ao iniciar o jogo.`, "Modpack Selecionado");
            loadModpacks();
        } else {
            await alertApp("Erro: " + res.message);
        }
    } catch (e) {
        await alertApp("Erro RPC: " + e);
    }
}

async function saveSettings() {
    const key = document.getElementById('api-key-input').value;
    const dir = document.getElementById('game-dir-input').value;
    const saves = document.getElementById('manage-saves-input').checked;

    const geminiKey = document.getElementById('gemini-key-input').value;
    const geminiModel = document.getElementById('gemini-model-select').value;

    await window.pywebview.api.save_config_py({
        api_key: key,
        game_dir: dir,
        manage_saves: saves,
        gemini_api_key: geminiKey,
        gemini_model: geminiModel
    });
    await alertApp("Salvo!");
}

async function loadScreenshots() {
    const grid = document.getElementById('screenshots-grid');
    grid.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Carregando...';

    try {
        const files = await window.pywebview.api.get_screenshots_py();
        grid.innerHTML = '';

        if (files.length === 0) {
            grid.innerHTML = '<div style="padding:20px; color:var(--text-secondary)">Nenhuma imagem encontrada em ~/Imagens</div>';
            return;
        }

        files.forEach(file => {
            const url = `http://127.0.0.1:${window.location.port}/screenshots/${file}`;
            const card = document.createElement('div');
            card.className = 'mod-card';
            card.style.cursor = 'pointer';
            card.onclick = () => window.open(url, '_blank'); // Simple fallback, or use a modal

            // Just displaying the image nicely
            card.innerHTML = `
                <div class="card-image" style="background-image: url('${url}'); height: 200px;"></div>
                <div class="card-content">
                    <div class="card-title-row"><div class="card-title" style="font-size:0.9rem">${file}</div></div>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (e) {
        grid.innerHTML = 'Erro: ' + e;
    }
}

async function loadLibrary() {
    const grid = document.getElementById('installed-grid');
    grid.innerHTML = '<div style="width:100%; text-align:center; padding:40px"><div class="loading-spinner"></div> Carregando biblioteca...</div>';

    try {
        const lib = await window.pywebview.api.get_library_py();
        grid.innerHTML = '';

        const modIds = Object.keys(lib);
        if (modIds.length === 0) {
            grid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:40px; color:var(--text-secondary)">Sua biblioteca está vazia. Instale mods pelo Marketplace!</div>';
            return;
        }

        modIds.forEach(async (id) => {
            let mod = lib[id];

            // Healer: If name is missing or generic, try to fetch it
            if (!mod.name || mod.name === 'Unknown' || mod.name === 'Sem nome') {
                const refreshed = await window.pywebview.api.fetch_mod_metadata_py(id);
                if (refreshed) mod = refreshed;
            }

            const logo = (mod.logo && mod.logo.url) ? mod.logo.url : 'assets/placeholder.png';

            const card = document.createElement('div');
            card.className = 'mod-card' + (selectedMods.has(Number(id)) ? ' selected' : '');

            // Manage on click
            card.onclick = (e) => {
                // Ignore if clicked on delete button or checkbox
                if (e.target.closest('.btn-delete-mod') || e.target.classList.contains('mod-card-checkbox')) return;

                if (selectedMods.size > 0) {
                    const cb = card.querySelector('.mod-card-checkbox');
                    cb.checked = !cb.checked;
                    toggleModSelection(id, cb.checked, 'library');
                    card.classList.toggle('selected', cb.checked);
                } else {
                    openModDetails(id);
                }
            };

            card.innerHTML = `
                <div class="card-image" style="background-image: url('${logo}')">
                    <input type="checkbox" class="mod-card-checkbox" 
                           ${selectedMods.has(Number(id)) ? 'checked' : ''}
                           onclick="event.stopPropagation(); toggleModSelection('${id}', this.checked, 'library'); this.closest('.mod-card').classList.toggle('selected', this.checked)">
                </div>
                <div class="card-content">
                    <div class="card-title-row">
                        <div class="card-title">${mod.name || 'Sem nome'}</div>
                    </div>
                    <div class="card-summary">${mod.summary || ''}</div>
                    <div style="margin-top: auto; display:flex; justify-content: flex-end;">
                        <button class="btn-install btn-delete-mod" style="width:auto; background: #dc2626; padding: 5px 10px; font-size: 0.8rem;" 
                                onclick="deleteModFromLibrary('${id}', '${(mod.name || '').replace(/'/g, "\\'")}')">
                            <i class="fa-solid fa-trash"></i> Remover
                        </button>
                    </div>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (e) {
        grid.innerHTML = 'Erro ao carregar biblioteca: ' + e;
    }
}

async function deleteModFromLibrary(id, name) {
    if (!(await confirmApp(`Tem certeza que deseja remover o mod "${name}"? Ele será removido de TODOS os seus modpacks.`))) return;

    try {
        const res = await window.pywebview.api.delete_mod_from_library_py(id);
        if (res.status === 'success') {
            loadLibrary();
        } else {
            await alertApp("Erro ao remover: " + res.message);
        }
    } catch (e) {
        await alertApp("Erro de comunicação: " + e);
    }
}

async function deleteSelectedFromLibrary() {
    const ids = Array.from(selectedMods);
    if (ids.length === 0) return;

    if (!(await confirmApp(`Remover permanentemente ${ids.length} mods selecionados?`))) return;

    try {
        const res = await window.pywebview.api.delete_mods_from_library_py(ids);
        if (res.status === 'success') {
            await alertApp(`${res.count} mods removidos com sucesso!`);
            clearSelection();
            loadLibrary();
        } else {
            await alertApp("Erro ao remover mods: " + res.message);
        }
    } catch (e) {
        await alertApp("Erro de comunicação: " + e);
    }
}

async function removeSelectedFromPack() {
    const ids = Array.from(selectedMods);
    if (ids.length === 0) return;
    const packName = window.currentPackName;
    if (!packName) return;

    if (!(await confirmApp(`Remover ${ids.length} mods do pacote "${packName}"?`))) return;

    try {
        const res = await window.pywebview.api.remove_mods_from_pack_py(packName, ids);
        if (res.status === 'success') {
            await alertApp(`${res.count} mods removidos do pacote!`);
            clearSelection();
            openPackDetails(packName);
        } else {
            await alertApp("Erro ao remover mods: " + res.message);
        }
    } catch (e) {
        await alertApp("Erro de comunicação: " + e);
    }
}

function switchView(viewName) {
    if (viewName !== currentView) {
        clearSelection();
        currentView = viewName;
    }

    // 1. Switch Content
    ['marketplace', 'modpacks', 'library', 'settings', 'packdetails', 'screenshots', 'moddetails'].forEach(v => {
        const el = document.getElementById(`view-${v}`);
        if (el) el.style.display = 'none';
    });
    const target = document.getElementById(`view-${viewName}`);
    if (target) target.style.display = 'block';

    // 2. Update Menu Active Interface
    document.querySelectorAll('.nav-item').forEach(el => {
        el.classList.remove('active');
        const onclick = el.getAttribute('onclick');
        if (onclick && onclick.includes(`'${viewName}'`)) {
            el.classList.add('active');
        }
    });

    if (viewName === 'modpacks') loadModpacks();
    if (viewName === 'screenshots') loadScreenshots();
    if (viewName === 'library') loadLibrary();
}

// --- AI Discovery ---
function openDiscoveryModal() {
    document.getElementById('discovery-modal').style.display = 'flex';
    document.getElementById('discovery-input').focus();
}

function closeDiscoveryModal() {
    document.getElementById('discovery-modal').style.display = 'none';
}

async function runDiscovery() {
    const pref = document.getElementById('discovery-input').value;
    closeDiscoveryModal();

    const recContainer = document.getElementById('recommended-container');
    const recGrid = document.getElementById('recommended-grid');

    recContainer.style.display = 'block';
    recGrid.innerHTML = '<div style="grid-column: 1/-1; text-align:center; padding:20px"><i class="fa-solid fa-wand-magic-sparkles fa-spin" style="color:#a78bfa"></i> Buscando recomendações personalizadas...</div>';

    // Clear normal grid to focus on discovery? Optional. Let's keep normal grid but maybe user wants to see results.
    // Ideally we might clear currentMods to avoid confusion or keep them.
    // Let's just prepend.

    try {
        const mods = await window.pywebview.api.get_recommendations_py(pref);

        if (mods.error) {
            recGrid.innerHTML = `Erro: ${mods.error}`;
            return;
        }

        if (mods.length === 0) {
            recGrid.innerHTML = '<div style="padding:10px">Nenhuma recomendação encontrada para este termo. Tente outro!</div>';
            return;
        }

        recGrid.innerHTML = '';
        mods.forEach(mod => {
            const thumb = mod.logo?.url || 'assets/placeholder.png';
            const card = document.createElement('div');
            card.className = 'mod-card';
            card.style.border = '1px solid #a78bfa'; // Purple border for recommended
            card.style.boxShadow = '0 0 15px rgba(167, 139, 250, 0.2)';

            // Add to currentMods so detail view works
            if (!currentMods.find(m => m.id === mod.id)) currentMods.push(mod);

            card.innerHTML = `
                <div class="card-image" style="background-image: url('${thumb}'); cursor:pointer" onclick="openModDetails(${mod.id})">
                    <div style="position:absolute; top:10px; right:10px; background:#a78bfa; color:white; padding:4px 8px; border-radius:4px; font-size:0.7rem; font-weight:bold">
                        <i class="fa-solid fa-star"></i> AI PICK
                    </div>
                </div>
                <div class="card-content">
                    <div class="card-title-row">
                         <div class="card-title" style="cursor:pointer" onclick="openModDetails(${mod.id})">${mod.name}</div>
                    </div>
                    <div class="card-meta">Down: ${new Intl.NumberFormat('pt-BR').format(mod.downloadCount)}</div>
                    <button class="btn-install" style="background:linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%)" onclick="installMod(${mod.id}, this)">
                        <i class="fa-solid fa-download"></i> Baixar
                    </button>
                </div>
            `;
            recGrid.appendChild(card);
        });

    } catch (e) {
        recGrid.innerHTML = 'Erro Discovery: ' + e;
    }
}

// --- Link Interceptor ---
document.addEventListener('click', async (e) => {
    const anchor = e.target.closest('a');
    if (!anchor) return;

    const href = anchor.href;

    // Ignore internal links (anchors, javascript calls)
    if (!href || href.startsWith('javascript:') || href.includes('#')) return;

    // Check if it's a "mod link" pattern (e.g. CurseForge)
    // Looking for .../mods/SLUG
    const modMatch = href.match(/\/mods\/([\w-]+)/);

    if (modMatch && modMatch[1]) {
        e.preventDefault();
        const slug = modMatch[1];
        console.log(`Intercepted Mod Link: ${slug}`);

        // Try to resolve slug to ID
        try {
            const modId = await window.pywebview.api.get_mod_by_slug_py(slug);
            if (modId) {
                openModDetails(modId);
                return;
            }
        } catch (err) {
            console.error("Failed to resolve slug:", err);
        }
        // Fallback: If slug resolution fails, open externally
        window.pywebview.api.open_external_link_py(href);
        return;
    }

    // Default External Handling: If it starts with http, open in browser
    if (href.startsWith('http')) {
        e.preventDefault();
        window.pywebview.api.open_external_link_py(href);
    }
});

async function translateDescription(container, btn, sourceHtml = null) {
    if (btn.disabled && !btn.classList.contains('translated')) return;

    // Toggle logic: If already translated, show original
    if (btn.classList.contains('translated')) {
        container.innerHTML = container.dataset.originalHtml;
        btn.innerHTML = '<i class="fa-solid fa-language"></i> Traduzir';
        btn.classList.remove('translated');
        return;
    }

    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Traduzindo...';
    btn.disabled = true;

    try {
        // Save original HTML if not already saved
        if (!container.dataset.originalHtml) {
            container.dataset.originalHtml = sourceHtml || container.innerHTML;
        }

        const currentHtml = container.dataset.originalHtml;
        const targetLang = (window.appConfig && window.appConfig.translation_lang) ? window.appConfig.translation_lang : 'pt';

        const translatedHtml = await window.pywebview.api.translate_description_html_py(currentHtml, targetLang);

        if (translatedHtml && !translatedHtml.startsWith('Erro')) {
            container.innerHTML = translatedHtml;
            btn.innerHTML = '<i class="fa-solid fa-rotate-left"></i> Ver Original';
            btn.classList.add('translated');
            btn.disabled = false; // Re-enable for toggle
        } else {
            console.error("Translation returned error or empty");
            if (translatedHtml && translatedHtml.startsWith('Erro')) {
                await alertApp(translatedHtml);
            }
            btn.innerHTML = 'Erro';
            // Restore original if valid
            if (container.dataset.originalHtml) container.innerHTML = container.dataset.originalHtml;

            setTimeout(() => {
                btn.innerHTML = originalText;
                btn.disabled = false;
            }, 2000);
        }
    } catch (e) {
        console.error("Translation failed:", e);
        btn.innerHTML = 'Erro';
        btn.disabled = false;
        if (container.dataset.originalHtml) container.innerHTML = container.dataset.originalHtml;
    }
}


async function launchGame() {
    const btn = document.getElementById('btn-play');
    const original = btn.innerHTML;

    try {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-sync fa-spin"></i> Sincronizando...';
        btn.style.background = '#f59e0b'; // Amber during sync

        const result = await window.pywebview.api.launch_game_py();

        if (result && result.status === 'error') {
            await alertApp(result.message);
            if (result.message.includes('configurar')) {
                switchView('settings');
            }
            btn.disabled = false;
            btn.innerHTML = original;
            btn.style.background = '';
        } else if (result && result.status === 'started') {
            // Background thread started.
            // UI updates will come via window.updatePlayButtonState callback.
            // Do not reset button here.
        } else {
            // Legacy/Fallback success (should not happen with new backend)
            btn.innerHTML = '<i class="fa-solid fa-check"></i> Abrindo...';
            btn.style.background = '#10b981';
        }
    } catch (e) {
        console.error("Launcher error:", e);
        await alertApp("Erro ao tentar abrir o jogo.");
        btn.disabled = false;
        btn.innerHTML = original;
        btn.style.background = '';
    }
}

// Global function to be called from Python
window.updatePlayButtonState = function (status) {
    const btn = document.getElementById('btn-play');
    if (!btn) return;

    if (status === 'playing') {
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-gamepad"></i> No Jogo';
        btn.style.background = '#6366f1'; // Indigo for playing
    } else if (status === 'finished') {
        const original = '<i class="fa-solid fa-play"></i> JOGAR';
        btn.disabled = false;
        btn.innerHTML = original;
        btn.style.background = '';
    } else {
        // Generic status update (e.g. "Syncing...", "Copying files...")
        btn.disabled = true;
        btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> ${status}`;
        btn.style.background = '#4b5563'; // Gray for loading
    }
};

async function saveSettings() {
    const config = {
        api_key: document.getElementById('api-key-input').value,
        game_dir: document.getElementById('game-dir-input').value,
        manage_saves: document.getElementById('manage-saves-input').checked,

        gemini_api_key: document.getElementById('gemini-key-input').value,
        gemini_model: document.getElementById('gemini-model-select').value,

        translation_lang: document.getElementById('setting-trans-lang').value,
        auto_translate: document.getElementById('setting-trans-auto').checked
    };

    try {
        await window.pywebview.api.save_config_py(config);
        window.appConfig = config;
        await alertApp("Configurações salvas com sucesso!");
    } catch (e) {
        alert("Erro ao salvar: " + e);
        console.error(e);
    }
}

async function previewWorldMap() {
    if (!editingSave || !window.currentPackName) return;

    const btn = document.querySelector('button[onclick="previewWorldMap()"]');
    const originalText = btn.innerHTML;
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Gerando...';
    btn.disabled = true;

    try {
        const res = await window.pywebview.api.generate_map_py(window.currentPackName, editingSave.folder_name);

        if (res.status === 'success') {
            const container = document.getElementById('map-preview-container');
            const img = document.getElementById('map-preview-img');
            // Add timestamp to bypass cache
            img.src = res.url + '?t=' + new Date().getTime();
            container.style.display = 'block';
        } else {
            await alertApp("Erro ao gerar mapa: " + res.message);
        }
    } catch (e) {
        console.error(e);
        await alertApp("Erro: " + e);
    } finally {
        btn.innerHTML = originalText;
        btn.disabled = false;
    }
}

/**
 * Update System
 */
let updateUrl = null;

async function checkUpdates() {
    try {
        const res = await window.pywebview.api.check_for_updates_py();
        if (res.status === 'update_available') {
            const banner = document.getElementById('update-banner');
            const versionEl = document.getElementById('update-version');
            if (banner && versionEl) {
                versionEl.innerText = 'v' + res.version;
                updateUrl = res.url;
                banner.style.display = 'flex';
            }
        }
    } catch (e) {
        console.error("Erro ao verificar atualizações:", e);
    }
}

function openUpdateLink() {
    if (updateUrl) {
        window.pywebview.api.open_external_link_py(updateUrl);
    }
}

function ignoreUpdate() {
    const banner = document.getElementById('update-banner');
    if (banner) {
        banner.style.display = 'none';
    }
}
