const formConfig = document.getElementById("form-config");
const exemplo = document.getElementById("exemplo-url");

function atualizarExemplo() {
  const dados = Object.fromEntries(new FormData(formConfig).entries());
  let base;
  try {
    base = new URL(dados.evento_url);
  } catch (erro) {
    exemplo.textContent = "(URL do evento inválida)";
    return;
  }
  base.searchParams.set("utm_source", dados.utm_source);
  base.searchParams.set("utm_medium", dados.utm_medium);
  base.searchParams.set("utm_campaign", dados.utm_campaign);
  base.searchParams.set("utm_content", "ana-souza");
  exemplo.textContent = base.toString();
}

formConfig.addEventListener("input", atualizarExemplo);

formConfig.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const dados = Object.fromEntries(new FormData(formConfig).entries());
  comBotao(formConfig.querySelector('button[type="submit"]'), "Salvando...", async () => {
    const resposta = await api("/api/config", { method: "POST", body: JSON.stringify(dados) });
    mostrarMensagem(resposta.mensagem);
  });
});

document.getElementById("btn-grupos").addEventListener("click", (evento) => {
  const lista = document.getElementById("lista-grupos");
  comBotao(evento.target, "Buscando...", async () => {
    const { grupos } = await api("/api/grupos");
    lista.innerHTML = "";
    lista.hidden = false;
    if (!grupos.length) {
      lista.textContent = "Nenhum grupo retornado pela conta.";
      return;
    }
    grupos.forEach((grupo) => {
      const botao = document.createElement("button");
      botao.type = "button";
      botao.className = "pequeno";
      botao.textContent = `${grupo.name || "(sem nome)"} — ${grupo.guid}`;
      botao.addEventListener("click", () => {
        formConfig.bitly_group_guid.value = grupo.guid;
        mostrarMensagem("group_guid preenchido. Não esqueça de salvar.");
      });
      lista.appendChild(botao);
    });
  });
});

atualizarExemplo();
