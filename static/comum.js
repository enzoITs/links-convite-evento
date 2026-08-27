// Utilidades compartilhadas pelas tres telas.

const faixa = document.getElementById("mensagem");

function mostrarMensagem(texto, tipo = "ok") {
  faixa.textContent = texto;
  faixa.className = "faixa " + tipo;
  faixa.hidden = false;
  if (tipo === "ok") {
    clearTimeout(faixa._timer);
    faixa._timer = setTimeout(() => { faixa.hidden = true; }, 5000);
  }
}

// Envolve fetch para que qualquer erro da API vire uma faixa legivel,
// nunca um traceback ou uma pagina de erro crua.
async function api(url, opcoes = {}) {
  const config = { headers: { "Content-Type": "application/json" }, ...opcoes };
  let resposta;
  try {
    resposta = await fetch(url, config);
  } catch (erro) {
    throw new Error("Não consegui falar com o servidor local: " + erro.message);
  }
  let dados;
  try {
    dados = await resposta.json();
  } catch (erro) {
    throw new Error("Resposta inesperada do servidor (HTTP " + resposta.status + ")");
  }
  if (!resposta.ok) throw new Error(dados.erro || "HTTP " + resposta.status);
  return dados;
}

// Roda uma acao mostrando estado de carregamento no botao que a disparou.
async function comBotao(botao, rotulo, acao) {
  const original = botao.textContent;
  botao.disabled = true;
  botao.textContent = rotulo;
  try {
    await acao();
  } catch (erro) {
    mostrarMensagem(erro.message, "erro");
  } finally {
    botao.disabled = false;
    botao.textContent = original;
  }
}

function gerarIdentificador(nome) {
  return nome
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .toLowerCase();
}
