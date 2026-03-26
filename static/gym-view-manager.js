(() => {
  const root = document.getElementById("gymViewRoot");
  if (!root) return;

  const state = {
    userCheckinInfo: null,
    currentCheckin: null,
    atletas: [],
    modal: {
      open: false,
      type: null,
      loading: false,
      requestId: null,
    },
    volei: {
      parceiroId: "",
      adversario1Id: "",
      adversario2Id: "",
      scoreA: "",
      scoreB: "",
      resumo: null,
    },
    natacao: {
      metros: "",
      tempo: "",
      resumo: null,
    },
    funcional: {
      nomeTreino: "",
      repsTempo: "",
      resumo: null,
    },
  };

  const apiService = {
    async getCurrentCheckin() {
      return fetchJson("/api/gym/checkin-info");
    },
    async buscarAtletas(termo = "") {
      const query = termo ? `?q=${encodeURIComponent(termo)}` : "";
      return fetchJson(`/api/gym/atletas${query}`);
    },
    async processRankingPoints(payload) {
      return fetchJson("/api/gym/process-points", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
    },
    async finalizarPartidaVolei(placar, duplas) {
      const userId = Number(state.currentCheckin?.userId || 0);
      return this.processRankingPoints({
        requestId: createRequestId("volei"),
        userId,
        modalidade: "volei",
        dataHora: new Date().toISOString(),
        score: {
          timeA: Number(placar.timeA || 0),
          timeB: Number(placar.timeB || 0),
        },
        timeAIds: [userId, Number(duplas.parceiroId)],
        timeBIds: [Number(duplas.adversario1Id), Number(duplas.adversario2Id)],
      });
    },
    async finalizarAtividadeNatacao(metros, tempo) {
      return this.processRankingPoints({
        requestId: createRequestId("natacao"),
        userId: Number(state.currentCheckin?.userId || 0),
        modalidade: "natacao",
        pontosGanhos: 20,
        dataHora: new Date().toISOString(),
        swimData: { metros: Number(metros || 0), tempo: String(tempo || "") },
      });
    },
    async finalizarAtividadeFuncional(detalhes) {
      return this.processRankingPoints({
        requestId: createRequestId("funcional"),
        userId: Number(state.currentCheckin?.userId || 0),
        modalidade: "funcional",
        pontosGanhos: 20,
        dataHora: new Date().toISOString(),
        wodData: detalhes,
      });
    },
  };

  function toast(message, type = "success") {
    if (typeof window.showToast === "function") {
      window.showToast(message, type);
      return;
    }
    alert(message);
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.error || "Falha na requisição.");
    }
    return data;
  }

  function createRequestId(prefix) {
    if (window.crypto?.randomUUID) {
      return `${prefix}-${window.crypto.randomUUID()}`;
    }
    return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1000000)}`;
  }

  function openModal(type) {
    state.modal.open = true;
    state.modal.type = type;
    state.modal.loading = false;
    state.modal.requestId = null;
    renderModal();
  }

  function closeModal() {
    state.modal.open = false;
    state.modal.type = null;
    state.modal.loading = false;
    state.modal.requestId = null;
    renderByModalidade();
  }

  function getAtletaNome(id) {
    return state.atletas.find((a) => Number(a.id) === Number(id))?.nome || `#${id}`;
  }

  function atletaOptions(extraPredicate = () => true) {
    const currentId = Number(state.currentCheckin?.userId || 0);
    return state.atletas
      .filter((a) => Number(a.id) !== currentId)
      .filter(extraPredicate)
      .map((a) => `<option value="${a.id}">${a.nome} (${a.email})</option>`)
      .join("");
  }

  function renderGenericCheckinPrompt() {
    root.innerHTML = `
      <article class="gym-card">
        <h3 class="gym-title">Gym indisponível no momento</h3>
        <p class="gym-subtitle">Faça check-in em uma modalidade para liberar esta área.</p>
        <div class="gym-empty">
          Nenhum check-in ativo encontrado. Acesse o Feed e confirme presença para abrir sua Área de Atividade.
        </div>
      </article>
    `;
  }

  function renderVoleiArenaView() {
    const resumo = state.volei.resumo;
    root.innerHTML = `
      <article class="gym-card">
        <h3 class="gym-title">VoleiArenaView</h3>
        <p class="gym-subtitle">Clique no Lado A ou Lado B da quadra para configurar a partida.</p>

        <div class="gym-activity-area" aria-label="Área de Atividade Vôlei">
          <svg class="gym-svg" viewBox="0 0 1000 540" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="sandGradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#efd39a" />
                <stop offset="50%" stop-color="#ddb370" />
                <stop offset="100%" stop-color="#bf8b49" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="1000" height="540" fill="url(#sandGradient)" />
            <rect x="80" y="50" width="840" height="440" rx="14" fill="none" stroke="rgba(255,255,255,0.7)" stroke-width="6" />
            <line x1="80" y1="270" x2="920" y2="270" stroke="rgba(255,255,255,0.8)" stroke-width="7" />
            <line x1="85" y1="255" x2="915" y2="255" stroke="rgba(15,23,42,0.2)" stroke-width="2" />
            <line x1="85" y1="285" x2="915" y2="285" stroke="rgba(15,23,42,0.2)" stroke-width="2" />
            <text x="500" y="150" text-anchor="middle" fill="#0f172a" font-size="38" font-weight="800">Lado A</text>
            <text x="500" y="415" text-anchor="middle" fill="#0f172a" font-size="38" font-weight="800">Lado B</text>
          </svg>
          <button type="button" class="gym-hotspot gym-hotspot--court-a" data-open="volei">Configurar Lado A</button>
          <button type="button" class="gym-hotspot gym-hotspot--court-b" data-open="volei">Configurar Lado B</button>
        </div>

        ${
          resumo
            ? `<div class="gym-summary"><strong>Partida concluída!</strong><br />Vencedores: ${resumo.vencedores.join(", ")}<br />Perdedores: ${resumo.perdedores.join(", ")}<br />Pontuação enviada para o Ranking Global.</div>`
            : ""
        }
      </article>
    `;

    root.querySelectorAll("[data-open='volei']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!state.atletas.length) {
          state.atletas = await apiService.buscarAtletas();
        }
        openModal("volei");
      });
    });
  }

  function renderNatacaoOceanView() {
    const resumo = state.natacao.resumo;
    root.innerHTML = `
      <article class="gym-card">
        <h3 class="gym-title">NatacaoOceanView</h3>
        <p class="gym-subtitle">Clique na zona do mar para registrar seu treino.</p>

        <div class="gym-activity-area" aria-label="Área de Atividade Natação">
          <svg class="gym-svg" viewBox="0 0 1000 540" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="oceanGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="#60d6ff" />
                <stop offset="45%" stop-color="#218abf" />
                <stop offset="100%" stop-color="#0f456b" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="1000" height="540" fill="url(#oceanGradient)" />
            <path d="M0 330 C70 300 140 360 210 330 C280 300 350 360 420 330 C490 300 560 360 630 330 C700 300 770 360 840 330 C910 300 960 350 1000 330 L1000 540 L0 540 Z" fill="rgba(255,255,255,0.2)" />
            <path d="M0 280 C80 250 160 310 240 280 C320 250 400 310 480 280 C560 250 640 310 720 280 C800 250 880 310 1000 280" fill="none" stroke="rgba(255,255,255,0.42)" stroke-width="5" />
            <text x="500" y="120" text-anchor="middle" fill="rgba(255,255,255,0.95)" font-size="40" font-weight="800">Zona Interativa do Mar</text>
          </svg>
          <button type="button" class="gym-hotspot gym-hotspot--ocean" data-open="natacao">Registrar Nado</button>
        </div>

        ${
          resumo
            ? `<div class="gym-summary"><strong>Nado registrado!</strong><br />Metros: ${resumo.metros}<br />Tempo: ${resumo.tempo}<br />Pontuação: +20 pontos.</div>`
            : ""
        }
      </article>
    `;

    root.querySelector("[data-open='natacao']")?.addEventListener("click", () => openModal("natacao"));
  }

  function renderFuncionalWodsView() {
    const resumo = state.funcional.resumo;
    root.innerHTML = `
      <article class="gym-card">
        <h3 class="gym-title">FuncionalWodsView</h3>
        <p class="gym-subtitle">Clique na ilustração para informar os dados do treino.</p>

        <div class="gym-activity-area" aria-label="Área de Atividade Funcional">
          <svg class="gym-svg" viewBox="0 0 1000 540" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="funcGradient" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stop-color="#ffb58c" />
                <stop offset="45%" stop-color="#f47821" />
                <stop offset="100%" stop-color="#7a3208" />
              </linearGradient>
            </defs>
            <rect x="0" y="0" width="1000" height="540" fill="url(#funcGradient)" />
            <circle cx="500" cy="130" r="48" fill="rgba(255,255,255,0.9)" />
            <path d="M420 240 C470 200 530 200 580 240 L620 270 C645 290 650 320 630 340 C610 360 580 355 560 336 L520 298 L500 350 L470 350 L450 298 L410 336 C390 355 360 360 340 340 C320 320 325 290 350 270 Z" fill="rgba(15,23,42,0.88)" />
            <rect x="405" y="380" width="190" height="24" rx="10" fill="rgba(15,23,42,0.85)" />
            <text x="500" y="470" text-anchor="middle" fill="rgba(255,255,255,0.95)" font-size="36" font-weight="800">Zona Interativa Funcional</text>
          </svg>
          <button type="button" class="gym-hotspot gym-hotspot--functional" data-open="funcional">Registrar Treino Funcional</button>
        </div>

        ${
          resumo
            ? `<div class="gym-summary"><strong>Treino finalizado!</strong><br />WOD: ${resumo.nomeTreino}<br />Tempo/Resultado: ${resumo.repsTempo}<br />Pontuação: +20 pontos.</div>`
            : ""
        }
      </article>
    `;

    root.querySelector("[data-open='funcional']")?.addEventListener("click", () => openModal("funcional"));
  }

  function buildVoleiModalContent() {
    const v = state.volei;
    return `
      <h3 class="gym-title">Configurar Partida de Vôlei</h3>
      <p class="gym-subtitle">Selecione as duplas e informe o placar final.</p>
      <div class="gym-grid gym-grid-2">
        <div>
          <label class="gym-label">Parceiro(a) da sua dupla</label>
          <select class="gym-select" id="voleiParceiro">
            <option value="">Selecione</option>
            ${atletaOptions((a) => Number(a.id) !== Number(v.adversario1Id || 0) && Number(a.id) !== Number(v.adversario2Id || 0))}
          </select>
        </div>
        <div>
          <label class="gym-label">Adversário 1</label>
          <select class="gym-select" id="voleiAdv1">
            <option value="">Selecione</option>
            ${atletaOptions((a) => Number(a.id) !== Number(v.parceiroId || 0) && Number(a.id) !== Number(v.adversario2Id || 0))}
          </select>
        </div>
        <div>
          <label class="gym-label">Adversário 2</label>
          <select class="gym-select" id="voleiAdv2">
            <option value="">Selecione</option>
            ${atletaOptions((a) => Number(a.id) !== Number(v.parceiroId || 0) && Number(a.id) !== Number(v.adversario1Id || 0))}
          </select>
        </div>
        <div>
          <label class="gym-label">Sets vencidos - Time A</label>
          <input id="voleiScoreA" class="gym-input" type="number" min="0" placeholder="Ex: 2" value="${v.scoreA}" />
        </div>
        <div>
          <label class="gym-label">Sets vencidos - Time B</label>
          <input id="voleiScoreB" class="gym-input" type="number" min="0" placeholder="Ex: 1" value="${v.scoreB}" />
        </div>
      </div>
      <div class="gym-grid" style="margin-top:0.8rem;">
        <button id="gymSubmitBtn" class="gym-button" type="button">Concluir Partida</button>
        <button id="gymCancelBtn" class="gym-button-secondary" type="button">Cancelar</button>
      </div>
    `;
  }

  function buildNatacaoModalContent() {
    const n = state.natacao;
    return `
      <h3 class="gym-title">Registrar Atividade de Natação</h3>
      <p class="gym-subtitle">Informe os dados do nado. A pontuação é fixa (+20).</p>
      <div class="gym-grid">
        <div>
          <label class="gym-label">Quantos metros foram feitos?</label>
          <input id="natacaoMetros" class="gym-input" type="number" min="1" placeholder="Ex: 1000" value="${n.metros}" />
        </div>
        <div>
          <label class="gym-label">Em quanto tempo? (hh:mm:ss)</label>
          <input id="natacaoTempo" class="gym-input" type="text" placeholder="Ex: 00:24:18" value="${n.tempo}" />
        </div>
      </div>
      <div class="gym-grid" style="margin-top:0.8rem;">
        <button id="gymSubmitBtn" class="gym-button" type="button">Enviar Dados</button>
        <button id="gymCancelBtn" class="gym-button-secondary" type="button">Cancelar</button>
      </div>
    `;
  }

  function buildFuncionalModalContent() {
    const f = state.funcional;
    return `
      <h3 class="gym-title">Registrar Treino Funcional</h3>
      <p class="gym-subtitle">Informe os detalhes do treino. A pontuação é fixa (+20).</p>
      <div class="gym-grid">
        <div>
          <label class="gym-label">Qual WOD você realizou?</label>
          <input id="funcionalNomeTreino" class="gym-input" type="text" placeholder="Ex: For Time 21-15-9" value="${f.nomeTreino}" />
        </div>
        <div>
          <label class="gym-label">Tempo total / resultado</label>
          <input id="funcionalRepsTempo" class="gym-input" type="text" placeholder="Ex: 12:43" value="${f.repsTempo}" />
        </div>
      </div>
      <div class="gym-grid" style="margin-top:0.8rem;">
        <button id="gymSubmitBtn" class="gym-button" type="button">Finalizar Treino</button>
        <button id="gymCancelBtn" class="gym-button-secondary" type="button">Cancelar</button>
      </div>
    `;
  }

  function renderModal() {
    const existing = document.getElementById("gymModal");
    if (existing) existing.remove();
    if (!state.modal.open || !state.modal.type) return;

    let content = "";
    if (state.modal.type === "volei") content = buildVoleiModalContent();
    if (state.modal.type === "natacao") content = buildNatacaoModalContent();
    if (state.modal.type === "funcional") content = buildFuncionalModalContent();

    const modal = document.createElement("div");
    modal.id = "gymModal";
    modal.className = "gym-modal is-open";
    modal.innerHTML = `
      <div class="gym-modal-backdrop" data-close="1"></div>
      <section class="gym-modal-panel">${content}</section>
    `;

    document.body.appendChild(modal);

    modal.querySelector("[data-close='1']")?.addEventListener("click", closeModal);
    modal.querySelector("#gymCancelBtn")?.addEventListener("click", closeModal);

    attachModalHandlers();
  }

  function attachModalHandlers() {
    if (state.modal.type === "volei") {
      const v = state.volei;
      const parceiro = document.getElementById("voleiParceiro");
      const adv1 = document.getElementById("voleiAdv1");
      const adv2 = document.getElementById("voleiAdv2");
      const scoreA = document.getElementById("voleiScoreA");
      const scoreB = document.getElementById("voleiScoreB");
      const btn = document.getElementById("gymSubmitBtn");

      if (parceiro) parceiro.value = v.parceiroId;
      if (adv1) adv1.value = v.adversario1Id;
      if (adv2) adv2.value = v.adversario2Id;

      parceiro?.addEventListener("change", (e) => (v.parceiroId = e.target.value));
      adv1?.addEventListener("change", (e) => (v.adversario1Id = e.target.value));
      adv2?.addEventListener("change", (e) => (v.adversario2Id = e.target.value));
      scoreA?.addEventListener("input", (e) => (v.scoreA = e.target.value));
      scoreB?.addEventListener("input", (e) => (v.scoreB = e.target.value));

      btn?.addEventListener("click", async () => {
        const parceiroId = Number(v.parceiroId || 0);
        const adversario1Id = Number(v.adversario1Id || 0);
        const adversario2Id = Number(v.adversario2Id || 0);
        const pontosA = Number(v.scoreA || 0);
        const pontosB = Number(v.scoreB || 0);

        if (!parceiroId || !adversario1Id || !adversario2Id) {
          toast("Selecione as duas duplas da partida.", "error");
          return;
        }
        if (new Set([parceiroId, adversario1Id, adversario2Id]).size !== 3) {
          toast("Os atletas selecionados devem ser diferentes.", "error");
          return;
        }
        if (pontosA === pontosB) {
          toast("Placar inválido: informe vencedor e perdedor.", "error");
          return;
        }

        try {
          btn.disabled = true;
          btn.textContent = "Processando...";
          const resposta = await apiService.finalizarPartidaVolei(
            { timeA: pontosA, timeB: pontosB },
            { parceiroId, adversario1Id, adversario2Id }
          );

          const vencedores = (resposta.resultado?.vencedores || []).map(getAtletaNome);
          const perdedores = (resposta.resultado?.perdedores || []).map(getAtletaNome);
          state.volei.resumo = { vencedores, perdedores };
          toast(resposta.message || "Partida finalizada.");
          closeModal();
        } catch (error) {
          toast(error.message || "Erro ao finalizar partida.", "error");
          btn.disabled = false;
          btn.textContent = "Concluir Partida";
        }
      });
      return;
    }

    if (state.modal.type === "natacao") {
      const n = state.natacao;
      const metros = document.getElementById("natacaoMetros");
      const tempo = document.getElementById("natacaoTempo");
      const btn = document.getElementById("gymSubmitBtn");

      metros?.addEventListener("input", (e) => (n.metros = e.target.value));
      tempo?.addEventListener("input", (e) => (n.tempo = e.target.value));

      btn?.addEventListener("click", async () => {
        if (!n.metros || !n.tempo) {
          toast("Preencha metros e tempo para continuar.", "error");
          return;
        }

        try {
          btn.disabled = true;
          btn.textContent = "Enviando...";
          const resposta = await apiService.finalizarAtividadeNatacao(n.metros, n.tempo);
          state.natacao.resumo = { metros: n.metros, tempo: n.tempo };
          toast(resposta.message || "Atividade de natação concluída.");
          closeModal();
        } catch (error) {
          toast(error.message || "Erro ao enviar nado.", "error");
          btn.disabled = false;
          btn.textContent = "Enviar Dados";
        }
      });
      return;
    }

    if (state.modal.type === "funcional") {
      const f = state.funcional;
      const nome = document.getElementById("funcionalNomeTreino");
      const repsTempo = document.getElementById("funcionalRepsTempo");
      const btn = document.getElementById("gymSubmitBtn");

      nome?.addEventListener("input", (e) => (f.nomeTreino = e.target.value));
      repsTempo?.addEventListener("input", (e) => (f.repsTempo = e.target.value));

      btn?.addEventListener("click", async () => {
        if (!f.nomeTreino || !f.repsTempo) {
          toast("Preencha os dados do treino.", "error");
          return;
        }

        try {
          btn.disabled = true;
          btn.textContent = "Finalizando...";
          const resposta = await apiService.finalizarAtividadeFuncional({
            nomeTreino: f.nomeTreino,
            repsTempo: f.repsTempo,
          });
          state.funcional.resumo = { nomeTreino: f.nomeTreino, repsTempo: f.repsTempo };
          toast(resposta.message || "Treino funcional concluído.");
          closeModal();
        } catch (error) {
          toast(error.message || "Erro ao finalizar treino.", "error");
          btn.disabled = false;
          btn.textContent = "Finalizar Treino";
        }
      });
    }
  }

  function renderByModalidade() {
    const modalidade = (state.currentCheckin?.modalidade || "").toLowerCase();
    if (modalidade === "volei") {
      renderVoleiArenaView();
      return;
    }
    if (modalidade === "natacao") {
      renderNatacaoOceanView();
      return;
    }
    if (modalidade === "funcional") {
      renderFuncionalWodsView();
      return;
    }
    renderGenericCheckinPrompt();
  }

  async function initGymViewManager() {
    try {
      const data = await apiService.getCurrentCheckin();
      state.userCheckinInfo = data.userCheckinInfo || null;
      state.currentCheckin = state.userCheckinInfo;
      window.userCheckinInfo = state.userCheckinInfo;
      window.currentCheckin = state.currentCheckin;

      if (state.currentCheckin?.modalidade === "volei") {
        state.atletas = await apiService.buscarAtletas();
      }

      renderByModalidade();
    } catch (error) {
      root.innerHTML = `<div class="gym-empty">Nao foi possivel carregar a tela Gym agora.</div>`;
      toast(error.message || "Falha ao inicializar Gym.", "error");
    }
  }

  window.refreshGymView = initGymViewManager;
  initGymViewManager();
})();
