/* ==========================================================================
   Meu-cifra-club Club — Lógica Frontend (Catálogo, Setlist, Transposição, Auto-Scroll, Print)
   ========================================================================== */

(() => {
  "use strict";

  const STORAGE_KEYS = {
    API_URL: "Meu-cifra-club_api_base_url",
    SETLIST: "Meu-cifra-club_setlist_ids",
  };

  const state = {
    apiBaseUrl: (localStorage.getItem(STORAGE_KEYS.API_URL) || "http://localhost:8000").replace(/\/+$/, ""),
    musicas: [],
    pastas: [],
    selectedFolderId: null,
    selectedId: null,
    searchQuery: "",
    setlistIds: JSON.parse(localStorage.getItem(STORAGE_KEYS.SETLIST) || "[]"),
    transposeBySong: {}, // { [id]: semitones }
    soloBySong: {},      // { [id]: boolean }
    autoScroll: {
      active: false,
      speed: 3,
      rafId: null,
      lastTime: 0,
      accumulator: 0,
    },
    draggedSetlistIndex: null,
  };

  // ------------------------------------------------------------------------
  // Referências DOM
  // ------------------------------------------------------------------------
  const el = {
    apiStatusBtn: document.getElementById("btn-api-status"),
    apiStatusDot: document.getElementById("api-status-dot"),
    apiStatusText: document.getElementById("api-status-text"),
    btnPrintRepertorio: document.getElementById("btn-print-repertorio"),
    btnPrintSetlistSidebar: document.getElementById("btn-print-setlist-sidebar"),
    btnOpenAddModal: document.getElementById("btn-open-add-modal"),
    btnEmptyAdd: document.getElementById("btn-empty-add"),

    tabBtns: document.querySelectorAll(".tab-btn"),
    tabCatalogo: document.getElementById("tab-catalogo"),
    tabPastas: document.getElementById("tab-pastas"),
    tabSetlist: document.getElementById("tab-setlist"),
    countCatalogo: document.getElementById("count-catalogo"),
    countPastas: document.getElementById("count-pastas"),
    countSetlist: document.getElementById("count-setlist"),

    btnNovaPasta: document.getElementById("btn-nova-pasta"),
    selectActiveFolder: document.getElementById("select-active-folder"),
    btnDeleteFolder: document.getElementById("btn-delete-folder"),
    btnPrintFolder: document.getElementById("btn-print-folder"),
    folderSongList: document.getElementById("folder-song-list"),

    btnAddToFolder: document.getElementById("btn-add-to-folder"),

    modalPastaNova: document.getElementById("modal-pasta-nova"),
    formNovaPasta: document.getElementById("form-nova-pasta"),
    pastaNome: document.getElementById("pasta-nome"),
    pastaCor: document.getElementById("pasta-cor"),

    modalSongFolders: document.getElementById("modal-song-folders"),
    songFolderMusicTitle: document.getElementById("song-folder-music-title"),
    songFoldersChecklist: document.getElementById("song-folders-checklist"),

    searchInput: document.getElementById("search-input"),
    songList: document.getElementById("song-list"),
    setlistList: document.getElementById("setlist-list"),
    btnClearSetlist: document.getElementById("btn-clear-setlist"),

    viewerEmpty: document.getElementById("viewer-empty"),
    viewerContent: document.getElementById("viewer-content"),
    viewTitulo: document.getElementById("view-titulo"),
    viewCantor: document.getElementById("view-cantor"),
    viewAutorWrap: document.getElementById("view-autor-wrap"),
    viewAutor: document.getElementById("view-autor"),
    btnToggleSetlist: document.getElementById("btn-toggle-setlist"),
    btnEditSong: document.getElementById("btn-edit-song"),
    btnDeleteSong: document.getElementById("btn-delete-song"),
    btnPrintSong: document.getElementById("btn-print-song"),

    btnTransposeDown: document.getElementById("btn-transpose-down"),
    btnTransposeUp: document.getElementById("btn-transpose-up"),
    btnTransposeReset: document.getElementById("btn-transpose-reset"),
    viewTomBadge: document.getElementById("view-tom-badge"),

    btnSoloOff: document.getElementById("btn-solo-off"),
    btnSoloOn: document.getElementById("btn-solo-on"),

    btnAutoScrollToggle: document.getElementById("btn-autoscroll-toggle"),
    scrollSpeed: document.getElementById("scroll-speed"),
    scrollSpeedVal: document.getElementById("scroll-speed-val"),
    cifraScrollContainer: document.getElementById("cifra-scroll-container"),
    cifraDisplay: document.getElementById("cifra-display"),

    // Modais
    modalAdd: document.getElementById("modal-add"),
    formAddMusic: document.getElementById("form-add-music"),
    addTitulo: document.getElementById("add-titulo"),
    addCantor: document.getElementById("add-cantor"),
    addAutor: document.getElementById("add-autor"),
    addTom: document.getElementById("add-tom"),
    addCifraManual: document.getElementById("add-cifra-manual"),
    addLoading: document.getElementById("add-loading"),
    addError: document.getElementById("add-error"),
    btnSubmitAdd: document.getElementById("btn-submit-add"),

    modalEdit: document.getElementById("modal-edit"),
    formEditMusic: document.getElementById("form-edit-music"),
    editTitulo: document.getElementById("edit-titulo"),
    editCantor: document.getElementById("edit-cantor"),
    editAutor: document.getElementById("edit-autor"),
    editTom: document.getElementById("edit-tom"),
    editCifraCompleta: document.getElementById("edit-cifra-completa"),
    editCifraSemSolo: document.getElementById("edit-cifra-sem-solo"),
    editError: document.getElementById("edit-error"),
    btnSubmitEdit: document.getElementById("btn-submit-edit"),

    modalApi: document.getElementById("modal-api"),
    formApiUrl: document.getElementById("form-api-url"),
    apiUrlInput: document.getElementById("api-url-input"),

    toastContainer: document.getElementById("toast-container"),
    printArea: document.getElementById("print-area"),
  };

  // ------------------------------------------------------------------------
  // Motor Musical: Transposição & Destaque de Acordes
  // ------------------------------------------------------------------------
  const SHARP_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
  const FLAT_NOTES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"];
  const FLAT_KEYS = new Set(["F", "Bb", "Eb", "Ab", "Db", "Gb", "Dm", "Gm", "Cm", "Fm", "Bbm", "Ebm"]);

  const NOTE_TO_INDEX = {
    C: 0, "B#": 0,
    "C#": 1, Db: 1,
    D: 2,
    "D#": 3, Eb: 3,
    E: 4, Fb: 4,
    F: 5, "E#": 5,
    "F#": 6, Gb: 6,
    G: 7,
    "G#": 8, Ab: 8,
    A: 9,
    "A#": 10, Bb: 10,
    B: 11, Cb: 11,
  };

  const CHORD_TOKEN_RE = /^([A-G](?:#|b)?)((?:m|maj|min|dim|aug|sus|add|M|º|°|\+|[0-9]|(?:\([^)]+\)))*)(?:\/([A-G](?:#|b)?))?$/;
  const FILLERS = new Set(["|", "/", "-", "–", "x", "X", "(", ")", "[", "]", "~", "•", "*"]);

  function mod12(n) {
    return ((n % 12) + 12) % 12;
  }

  function isChordToken(token) {
    const cleaned = token.replace(/^[(\[]+|[)\],;:]+$/g, "");
    if (!cleaned) return false;
    return CHORD_TOKEN_RE.test(cleaned);
  }

  function isChordLine(line) {
    const trimmed = line.trim();
    if (!trimmed) return false;
    if (trimmed.includes("|") && trimmed.includes("---")) return false;

    let cleaned = trimmed.replace(/^\[[^\]]+\]\s*/, "");
    cleaned = cleaned.replace(/^(?:Intro|Refrão|Estrofe|Solo|Ponte|Final|Pré-refrão)\s*:\s*/i, "");
    if (!cleaned) return false;

    const tokens = cleaned.split(/\s+/);
    let chordCount = 0;
    let nonChordCount = 0;
    for (const tok of tokens) {
      if (FILLERS.has(tok) || /^\d+x$/i.test(tok)) continue;
      if (isChordToken(tok)) chordCount += 1;
      else nonChordCount += 1;
    }
    if (chordCount === 0) return false;
    return nonChordCount === 0 || chordCount / (chordCount + nonChordCount) >= 0.7;
  }

  function transposeNote(note, semitones, useFlats = false) {
    const idx = NOTE_TO_INDEX[note];
    if (idx === undefined) return note;
    const scale = useFlats ? FLAT_NOTES : SHARP_NOTES;
    return scale[mod12(idx + semitones)];
  }

  function transposeKeyName(baseKey, semitones) {
    if (!baseKey) return "C";
    const m = baseKey.trim().match(/^([A-Ga-g])([#b]?)(m?)$/);
    if (!m) return baseKey;
    const root = m[1].toUpperCase() + m[2];
    const minor = m[3].toLowerCase() === "m" ? "m" : "";
    const idx = NOTE_TO_INDEX[root];
    if (idx === undefined) return baseKey;
    const nextIdx = mod12(idx + semitones);
    // Usa bemóis se a tonalidade resultante for típica de bemóis
    const sharpCandidate = `${SHARP_NOTES[nextIdx]}${minor}`;
    const flatCandidate = `${FLAT_NOTES[nextIdx]}${minor}`;
    return FLAT_KEYS.has(flatCandidate) ? flatCandidate : sharpCandidate;
  }

  function transposeChord(chord, semitones, useFlats = false) {
    const m = chord.match(CHORD_TOKEN_RE);
    if (!m) return chord;
    const newRoot = transposeNote(m[1], semitones, useFlats);
    const quality = m[2] || "";
    const bass = m[3];
    if (bass) {
      const newBass = transposeNote(bass, semitones, useFlats);
      return `${newRoot}${quality}/${newBass}`;
    }
    return `${newRoot}${quality}`;
  }

  function transposeChordLine(line, semitones, useFlats = false) {
    if (mod12(semitones) === 0) return line;
    const regex = /\S+/g;
    let match;
    let pos = 0;
    let pendingDelta = 0;
    let out = "";

    while ((match = regex.exec(line)) !== null) {
      const start = match.index;
      const end = start + match[0].length;
      const spaceLen = start - pos;

      if (spaceLen > 0 && pendingDelta !== 0) {
        const adjusted = Math.max(1, spaceLen - pendingDelta);
        pendingDelta -= spaceLen - adjusted;
        out += " ".repeat(adjusted);
      } else {
        out += line.slice(pos, start);
      }

      const token = match[0];
      const parts = token.match(/^([(\[]*)(.+?)([)\],;:]*)$/);
      const prefix = parts ? parts[1] : "";
      const core = parts ? parts[2] : token;
      const suffix = parts ? parts[3] : "";

      if (isChordToken(core)) {
        const newCore = transposeChord(core, semitones, useFlats);
        const newToken = `${prefix}${newCore}${suffix}`;
        pendingDelta += newToken.length - token.length;
        out += newToken;
      } else {
        out += token;
      }
      pos = end;
    }

    out += line.slice(pos);
    return out;
  }

  function transposeCifraText(texto, semitones, targetKey) {
    if (!texto || mod12(semitones) === 0) return texto || "";
    const useFlats = FLAT_KEYS.has(targetKey);
    return texto
      .split("\n")
      .map((line) => (isChordLine(line) ? transposeChordLine(line, semitones, useFlats) : line))
      .join("\n");
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function highlightLineHtml(line, chordClass = "chord", sectionClass = "section-tag") {
    if (/^\s*\[[^\]]+\]\s*$/.test(line)) {
      return `<span class="${sectionClass}">${escapeHtml(line)}</span>`;
    }

    if (isChordLine(line)) {
      return line.replace(/\S+/g, (token) => {
        const parts = token.match(/^([(\[]*)(.+?)([)\],;:]*)$/);
        const prefix = parts ? parts[1] : "";
        const core = parts ? parts[2] : token;
        const suffix = parts ? parts[3] : "";
        if (isChordToken(core)) {
          return `${escapeHtml(prefix)}<span class="${chordClass}">${escapeHtml(core)}</span>${escapeHtml(suffix)}`;
        }
        return escapeHtml(token);
      });
    }

    if (/^\s*(?:[EADGBeadgb][#b]?|[1-6])?\s*[:|]\s*[-~0-9hHpPbBrRsS/\\xX()^.*|\s]{3,}/.test(line) && line.includes("-")) {
      return `<span class="tab-line">${escapeHtml(line)}</span>`;
    }

    return escapeHtml(line);
  }

  function renderCifraHtml(texto, chordClass = "chord", sectionClass = "section-tag") {
    return texto
      .split("\n")
      .map((line) => highlightLineHtml(line, chordClass, sectionClass))
      .join("\n");
  }

  // ------------------------------------------------------------------------
  // Helpers de Estado da Música
  // ------------------------------------------------------------------------
  function getSongById(id) {
    return state.musicas.find((m) => m.id === id) || null;
  }

  function getEffectiveSolo(song) {
    if (state.soloBySong[song.id] !== undefined) {
      return state.soloBySong[song.id];
    }
    return Boolean(song.exibir_solo);
  }

  function getTransposeOffset(song) {
    return state.transposeBySong[song.id] || 0;
  }

  function getEffectiveKey(song) {
    return transposeKeyName(song.tom, getTransposeOffset(song));
  }

  function getEffectiveCifra(song) {
    const showSolo = getEffectiveSolo(song);
    const baseText = showSolo ? song.cifra_completa : song.cifra_sem_solo;
    const semitones = getTransposeOffset(song);
    const targetKey = getEffectiveKey(song);
    return transposeCifraText(baseText, semitones, targetKey);
  }

  function saveSetlist() {
    localStorage.setItem(STORAGE_KEYS.SETLIST, JSON.stringify(state.setlistIds));
  }

  function showToast(message, type = "success") {
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;
    toast.textContent = message;
    el.toastContainer.appendChild(toast);
    setTimeout(() => {
      toast.remove();
    }, 3400);
  }

  // ------------------------------------------------------------------------
  // Comunicação com a API FastAPI
  // ------------------------------------------------------------------------
  async function apiFetch(path, options = {}) {
    const res = await fetch(`${state.apiBaseUrl}${path}`, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Erro HTTP ${res.status}`);
    }
    return data;
  }

  async function checkHealth() {
    el.apiStatusDot.className = "status-dot";
    el.apiStatusText.textContent = "Conectando...";
    try {
      const data = await apiFetch("/api/health");
      if (data.status === "ok") {
        el.apiStatusDot.className = "status-dot online";
        el.apiStatusText.textContent = "Neon.db Online";
      } else {
        el.apiStatusDot.className = "status-dot offline";
        el.apiStatusText.textContent = "Banco não configurado";
      }
    } catch {
      el.apiStatusDot.className = "status-dot offline";
      el.apiStatusText.textContent = "API Offline";
    }
  }

  async function loadPastas() {
    try {
      const list = await apiFetch("/api/pastas");
      state.pastas = list;
      if (state.pastas.length > 0 && !state.selectedFolderId) {
        state.selectedFolderId = state.pastas[0].id;
      } else if (!state.pastas.some((p) => p.id === state.selectedFolderId)) {
        state.selectedFolderId = state.pastas.length > 0 ? state.pastas[0].id : null;
      }
      renderPastas();
    } catch {
      // Falha silenciosa ou log
    }
  }

  async function loadMusicas(preserveSelection = true) {
    try {
      const list = await apiFetch("/api/musicas");
      state.musicas = list;
      // Limpa IDs no setlist que não existem mais no banco
      const validIds = new Set(list.map((m) => m.id));
      state.setlistIds = state.setlistIds.filter((id) => validIds.has(id));
      saveSetlist();

      if (!preserveSelection || !getSongById(state.selectedId)) {
        state.selectedId = list.length > 0 ? list[0].id : null;
      }
      await loadPastas();
      renderAll();
    } catch (err) {
      showToast(`Erro ao carregar músicas: ${err.message}`, "error");
      renderAll();
    }
  }

  // ------------------------------------------------------------------------
  // Renderização da Interface
  // ------------------------------------------------------------------------
  function renderCatalogo() {
    const q = state.searchQuery.trim().toLowerCase();
    const filtered = state.musicas.filter((m) => {
      if (!q) return true;
      return (
        m.titulo.toLowerCase().includes(q) ||
        m.cantor.toLowerCase().includes(q) ||
        (m.autor && m.autor.toLowerCase().includes(q))
      );
    });

    el.countCatalogo.textContent = state.musicas.length;
    el.songList.innerHTML = "";

    if (filtered.length === 0) {
      const empty = document.createElement("li");
      empty.className = "list-empty-msg";
      empty.textContent = state.musicas.length === 0
        ? "Nenhuma música salva ainda. Clique em '+ Adicionar Música'."
        : "Nenhuma música encontrada para essa busca.";
      el.songList.appendChild(empty);
      return;
    }

    for (const song of filtered) {
      const li = document.createElement("li");
      li.className = `song-item${song.id === state.selectedId ? " active" : ""}`;
      const inSetlist = state.setlistIds.includes(song.id);
      const currentKey = getEffectiveKey(song);

      li.innerHTML = `
        <div class="song-item-info">
          <div class="song-item-title">${escapeHtml(song.titulo)}</div>
          <div class="song-item-sub">${escapeHtml(song.cantor)}${song.autor ? ` • ${escapeHtml(song.autor)}` : ""}</div>
        </div>
        <div class="song-item-right">
          <span class="key-pill">${escapeHtml(currentKey)}</span>
          <button class="icon-btn ${inSetlist ? "in-setlist" : ""}" data-setlist-toggle="${song.id}" title="${inSetlist ? "Remover do Setlist" : "Adicionar ao Setlist"}">
            ${inSetlist ? "✓" : "+"}
          </button>
        </div>
      `;

      li.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-setlist-toggle]")) {
          toggleSetlist(song.id);
          return;
        }
        selectSong(song.id);
      });

      el.songList.appendChild(li);
    }
  }

  function renderSetlist() {
    const items = state.setlistIds.map(getSongById).filter(Boolean);
    el.countSetlist.textContent = items.length;
    el.setlistList.innerHTML = "";

    if (items.length === 0) {
      const empty = document.createElement("li");
      empty.className = "list-empty-msg";
      empty.textContent = "Seu Setlist do Dia está vazio. Clique no '+' ao lado das músicas no Catálogo.";
      el.setlistList.appendChild(empty);
      return;
    }

    items.forEach((song, index) => {
      const li = document.createElement("li");
      li.className = `song-item${song.id === state.selectedId ? " active" : ""}`;
      li.draggable = true;
      li.dataset.index = String(index);

      li.innerHTML = `
        <div class="song-item-info">
          <div class="song-item-title">${index + 1}. ${escapeHtml(song.titulo)}</div>
          <div class="song-item-sub">${escapeHtml(song.cantor)}</div>
        </div>
        <div class="song-item-right">
          <span class="key-pill">${escapeHtml(getEffectiveKey(song))}</span>
          <button class="icon-btn" data-move-up="${index}" title="Subir" ${index === 0 ? "disabled" : ""}>↑</button>
          <button class="icon-btn" data-move-down="${index}" title="Descer" ${index === items.length - 1 ? "disabled" : ""}>↓</button>
          <button class="icon-btn" data-remove-setlist="${song.id}" title="Remover">&times;</button>
        </div>
      `;

      li.addEventListener("click", (ev) => {
        if (ev.target.closest("[data-move-up]")) {
          moveSetlistItem(index, index - 1);
          return;
        }
        if (ev.target.closest("[data-move-down]")) {
          moveSetlistItem(index, index + 1);
          return;
        }
        if (ev.target.closest("[data-remove-setlist]")) {
          toggleSetlist(song.id);
          return;
        }
        selectSong(song.id);
      });

      // Drag and drop para reordenar
      li.addEventListener("dragstart", () => {
        state.draggedSetlistIndex = index;
        li.classList.add("dragging");
      });
      li.addEventListener("dragend", () => {
        state.draggedSetlistIndex = null;
        li.classList.remove("dragging");
      });
      li.addEventListener("dragover", (ev) => {
        ev.preventDefault();
      });
      li.addEventListener("drop", (ev) => {
        ev.preventDefault();
        if (state.draggedSetlistIndex !== null && state.draggedSetlistIndex !== index) {
          moveSetlistItem(state.draggedSetlistIndex, index);
        }
      });

      el.setlistList.appendChild(li);
    });
  }

  function renderPastas() {
    el.countPastas.textContent = state.pastas.length;
    el.selectActiveFolder.innerHTML = "";

    if (state.pastas.length === 0) {
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Nenhuma pasta criada";
      el.selectActiveFolder.appendChild(opt);
      el.folderSongList.innerHTML = `<li class="list-empty-msg">Nenhuma pasta criada. Clique acima em "+ Criar Nova Pasta".</li>`;
      return;
    }

    state.pastas.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      opt.textContent = `${p.nome} (${(p.musicas_ids || []).length})`;
      if (p.id === state.selectedFolderId) opt.selected = true;
      el.selectActiveFolder.appendChild(opt);
    });

    const activeFolder = state.pastas.find((p) => p.id === state.selectedFolderId) || state.pastas[0];
    if (activeFolder) {
      state.selectedFolderId = activeFolder.id;
      const folderSongs = (activeFolder.musicas_ids || []).map(getSongById).filter(Boolean);
      el.folderSongList.innerHTML = "";

      if (folderSongs.length === 0) {
        el.folderSongList.innerHTML = `<li class="list-empty-msg">Pasta vazia. Abra uma música e clique no botão "📁 Pastas" no topo da cifra para adicioná-la aqui.</li>`;
      } else {
        folderSongs.forEach((song) => {
          const li = document.createElement("li");
          li.className = `song-item${song.id === state.selectedId ? " active" : ""}`;
          li.innerHTML = `
            <div class="song-item-info">
              <div class="song-item-title">${escapeHtml(song.titulo)}</div>
              <div class="song-item-sub">${escapeHtml(song.cantor)}</div>
            </div>
            <div class="song-item-right">
              <span class="key-pill">${escapeHtml(getEffectiveKey(song))}</span>
              <button class="icon-btn" data-remove-folder-song="${song.id}" title="Remover desta pasta">&times;</button>
            </div>
          `;
          li.addEventListener("click", (ev) => {
            if (ev.target.closest("[data-remove-folder-song]")) {
              removerMusicaDaPasta(activeFolder.id, song.id);
              return;
            }
            selectSong(song.id);
          });
          el.folderSongList.appendChild(li);
        });
      }
    }
  }

  function renderViewer() {
    const song = getSongById(state.selectedId);
    if (!song) {
      el.viewerEmpty.classList.remove("hidden");
      el.viewerContent.classList.add("hidden");
      stopAutoScroll();
      return;
    }

    el.viewerEmpty.classList.add("hidden");
    el.viewerContent.classList.remove("hidden");

    el.viewTitulo.textContent = song.titulo;
    el.viewCantor.textContent = song.cantor;

    if (song.autor) {
      el.viewAutor.textContent = song.autor;
      el.viewAutorWrap.classList.remove("hidden");
    } else {
      el.viewAutorWrap.classList.add("hidden");
    }

    const inSetlist = state.setlistIds.includes(song.id);
    el.btnToggleSetlist.textContent = inSetlist ? "✓ No Setlist" : "+ Setlist";

    const offset = getTransposeOffset(song);
    const currentKey = getEffectiveKey(song);
    const signedOffset = offset > 0 ? `+${offset}` : `${offset}`;
    el.viewTomBadge.textContent = offset === 0 ? currentKey : `${currentKey} (${signedOffset})`;
    el.btnTransposeReset.classList.toggle("hidden", offset === 0);

    const showSolo = getEffectiveSolo(song);
    el.btnSoloOn.classList.toggle("active", showSolo);
    el.btnSoloOff.classList.toggle("active", !showSolo);

    const cifraText = getEffectiveCifra(song);
    el.cifraDisplay.innerHTML = renderCifraHtml(cifraText, "chord", "section-tag");
  }

  function renderAll() {
    renderCatalogo();
    renderPastas();
    renderSetlist();
    renderViewer();
  }

  // ------------------------------------------------------------------------
  // Ações do Usuário
  // ------------------------------------------------------------------------
  function selectSong(id) {
    stopAutoScroll();
    state.selectedId = id;
    el.cifraScrollContainer.scrollTop = 0;
    renderAll();
  }

  function toggleSetlist(id) {
    const idx = state.setlistIds.indexOf(id);
    if (idx === -1) {
      state.setlistIds.push(id);
      showToast("Música adicionada ao Setlist do Dia.");
    } else {
      state.setlistIds.splice(idx, 1);
    }
    saveSetlist();
    renderAll();
  }

  function moveSetlistItem(fromIdx, toIdx) {
    if (toIdx < 0 || toIdx >= state.setlistIds.length) return;
    const [moved] = state.setlistIds.splice(fromIdx, 1);
    state.setlistIds.splice(toIdx, 0, moved);
    saveSetlist();
    renderSetlist();
  }

  function transposeSelected(delta) {
    const song = getSongById(state.selectedId);
    if (!song) return;
    const next = (state.transposeBySong[song.id] || 0) + delta;
    state.transposeBySong[song.id] = next;
    renderAll();
  }

  async function setSoloMode(showSolo) {
    const song = getSongById(state.selectedId);
    if (!song) return;
    state.soloBySong[song.id] = showSolo;
    renderViewer();

    // Persiste preferência no Neon.db em segundo plano
    try {
      const updated = await apiFetch(`/api/musicas/${song.id}`, {
        method: "PUT",
        body: JSON.stringify({ exibir_solo: showSolo }),
      });
      song.exibir_solo = updated.exibir_solo;
    } catch {
      // Mantém estado local mesmo se a rede oscilar
    }
  }

  // ------------------------------------------------------------------------
  // Operações de Pastas
  // ------------------------------------------------------------------------
  async function criarPasta(nome, cor) {
    try {
      const nova = await apiFetch("/api/pastas", {
        method: "POST",
        body: JSON.stringify({ nome, cor }),
      });
      state.pastas.push(nova);
      state.selectedFolderId = nova.id;
      showToast(`Pasta "${nova.nome}" criada com sucesso!`);
      renderPastas();
    } catch (err) {
      showToast(`Erro ao criar pasta: ${err.message}`, "error");
    }
  }

  async function excluirPasta(pastaId) {
    const pasta = state.pastas.find((p) => p.id === pastaId);
    if (!pasta) return;
    if (!window.confirm(`Deseja excluir a pasta "${pasta.nome}"? (As músicas não serão apagadas).`)) return;

    try {
      await apiFetch(`/api/pastas/${pastaId}`, { method: "DELETE" });
      state.pastas = state.pastas.filter((p) => p.id !== pastaId);
      state.selectedFolderId = state.pastas.length > 0 ? state.pastas[0].id : null;
      showToast(`Pasta "${pasta.nome}" excluída.`);
      renderPastas();
    } catch (err) {
      showToast(`Erro ao excluir pasta: ${err.message}`, "error");
    }
  }

  async function adicionarMusicaNaPasta(pastaId, musicaId) {
    try {
      await apiFetch(`/api/pastas/${pastaId}/musicas`, {
        method: "POST",
        body: JSON.stringify({ musica_id: musicaId }),
      });
      const pasta = state.pastas.find((p) => p.id === pastaId);
      if (pasta && !(pasta.musicas_ids || []).includes(musicaId)) {
        pasta.musicas_ids = pasta.musicas_ids || [];
        pasta.musicas_ids.push(musicaId);
      }
      renderPastas();
    } catch (err) {
      showToast(`Erro ao vincular música: ${err.message}`, "error");
    }
  }

  async function removerMusicaDaPasta(pastaId, musicaId) {
    try {
      await apiFetch(`/api/pastas/${pastaId}/musicas/${musicaId}`, { method: "DELETE" });
      const pasta = state.pastas.find((p) => p.id === pastaId);
      if (pasta && pasta.musicas_ids) {
        pasta.musicas_ids = pasta.musicas_ids.filter((id) => id !== musicaId);
      }
      renderPastas();
      showToast("Música removida da pasta.");
    } catch (err) {
      showToast(`Erro ao remover da pasta: ${err.message}`, "error");
    }
  }

  function openSongFoldersModal(song) {
    el.songFolderMusicTitle.textContent = `"${song.titulo}"`;
    el.songFoldersChecklist.innerHTML = "";

    if (state.pastas.length === 0) {
      el.songFoldersChecklist.innerHTML = `<p style="color: var(--text-muted); font-size: 0.85rem;">Nenhuma pasta criada ainda. Vá na aba "Pastas" para criar uma.</p>`;
      openModal(el.modalSongFolders);
      return;
    }

    state.pastas.forEach((pasta) => {
      const isChecked = (pasta.musicas_ids || []).includes(song.id);
      const label = document.createElement("label");
      label.className = "radio-card";
      label.style.cursor = "pointer";
      label.innerHTML = `
        <input type="checkbox" ${isChecked ? "checked" : ""} data-folder-id="${pasta.id}" />
        <span style="font-weight: 600;">📁 ${escapeHtml(pasta.nome)}</span>
      `;

      const checkbox = label.querySelector("input");
      checkbox.addEventListener("change", async () => {
        if (checkbox.checked) {
          await adicionarMusicaNaPasta(pasta.id, song.id);
        } else {
          await removerMusicaDaPasta(pasta.id, song.id);
        }
      });

      el.songFoldersChecklist.appendChild(label);
    });

    openModal(el.modalSongFolders);
  }

  // ------------------------------------------------------------------------
  // Rolagem Automática (Auto-Scroll) com requestAnimationFrame
  // ------------------------------------------------------------------------
  function getScrollStepPixelsPerSec(level) {
    // Nível 1 (~10 px/s) até Nível 10 (~135 px/s)
    return 8 + level * level * 1.25;
  }

  function autoScrollTick(timestamp) {
    if (!state.autoScroll.active) return;

    if (!state.autoScroll.lastTime) {
      state.autoScroll.lastTime = timestamp;
    }
    const dt = (timestamp - state.autoScroll.lastTime) / 1000;
    state.autoScroll.lastTime = timestamp;

    const container = el.cifraScrollContainer;
    const canScrollContainer = container.scrollHeight > container.clientHeight + 2;
    const speedPx = getScrollStepPixelsPerSec(state.autoScroll.speed);
    state.autoScroll.accumulator += speedPx * dt;

    if (state.autoScroll.accumulator >= 1) {
      const px = Math.floor(state.autoScroll.accumulator);
      state.autoScroll.accumulator -= px;

      if (canScrollContainer) {
        container.scrollTop += px;
        if (container.scrollTop + container.clientHeight >= container.scrollHeight - 2) {
          stopAutoScroll();
          return;
        }
      } else {
        window.scrollBy(0, px);
        if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 2) {
          stopAutoScroll();
          return;
        }
      }
    }

    state.autoScroll.rafId = requestAnimationFrame(autoScrollTick);
  }

  function startAutoScroll() {
    if (state.autoScroll.active) return;
    state.autoScroll.active = true;
    state.autoScroll.lastTime = 0;
    state.autoScroll.accumulator = 0;
    el.btnAutoScrollToggle.textContent = "⏸ Pausar Rolagem";
    el.btnAutoScrollToggle.classList.add("active-scroll");
    state.autoScroll.rafId = requestAnimationFrame(autoScrollTick);
  }

  function stopAutoScroll() {
    state.autoScroll.active = false;
    if (state.autoScroll.rafId) {
      cancelAnimationFrame(state.autoScroll.rafId);
      state.autoScroll.rafId = null;
    }
    el.btnAutoScrollToggle.textContent = "▶ Iniciar Rolagem";
    el.btnAutoScrollToggle.classList.remove("active-scroll");
  }

  // ------------------------------------------------------------------------
  // Impressão & Exportação PDF (@media print)
  // ------------------------------------------------------------------------
  function buildPrintableSongHtml(song, addPageBreakAfter = false) {
    const effectiveKey = getEffectiveKey(song);
    const showSolo = getEffectiveSolo(song);
    const cifraText = getEffectiveCifra(song);
    const lineCount = cifraText.split("\n").length;
    const isShortSong = lineCount <= 34;

    const stanzas = cifraText.split(/\n\s*\n/);
    const stanzasHtml = stanzas
      .map((stanza) => {
        const rendered = renderCifraHtml(stanza, "print-chord", "print-section-tag");
        return `<pre class="print-stanza">${rendered}</pre>`;
      })
      .join("");

    const classes = ["print-song-block"];
    if (isShortSong) classes.push("print-song-short");
    if (addPageBreakAfter) classes.push("print-song-page-break");

    const soloLabel = showSolo ? "Com Solo/Tab" : "Sem Solo";
    const autorPart = song.autor ? ` • Composição: ${escapeHtml(song.autor)}` : "";

    return `
      <article class="${classes.join(" ")}">
        <header class="print-song-header">
          <h2 class="print-song-title">${escapeHtml(song.titulo)}</h2>
          <p class="print-song-meta">
            ${escapeHtml(song.cantor)}${autorPart} • <strong>Tom: ${escapeHtml(effectiveKey)}</strong> (${soloLabel})
          </p>
        </header>
        ${stanzasHtml}
      </article>
    `;
  }

  function printSingleSong() {
    const song = getSongById(state.selectedId);
    if (!song) return;
    stopAutoScroll();
    el.printArea.innerHTML = buildPrintableSongHtml(song, false);
    window.print();
  }

  function printSetlistOrRepertoire() {
    stopAutoScroll();
    const setlistSongs = state.setlistIds.map(getSongById).filter(Boolean);
    const songsToPrint = setlistSongs.length > 0 ? setlistSongs : state.musicas;

    if (songsToPrint.length === 0) {
      showToast("Nenhuma música disponível para gerar PDF.", "error");
      return;
    }

    const docTitle = setlistSongs.length > 0
      ? `Setlist do Dia (${songsToPrint.length} músicas)`
      : `Repertório Completo (${songsToPrint.length} músicas)`;

    const blocks = songsToPrint
      .map((song, idx) => buildPrintableSongHtml(song, idx < songsToPrint.length - 1))
      .join("");

    el.printArea.innerHTML = `
      <h1 class="print-doc-title">Meu-cifra-club Club — ${escapeHtml(docTitle)}</h1>
      ${blocks}
    `;
    window.print();
  }

  function printFolder(pastaId) {
    stopAutoScroll();
    const pasta = state.pastas.find((p) => p.id === pastaId);
    if (!pasta) return;
    const songsToPrint = (pasta.musicas_ids || []).map(getSongById).filter(Boolean);

    if (songsToPrint.length === 0) {
      showToast("Esta pasta não contém músicas para gerar PDF.", "error");
      return;
    }

    const docTitle = `Pasta: ${pasta.nome} (${songsToPrint.length} músicas)`;
    const blocks = songsToPrint
      .map((song, idx) => buildPrintableSongHtml(song, idx < songsToPrint.length - 1))
      .join("");

    el.printArea.innerHTML = `
      <h1 class="print-doc-title">Meu-cifra-club Club — ${escapeHtml(docTitle)}</h1>
      ${blocks}
    `;
    window.print();
  }

  // ------------------------------------------------------------------------
  // Modais
  // ------------------------------------------------------------------------
  function openModal(modalEl) {
    modalEl.classList.remove("hidden");
  }

  function closeModal(modalEl) {
    modalEl.classList.add("hidden");
  }

  // ------------------------------------------------------------------------
  // Event Listeners
  // ------------------------------------------------------------------------
  el.tabBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.tab;
      el.tabBtns.forEach((b) => {
        b.classList.toggle("active", b === btn);
        b.setAttribute("aria-selected", String(b === btn));
      });
      el.tabCatalogo.classList.toggle("active", target === "catalogo");
      el.tabPastas.classList.toggle("active", target === "pastas");
      el.tabSetlist.classList.toggle("active", target === "setlist");
    });
  });

  // Operações de Pastas
  el.btnNovaPasta.addEventListener("click", () => {
    el.formNovaPasta.reset();
    openModal(el.modalPastaNova);
    el.pastaNome.focus();
  });

  el.formNovaPasta.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const nome = el.pastaNome.value.trim();
    const cor = el.pastaCor.value;
    if (!nome) return;
    await criarPasta(nome, cor);
    closeModal(el.modalPastaNova);
  });

  el.selectActiveFolder.addEventListener("change", (ev) => {
    state.selectedFolderId = Number(ev.target.value);
    renderPastas();
  });

  el.btnDeleteFolder.addEventListener("click", () => {
    if (state.selectedFolderId) {
      excluirPasta(state.selectedFolderId);
    }
  });

  el.btnPrintFolder.addEventListener("click", () => {
    if (state.selectedFolderId) {
      printFolder(state.selectedFolderId);
    }
  });

  el.btnAddToFolder.addEventListener("click", () => {
    const song = getSongById(state.selectedId);
    if (!song) return;
    openSongFoldersModal(song);
  });

  el.searchInput.addEventListener("input", (ev) => {
    state.searchQuery = ev.target.value;
    renderCatalogo();
  });

  el.btnClearSetlist.addEventListener("click", () => {
    if (state.setlistIds.length === 0) return;
    state.setlistIds = [];
    saveSetlist();
    renderAll();
  });

  el.btnToggleSetlist.addEventListener("click", () => {
    if (state.selectedId) toggleSetlist(state.selectedId);
  });

  el.btnTransposeDown.addEventListener("click", () => transposeSelected(-1));
  el.btnTransposeUp.addEventListener("click", () => transposeSelected(1));
  el.btnTransposeReset.addEventListener("click", () => {
    const song = getSongById(state.selectedId);
    if (!song) return;
    state.transposeBySong[song.id] = 0;
    renderAll();
  });

  el.btnSoloOff.addEventListener("click", () => setSoloMode(false));
  el.btnSoloOn.addEventListener("click", () => setSoloMode(true));

  el.btnAutoScrollToggle.addEventListener("click", () => {
    if (state.autoScroll.active) stopAutoScroll();
    else startAutoScroll();
  });

  el.scrollSpeed.addEventListener("input", (ev) => {
    const val = Number(ev.target.value);
    state.autoScroll.speed = val;
    el.scrollSpeedVal.textContent = String(val);
  });

  el.btnPrintSong.addEventListener("click", printSingleSong);
  el.btnPrintRepertorio.addEventListener("click", printSetlistOrRepertoire);
  el.btnPrintSetlistSidebar.addEventListener("click", printSetlistOrRepertoire);

  // Abrir Modal + Adicionar Música
  const openAddHandler = () => {
    el.formAddMusic.reset();
    el.addError.classList.add("hidden");
    el.addLoading.classList.add("hidden");
    el.btnSubmitAdd.disabled = false;
    openModal(el.modalAdd);
    el.addTitulo.focus();
  };
  el.btnOpenAddModal.addEventListener("click", openAddHandler);
  el.btnEmptyAdd.addEventListener("click", openAddHandler);

  // Enviar + Adicionar Música
  el.formAddMusic.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const comSoloRadio = el.formAddMusic.querySelector('input[name="add-solo-mode"]:checked');
    const payload = {
      titulo: el.addTitulo.value.trim(),
      cantor: el.addCantor.value.trim(),
      autor: el.addAutor.value.trim() || null,
      tom: el.addTom.value.trim() || null,
      com_solo: comSoloRadio ? comSoloRadio.value === "true" : false,
      cifra_manual: el.addCifraManual.value.trim() || null,
    };

    el.addError.classList.add("hidden");
    el.addLoading.classList.remove("hidden");
    el.btnSubmitAdd.disabled = true;

    try {
      const saved = await apiFetch("/api/adicionar-musica", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      closeModal(el.modalAdd);
      showToast(`"${saved.titulo}" adicionada ao repertório!`);
      await loadMusicas(false);
      selectSong(saved.id);
    } catch (err) {
      el.addError.textContent = err.message;
      el.addError.classList.remove("hidden");
    } finally {
      el.addLoading.classList.add("hidden");
      el.btnSubmitAdd.disabled = false;
    }
  });

  // Abrir Modal Editar
  el.btnEditSong.addEventListener("click", () => {
    const song = getSongById(state.selectedId);
    if (!song) return;
    el.editTitulo.value = song.titulo;
    el.editCantor.value = song.cantor;
    el.editAutor.value = song.autor || "";
    el.editTom.value = song.tom;
    el.editCifraCompleta.value = song.cifra_completa;
    el.editCifraSemSolo.value = song.cifra_sem_solo;
    el.editError.classList.add("hidden");
    openModal(el.modalEdit);
  });

  el.formEditMusic.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const song = getSongById(state.selectedId);
    if (!song) return;

    el.editError.classList.add("hidden");
    el.btnSubmitEdit.disabled = true;

    try {
      const updated = await apiFetch(`/api/musicas/${song.id}`, {
        method: "PUT",
        body: JSON.stringify({
          titulo: el.editTitulo.value.trim(),
          cantor: el.editCantor.value.trim(),
          autor: el.editAutor.value.trim() || null,
          tom: el.editTom.value.trim(),
          cifra_completa: el.editCifraCompleta.value,
          cifra_sem_solo: el.editCifraSemSolo.value,
        }),
      });
      const idx = state.musicas.findIndex((m) => m.id === song.id);
      if (idx !== -1) state.musicas[idx] = updated;
      state.transposeBySong[song.id] = 0;
      closeModal(el.modalEdit);
      showToast("Música atualizada com sucesso.");
      renderAll();
    } catch (err) {
      el.editError.textContent = err.message;
      el.editError.classList.remove("hidden");
    } finally {
      el.btnSubmitEdit.disabled = false;
    }
  });

  // Excluir Música
  el.btnDeleteSong.addEventListener("click", async () => {
    const song = getSongById(state.selectedId);
    if (!song) return;
    if (!window.confirm(`Tem certeza que deseja excluir "${song.titulo}" de ${song.cantor}?`)) {
      return;
    }

    try {
      await apiFetch(`/api/musicas/${song.id}`, { method: "DELETE" });
      showToast(`"${song.titulo}" excluída.`);
      await loadMusicas(false);
    } catch (err) {
      showToast(`Erro ao excluir: ${err.message}`, "error");
    }
  });

  // Configurar URL da API
  el.apiStatusBtn.addEventListener("click", () => {
    el.apiUrlInput.value = state.apiBaseUrl;
    openModal(el.modalApi);
  });

  el.formApiUrl.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    state.apiBaseUrl = el.apiUrlInput.value.trim().replace(/\/+$/, "");
    localStorage.setItem(STORAGE_KEYS.API_URL, state.apiBaseUrl);
    closeModal(el.modalApi);
    await checkHealth();
    await loadMusicas(false);
  });

  // Fechar modais no botão X, Cancelar ou clicando fora
  document.querySelectorAll("[data-close-modal]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const target = document.getElementById(btn.dataset.closeModal);
      if (target) closeModal(target);
    });
  });

  document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
    backdrop.addEventListener("click", (ev) => {
      if (ev.target === backdrop) closeModal(backdrop);
    });
  });

  // Inicialização
  checkHealth();
  loadMusicas(false);
})();
