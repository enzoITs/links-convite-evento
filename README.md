# Ranking de cliques por funcionário (Bitly + UTM)

Gera um link curto único por funcionário — todos apontando para a mesma página de
inscrição do evento — e mede quantos cliques cada um gerou, montando um ranking.

A atribuição é feita por parâmetros UTM na URL de destino (`utm_content` recebe o
identificador do funcionário) e a contagem vem da API do Bitly.

Dá para usar de duas formas, que compartilham os mesmos arquivos e a mesma lógica:

- **Interface web** (`python3 app.py`) — configurar, cadastrar nomes, gerar links e
  comparar cliques pelo navegador. Veja a seção 9.
- **Terminal** — `criar_links.py` e `relatorio_cliques.py`, para rodar em lote ou agendar.

## Arquivos

| Arquivo | Papel |
|---|---|
| `app.py` | Interface web (Flask) |
| `bitly.py` | Núcleo compartilhado: configuração, CSVs e chamadas à API |
| `config.json` | Configuração da campanha (criado ao salvar pela web) |
| `funcionarios.csv` | Entrada: `nome,identificador` (um por linha) |
| `criar_links.py` | Monta as URLs com UTM e encurta no Bitly |
| `links_funcionarios.csv` | Saída do passo acima: `nome,identificador,url_utm,link_curto,bitlink_id` |
| `relatorio_cliques.py` | Consulta os cliques e monta o ranking |
| `ranking_cliques.csv` | Saída do ranking: `posicao,nome,identificador,link_curto,cliques,consultado_em` |

## 1. Instalação

Python 3.8+ e duas dependências externas (`requests` e `flask`):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 2. Token de acesso do Bitly

Documentação oficial: <https://dev.bitly.com/docs/getting-started/authentication/>

1. Entre em <https://app.bitly.com> com sua conta.
2. Vá em **Settings → API** (ou *Developer settings → API*).
3. Em **Access token**, digite sua senha e clique em **Generate token**.
4. Copie o token e exporte na sua shell:

```bash
export BITLY_TOKEN="seu_token_aqui"
```

O token **nunca** é lido de dentro do código: os scripts só o buscam na variável de
ambiente `BITLY_TOKEN`. Não escreva o token em nenhum arquivo do projeto. Para deixar
permanente, adicione a linha `export` ao seu `~/.bashrc` (ou use um gerenciador de
segredos).

## 3. Descobrir o `group_guid`

Toda conta Bitly pertence a pelo menos um grupo. Com o token exportado:

```bash
curl -H "Authorization: Bearer $BITLY_TOKEN" https://api-ssl.bitly.com/v4/groups
```

A resposta traz uma lista `groups`; use o campo `guid` do grupo desejado (numa conta
pessoal normalmente há só um):

```json
{ "groups": [ { "guid": "Bk3XXXXXXXX", "name": "Minha conta", ... } ] }
```

Se você deixar `BITLY_GROUP_GUID` vazio, o Bitly usa o grupo padrão da conta e o script
apenas emite um aviso — funciona, mas é mais previsível fixar o GUID.

## 4. Como a configuração funciona

**A configuração fica em `config.json`**, na raiz do projeto, e vale tanto para a
interface web quanto para os scripts de terminal. A precedência é:

```
variável de ambiente  >  config.json  >  padrão embutido em bitly.py
```

Ou seja: edite pela tela **Configuração** da interface web (jeito mais simples), ou
edite `config.json` na mão, ou exporte a variável de ambiente correspondente para
sobrescrever pontualmente sem tocar no arquivo. `BITLY_TOKEN` é a única exceção: existe
**somente** como variável de ambiente e nunca é gravado em `config.json` nem enviado ao
navegador.

| Chave em `config.json` | Variável de ambiente | Padrão | O que é |
|---|---|---|---|
| `evento_url` | `EVENTO_URL` | `https://exemplo.com/evento/inscricao` | Página de RSVP do evento |
| `utm_source` | `UTM_SOURCE` | `funcionario` | `utm_source` |
| `utm_medium` | `UTM_MEDIUM` | `convite` | `utm_medium` |
| `utm_campaign` | `UTM_CAMPAIGN` | `evento-2026` | `utm_campaign` |
| `bitly_domain` | `BITLY_DOMAIN` | `bit.ly` | Domínio do link curto |
| `bitly_group_guid` | `BITLY_GROUP_GUID` | *(vazio)* | Grupo da conta Bitly |
| `prefixo_keyword` | `PREFIXO_KEYWORD` | `evento-` | Prefixo do back-half customizado |

Os caminhos dos CSVs também aceitam override por `ARQUIVO_FUNCIONARIOS`, `ARQUIVO_LINKS`
e `ARQUIVO_RANKING`. A consulta de cliques usa `unit=day` + `units=-1`, que significa
"todo o período desde a criação do link", ou seja, o total acumulado.

## 5. Passo a passo de uso

1. Configure a campanha — no mínimo `evento_url` e `bitly_group_guid`. Pela interface
   web (tela **Configuração**) ou editando `config.json` na mão.
2. Preencha `funcionarios.csv`. O `identificador` vai para o `utm_content`, então use algo
   curto, sem espaços e sem acentos (`ana-souza`, `bruno-lima`). Ele precisa ser único.
3. Gere os links:

   ```bash
   export BITLY_TOKEN="seu_token_aqui"
   python3 criar_links.py
   ```

   Isso cria `links_funcionarios.csv`. O script é seguro para rodar de novo: funcionários
   que já têm link são pulados (útil se alguns falharem na primeira tentativa). Para
   recriar tudo do zero, use `python3 criar_links.py --forcar`.
4. Distribua a coluna `link_curto` para cada funcionário.
5. Sempre que quiser ver o placar (inclusive várias vezes por dia até o evento):

   ```bash
   python3 relatorio_cliques.py
   ```

   Ele imprime a tabela no terminal e regrava `ranking_cliques.csv` com o total
   atualizado e o horário da consulta.

## 6. Back-half customizado exige conta paga

O script tenta criar cada link com um back-half legível (`bit.ly/evento-ana-souza`), via
campo `keyword` da API. **Esse recurso só existe em planos pagos do Bitly.** Se a chamada
com `keyword` retornar erro 4xx, o script avisa no terminal e repete a chamada sem o
campo, caindo no sufixo aleatório do Bitly (`bit.ly/3xYzAbC`). A medição de cliques
funciona igual nos dois casos — muda só a aparência do link.

## 7. Erros e como o sistema reage

- **Sem `BITLY_TOKEN`** — sai imediatamente com instruções.
- **Token inválido (401)** — erro fatal: o script para, salva o que já conseguiu e pede
  um token novo.
- **Rate limit (429)** — respeita o header `Retry-After` (ou usa backoff 2s/4s/8s) e
  tenta novamente até 3 vezes; só então marca como falha.
- **URL inválida, permissão, grupo errado (4xx)** — o funcionário é pulado, o motivo é
  exibido e o processamento continua nos demais. No fim sai um resumo com a lista de
  falhas.
- **Timeout / queda de rede** — mesmo tratamento: pula e continua.

No `relatorio_cliques.py`, um link que falhe aparece como `erro` na tabela (e célula
vazia no CSV), sem virar zero e sem derrubar o relatório.

Na interface web vale o mesmo: cada falha vira uma faixa de aviso legível no topo da
página, nunca um traceback ou uma página de erro do servidor.

## 8. Interface web

Faz tudo o que os scripts fazem, pelo navegador: configurar a campanha, cadastrar os
nomes, gerar e atrelar os links, e comparar cliques.

```bash
source .venv/bin/activate
export BITLY_TOKEN="seu_token_aqui"
python3 app.py
```

Abra <http://127.0.0.1:5000>. Para trocar a porta: `PORTA=8080 python3 app.py`.

### Tela "Configuração"

Os mesmos campos da seção 4, salvos em `config.json`. O botão **Buscar meus grupos**
consulta `GET /v4/groups` e preenche o `group_guid` com um clique, sem precisar do
`curl`. Um exemplo da URL final com UTM é atualizado enquanto você digita.

### Tela "Funcionários"

- Adicionar funcionário: digite o nome; o identificador (`utm_content`) é sugerido
  automaticamente como slug (`Ana Souza` → `ana-souza`) e pode ser editado. Precisa ser
  único.
- **Gerar links faltantes** cria de uma vez os bitlinks de quem ainda não tem. Quem já
  tem link é pulado, então dá para clicar de novo sem duplicar nada. Também há um botão
  de gerar link individual, útil quando um funcionário falhou sozinho.
- **Copiar link** põe o link curto na área de transferência.
- **Renomear** muda só o nome exibido; o identificador não muda, porque ele já está
  dentro do link distribuído.
- **Remover** apaga o funcionário dos arquivos do projeto, mas **não destrói o link curto
  no Bitly** — quem já recebeu o link continua conseguindo abrir a página.

### Tela "Ranking"

- **Atualizar cliques** consulta o total de cada link e regrava `ranking_cliques.csv`.
  Pode ser clicado quantas vezes quiser até o dia do evento. Ao abrir a tela, o último
  ranking salvo aparece na hora, sem consultar a API.
- **Ranking com barras**: posição, cliques e a participação percentual de cada um no
  total, com barra proporcional.
- **Comparação lado a lado**: marque dois ou mais funcionários na tabela e um painel
  mostra só eles, com a diferença absoluta e percentual em relação ao líder da seleção.
- **Evolução no tempo**: escolha o período (7 a 90 dias) e clique em **Carregar
  gráfico** para ver os cliques por dia de cada link. A seleção da tabela também filtra o
  gráfico, e clicar na legenda liga/desliga uma linha. O gráfico é SVG desenhado pela
  própria página — nenhuma biblioteca externa, funciona offline.
- **Exportar CSV** baixa o `ranking_cliques.csv` atual.

### Web e terminal juntos

Os dois caminhos leem e escrevem os mesmos arquivos (`funcionarios.csv`,
`links_funcionarios.csv`, `ranking_cliques.csv`, `config.json`) e usam o mesmo código de
API (`bitly.py`). Você pode cadastrar pela web e rodar `relatorio_cliques.py` num cron,
por exemplo. Só evite rodar os dois ao mesmo tempo escrevendo no mesmo CSV.

### Segurança

O servidor sobe em `127.0.0.1` e **não tem autenticação**: ele foi feito para rodar na
sua máquina. Não exponha em rede pública nem troque o host para `0.0.0.0` sem colocar
uma camada de autenticação na frente. O token do Bitly fica só no processo do servidor —
nunca é enviado ao navegador nem gravado em disco.

## 9. Cruzando cliques com inscrições de fato no GA4

O Bitly conta **cliques**; ele não sabe quem realmente preencheu o RSVP. Para isso, use o
Google Analytics 4 da própria página do evento — **sem nenhuma configuração adicional
além do GA4 já estar instalado na página**, porque o GA4 captura os parâmetros UTM
automaticamente em toda visita.

Como o `utm_content` de cada link carrega o identificador do funcionário, cada sessão
originada de um convite já chega ao GA4 marcada com o dono do link.

No GA4:

- **Relatórios → Aquisição → Aquisição de tráfego**: troque a dimensão primária para
  **Conteúdo manual da sessão** (`session_manual_content`, alimentada pelo `utm_content`).
  Cada linha é um funcionário, com sessões, engajamento e conversões.
- **Explorar → Exploração de formato livre**: use **Conteúdo manual da sessão** nas linhas
  e, nas métricas, sessões + o evento de conversão da inscrição (`generate_lead`,
  `form_submit` ou o evento que sua página dispara ao concluir o RSVP).
- Filtre por **Campanha manual da sessão** = `evento-2026` para isolar só esse tráfego.

Comparando o CSV do ranking (cliques) com o relatório do GA4 (inscrições) você vê tanto
quem trouxe mais tráfego quanto quem trouxe tráfego que de fato converteu.
