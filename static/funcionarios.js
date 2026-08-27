const corpoTabela = document.querySelector("#tabela-funcionarios tbody");
const formFuncionario = document.getElementById("form-funcionario");
const campoNome = document.getElementById("campo-nome");
const campoIdentificador = document.getElementById("campo-identificador");

// O identificador acompanha o nome ate o usuario digitar um proprio.
let identificadorEditadoManualmente = false;
campoIdentificador.addEventListener("input", () => { identificadorEditadoManualmente = true; });
campoNome.addEventListener("input", () => {
  if (!identificadorEditadoManualmente) campoIdentificador.value = gerarIdentificador(campoNome.value);
});

function celulaAcoes(funcionario) {
  const celula = document.createElement("td");

  if (funcionario.link_curto) {
    const copiar = document.createElement("button");
    copiar.className = "pequeno";
    copiar.textContent = "Copiar link";
    copiar.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(funcionario.link_curto);
        mostrarMensagem(`Link de ${funcionario.nome} copiado.`);
      } catch (erro) {
        mostrarMensagem("O navegador bloqueou a cópia. Selecione o link na tabela.", "aviso");
      }
    });
    celula.appendChild(copiar);
  } else {
    const gerar = document.createElement("button");
    gerar.className = "pequeno";
    gerar.textContent = "Gerar link";
    gerar.addEventListener("click", (evento) =>
      comBotao(evento.target, "Gerando...", async () => {
        const resposta = await api(`/api/gerar-links/${funcionario.identificador}`, { method: "POST" });
        relatarGeracao(resposta);
        desenhar(resposta.funcionarios);
      })
    );
    celula.appendChild(gerar);
  }

  const renomear = document.createElement("button");
  renomear.className = "pequeno";
  renomear.textContent = "Renomear";
  renomear.addEventListener("click", async () => {
    const nome = prompt("Novo nome:", funcionario.nome);
    if (!nome || nome === funcionario.nome) return;
    try {
      const resposta = await api(`/api/funcionarios/${funcionario.identificador}`, {
        method: "PUT",
        body: JSON.stringify({ nome }),
      });
      mostrarMensagem(resposta.mensagem);
      desenhar(resposta.funcionarios);
    } catch (erro) {
      mostrarMensagem(erro.message, "erro");
    }
  });
  celula.appendChild(renomear);

  const remover = document.createElement("button");
  remover.className = "pequeno";
  remover.textContent = "Remover";
  remover.addEventListener("click", async () => {
    if (!confirm(`Remover ${funcionario.nome} do projeto? O link curto continua ativo no Bitly.`)) return;
    try {
      const resposta = await api(`/api/funcionarios/${funcionario.identificador}`, { method: "DELETE" });
      mostrarMensagem(resposta.mensagem, "aviso");
      desenhar(resposta.funcionarios);
    } catch (erro) {
      mostrarMensagem(erro.message, "erro");
    }
  });
  celula.appendChild(remover);

  return celula;
}

function desenhar(funcionarios) {
  corpoTabela.innerHTML = "";
  if (!funcionarios.length) {
    const linha = document.createElement("tr");
    const celula = document.createElement("td");
    celula.colSpan = 4;
    celula.className = "vazio";
    celula.textContent = "Nenhum funcionário cadastrado ainda.";
    linha.appendChild(celula);
    corpoTabela.appendChild(linha);
    return;
  }

  funcionarios.forEach((funcionario) => {
    const linha = document.createElement("tr");

    const nome = document.createElement("td");
    nome.textContent = funcionario.nome;
    linha.appendChild(nome);

    const identificador = document.createElement("td");
    identificador.innerHTML = `<code>${funcionario.identificador}</code>`;
    linha.appendChild(identificador);

    const link = document.createElement("td");
    if (funcionario.link_curto) {
      const ancora = document.createElement("a");
      ancora.href = funcionario.link_curto;
      ancora.target = "_blank";
      ancora.rel = "noopener";
      ancora.textContent = funcionario.link_curto;
      ancora.title = funcionario.url_utm;
      link.appendChild(ancora);
    } else {
      link.className = "vazio";
      link.textContent = "sem link";
    }
    linha.appendChild(link);

    linha.appendChild(celulaAcoes(funcionario));
    corpoTabela.appendChild(linha);
  });
}

function relatarGeracao(resposta) {
  resposta.avisos.forEach((aviso) => console.warn(aviso));
  const partes = [`${resposta.criados} link(s) criado(s)`];
  if (resposta.sem_back_half_customizado) {
    partes.push(
      `${resposta.sem_back_half_customizado} com sufixo aleatório (back-half customizado exige conta Bitly paga)`
    );
  }
  if (resposta.falhas.length) {
    partes.push(
      "falhas: " + resposta.falhas.map((f) => `${f.nome} (${f.motivo})`).join("; ")
    );
    mostrarMensagem(partes.join(" · "), "aviso");
  } else {
    mostrarMensagem(partes.join(" · "));
  }
}

formFuncionario.addEventListener("submit", (evento) => {
  evento.preventDefault();
  const dados = Object.fromEntries(new FormData(formFuncionario).entries());
  comBotao(formFuncionario.querySelector('button[type="submit"]'), "Adicionando...", async () => {
    const resposta = await api("/api/funcionarios", { method: "POST", body: JSON.stringify(dados) });
    mostrarMensagem(resposta.mensagem);
    formFuncionario.reset();
    identificadorEditadoManualmente = false;
    campoNome.focus();
    desenhar(resposta.funcionarios);
  });
});

document.getElementById("btn-gerar").addEventListener("click", (evento) =>
  comBotao(evento.target, "Gerando...", async () => {
    const resposta = await api("/api/gerar-links", { method: "POST" });
    relatarGeracao(resposta);
    desenhar(resposta.funcionarios);
  })
);

api("/api/funcionarios")
  .then((dados) => desenhar(dados.funcionarios))
  .catch((erro) => mostrarMensagem(erro.message, "erro"));
