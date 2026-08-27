// Tela de ranking: tabela com barras, comparacao lado a lado e grafico de
// evolucao em SVG desenhado na mao (sem biblioteca externa, funciona offline).

const corpoRanking = document.querySelector("#tabela-ranking tbody");
const totalTexto = document.getElementById("total-cliques");
const consultadoEm = document.getElementById("consultado-em");
const painelComparacao = document.getElementById("painel-comparacao");
const cartoesComparacao = document.getElementById("cartoes-comparacao");
const marcarTodos = document.getElementById("marcar-todos");
const divGrafico = document.getElementById("grafico");
const divLegenda = document.getElementById("legenda");

const CORES = ["#2563eb", "#dc2626", "#059669", "#d97706", "#7c3aed",
               "#0891b2", "#db2777", "#65a30d", "#475569", "#c2410c"];

let ranking = [];
let series = [];
let ultimaConsulta = null;
const selecionados = new Set();
const ocultos = new Set();

function corDe(identificador) {
  const indice = ranking.findIndex((item) => item.identificador === identificador);
  return CORES[(indice < 0 ? 0 : indice) % CORES.length];
}

// ------------------------------------------------------------------- tabela

function desenharRanking(dados) {
  ranking = dados.ranking || [];
  if (dados.consultado_em !== undefined) ultimaConsulta = dados.consultado_em;
  const total = dados.total || 0;
  corpoRanking.innerHTML = "";

  if (!ranking.length) {
    const linha = document.createElement("tr");
    const celula = document.createElement("td");
    celula.colSpan = 6;
    celula.className = "vazio";
    celula.textContent = "Nenhum ranking ainda. Gere os links e clique em 'Atualizar cliques'.";
    linha.appendChild(celula);
    corpoRanking.appendChild(linha);
    totalTexto.textContent = "";
    return;
  }

  const maior = Math.max(...ranking.map((item) => item.cliques || 0), 1);

  ranking.forEach((item) => {
    const linha = document.createElement("tr");

    const marcar = document.createElement("td");
    const caixa = document.createElement("input");
    caixa.type = "checkbox";
    caixa.checked = selecionados.has(item.identificador);
    caixa.addEventListener("change", () => {
      if (caixa.checked) selecionados.add(item.identificador);
      else selecionados.delete(item.identificador);
      atualizarComparacao();
      desenharGrafico();
    });
    marcar.appendChild(caixa);
    linha.appendChild(marcar);

    const posicao = document.createElement("td");
    posicao.textContent = item.posicao;
    linha.appendChild(posicao);

    const nome = document.createElement("td");
    nome.textContent = item.nome;
    linha.appendChild(nome);

    const link = document.createElement("td");
    const ancora = document.createElement("a");
    ancora.href = item.link_curto;
    ancora.target = "_blank";
    ancora.rel = "noopener";
    ancora.textContent = item.link_curto;
    link.appendChild(ancora);
    linha.appendChild(link);

    const cliques = document.createElement("td");
    cliques.className = "numero";
    cliques.textContent = item.cliques === null ? "erro" : item.cliques;
    linha.appendChild(cliques);

    const participacao = document.createElement("td");
    const percentual = total ? ((item.cliques || 0) / total) * 100 : 0;
    participacao.innerHTML =
      `<div class="participacao">` +
      `<div class="barra"><span style="width:${((item.cliques || 0) / maior) * 100}%;` +
      `background:${corDe(item.identificador)}"></span></div>` +
      `<small>${percentual.toFixed(1)}%</small></div>`;
    linha.appendChild(participacao);

    corpoRanking.appendChild(linha);
  });

  totalTexto.textContent = `Total de cliques: ${total}`;
  consultadoEm.textContent = ultimaConsulta
    ? `Última consulta: ${new Date(ultimaConsulta).toLocaleString("pt-BR")}`
    : "Ainda não consultado. Clique em 'Atualizar cliques'.";

  if (dados.falhas && dados.falhas.length) {
    mostrarMensagem(
      `${dados.falhas.length} link(s) não puderam ser consultados: ` +
        dados.falhas.map((f) => `${f.nome} (${f.motivo})`).join("; "),
      "aviso"
    );
  }
  atualizarComparacao();
}

// -------------------------------------------------------------- comparacao

function atualizarComparacao() {
  const escolhidos = ranking.filter((item) => selecionados.has(item.identificador));
  if (escolhidos.length < 2) {
    painelComparacao.hidden = true;
    return;
  }
  painelComparacao.hidden = false;
  cartoesComparacao.innerHTML = "";

  const lider = escolhidos.reduce((a, b) => ((b.cliques || 0) > (a.cliques || 0) ? b : a));
  escolhidos.forEach((item) => {
    const cliques = item.cliques || 0;
    const base = lider.cliques || 0;
    const diferenca = cliques - base;
    const percentual = base ? (diferenca / base) * 100 : 0;

    const cartao = document.createElement("div");
    cartao.className = "item";
    cartao.style.borderLeftColor = corDe(item.identificador);
    cartao.innerHTML =
      `<strong>${item.nome}</strong>` +
      `<div class="valor">${item.cliques === null ? "erro" : cliques}</div>` +
      `<div class="delta">${
        item === lider
          ? "líder da seleção"
          : `${diferenca} cliques (${percentual.toFixed(1)}%) vs. ${lider.nome}`
      }</div>`;
    cartoesComparacao.appendChild(cartao);
  });
}

// ----------------------------------------------------------------- grafico

function svgEl(tag, atributos) {
  const elemento = document.createElementNS("http://www.w3.org/2000/svg", tag);
  Object.entries(atributos).forEach(([chave, valor]) => elemento.setAttribute(chave, valor));
  return elemento;
}

function seriesVisiveis() {
  const filtradas = selecionados.size
    ? series.filter((serie) => selecionados.has(serie.identificador))
    : series;
  return filtradas.filter((serie) => !ocultos.has(serie.identificador));
}

function desenharGrafico() {
  divGrafico.innerHTML = "";
  desenharLegenda();
  const visiveis = seriesVisiveis();
  if (!visiveis.length) {
    divGrafico.innerHTML = '<p class="ajuda">Sem série carregada. Clique em "Carregar gráfico".</p>';
    return;
  }

  const datas = [...new Set(visiveis.flatMap((s) => s.pontos.map((p) => p.date)))].sort();
  if (!datas.length) {
    divGrafico.innerHTML = '<p class="ajuda">O Bitly ainda não registrou cliques nesse período.</p>';
    return;
  }

  const largura = 880, altura = 320;
  const margem = { topo: 16, direita: 16, baixo: 42, esquerda: 44 };
  const larguraUtil = largura - margem.esquerda - margem.direita;
  const alturaUtil = altura - margem.topo - margem.baixo;

  const maximo = Math.max(1, ...visiveis.flatMap((s) => s.pontos.map((p) => p.clicks)));
  const x = (indice) => margem.esquerda + (datas.length === 1 ? larguraUtil / 2 : (indice / (datas.length - 1)) * larguraUtil);
  const y = (valor) => margem.topo + alturaUtil - (valor / maximo) * alturaUtil;

  const svg = svgEl("svg", { viewBox: `0 0 ${largura} ${altura}`, width: "100%", height: altura });

  // Grade horizontal + rotulos do eixo Y.
  for (let i = 0; i <= 4; i++) {
    const valor = Math.round((maximo / 4) * i);
    const posicao = y(valor);
    svg.appendChild(svgEl("line", {
      x1: margem.esquerda, x2: largura - margem.direita, y1: posicao, y2: posicao,
      stroke: "#e2e5ea",
    }));
    const rotulo = svgEl("text", { x: margem.esquerda - 8, y: posicao + 4, "text-anchor": "end", "font-size": 11, fill: "#6b7280" });
    rotulo.textContent = valor;
    svg.appendChild(rotulo);
  }

  // Rotulos do eixo X (no maximo 6, para nao embolar).
  const passo = Math.max(1, Math.ceil(datas.length / 6));
  datas.forEach((data, indice) => {
    if (indice % passo && indice !== datas.length - 1) return;
    const rotulo = svgEl("text", { x: x(indice), y: altura - 14, "text-anchor": "middle", "font-size": 11, fill: "#6b7280" });
    rotulo.textContent = data.slice(5).split("-").reverse().join("/");
    svg.appendChild(rotulo);
  });

  visiveis.forEach((serie) => {
    const porData = Object.fromEntries(serie.pontos.map((p) => [p.date, p.clicks]));
    const pontos = datas.map((data, indice) => [x(indice), y(porData[data] || 0)]);
    svg.appendChild(svgEl("polyline", {
      points: pontos.map(([px, py]) => `${px},${py}`).join(" "),
      fill: "none",
      stroke: corDe(serie.identificador),
      "stroke-width": 2,
      "stroke-linejoin": "round",
    }));
    pontos.forEach(([px, py], indice) => {
      const circulo = svgEl("circle", { cx: px, cy: py, r: 3, fill: corDe(serie.identificador) });
      const titulo = svgEl("title", {});
      titulo.textContent = `${serie.nome} — ${datas[indice]}: ${porData[datas[indice]] || 0} cliques`;
      circulo.appendChild(titulo);
      svg.appendChild(circulo);
    });
  });

  divGrafico.appendChild(svg);
}

function desenharLegenda() {
  divLegenda.innerHTML = "";
  const candidatas = selecionados.size
    ? series.filter((serie) => selecionados.has(serie.identificador))
    : series;
  candidatas.forEach((serie) => {
    const botao = document.createElement("button");
    botao.className = ocultos.has(serie.identificador) ? "desligado" : "";
    botao.innerHTML = `<span class="cor" style="background:${corDe(serie.identificador)}"></span>${serie.nome}`;
    botao.addEventListener("click", () => {
      if (ocultos.has(serie.identificador)) ocultos.delete(serie.identificador);
      else ocultos.add(serie.identificador);
      desenharGrafico();
    });
    divLegenda.appendChild(botao);
  });
}

// ------------------------------------------------------------------- eventos

marcarTodos.addEventListener("change", () => {
  selecionados.clear();
  if (marcarTodos.checked) ranking.forEach((item) => selecionados.add(item.identificador));
  desenharRanking({ ranking, total: ranking.reduce((soma, item) => soma + (item.cliques || 0), 0) });
  desenharGrafico();
});

document.getElementById("btn-atualizar").addEventListener("click", (evento) =>
  comBotao(evento.target, "Consultando...", async () => {
    const dados = await api("/api/atualizar", { method: "POST" });
    desenharRanking(dados);
    if (!dados.falhas.length) mostrarMensagem("Cliques atualizados.");
  })
);

document.getElementById("btn-serie").addEventListener("click", (evento) =>
  comBotao(evento.target, "Carregando...", async () => {
    const dias = document.getElementById("dias").value;
    const dados = await api(`/api/serie?dias=${dias}`);
    series = dados.series;
    ocultos.clear();
    desenharGrafico();
    if (dados.falhas.length) {
      mostrarMensagem(
        "Séries não carregadas: " + dados.falhas.map((f) => `${f.nome} (${f.motivo})`).join("; "),
        "aviso"
      );
    }
  })
);

api("/api/ranking")
  .then(desenharRanking)
  .catch((erro) => mostrarMensagem(erro.message, "erro"));
desenharGrafico();
