#!/usr/bin/env python3
"""Interface web para configurar links de convite e comparar cliques.

Sobe um servidor local (http://127.0.0.1:5000) com tres telas: configuracao da
campanha, cadastro de funcionarios com geracao de links, e ranking/comparacao
de cliques.

Compartilha os mesmos CSVs e a mesma logica de API dos scripts de terminal
(veja bitly.py), entao da para usar web e CLI de forma intercalada.

ATENCAO: servidor local sem autenticacao, feito para rodar na sua maquina.
Nao exponha em rede publica. O token do Bitly nunca e enviado ao navegador.
"""

import csv
import os
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request, send_file

import bitly

app = Flask(__name__)

HOST = os.getenv("HOST", "127.0.0.1")
PORTA = int(os.getenv("PORTA", "5000"))


def responder_erro(mensagem, status=400):
    return jsonify({"erro": mensagem}), status


def executar_com_bitly(funcao):
    """Roda uma funcao que usa a API do Bitly, convertendo falhas em JSON legivel."""
    try:
        sessao = bitly.sessao_autenticada()
        return funcao(sessao)
    except bitly.TokenInvalido as erro:
        return responder_erro(
            f"Token do Bitly ausente ou invalido ({erro}). "
            'Exporte BITLY_TOKEN e reinicie o servidor.',
            401,
        )
    except requests.RequestException as erro:
        return responder_erro(f"Falha de rede ao falar com o Bitly: {erro}", 502)
    except bitly.ErroBitly as erro:
        return responder_erro(f"Bitly recusou a chamada: {erro}", 502)
    except ValueError as erro:
        return responder_erro(str(erro), 400)


def estado_token():
    return {"token_presente": bool(bitly.obter_token())}


# --------------------------------------------------------------------- telas


@app.route("/")
def tela_configuracao():
    return render_template(
        "configuracao.html",
        config=bitly.carregar_config(),
        exemplo_url=bitly.montar_url_utm(
            bitly.carregar_config()["evento_url"], "ana-souza"
        ),
        **estado_token(),
    )


@app.route("/funcionarios")
def tela_funcionarios():
    return render_template("funcionarios.html", **estado_token())


@app.route("/ranking")
def tela_ranking():
    return render_template("ranking.html", **estado_token())


# ----------------------------------------------------------- API: configuracao


@app.get("/api/config")
def api_config():
    return jsonify({"config": bitly.carregar_config(), **estado_token()})


@app.post("/api/config")
def api_salvar_config():
    dados = request.get_json(silent=True) or {}
    url = (dados.get("evento_url") or "").strip()
    if not url.startswith(("http://", "https://")):
        return responder_erro("A URL do evento precisa comecar com http:// ou https://")
    for campo in ("utm_source", "utm_medium", "utm_campaign"):
        if not (dados.get(campo) or "").strip():
            return responder_erro(f"O campo {campo} nao pode ficar vazio")
    return jsonify({"config": bitly.salvar_config(dados), "mensagem": "Configuracao salva."})


@app.get("/api/grupos")
def api_grupos():
    return executar_com_bitly(lambda sessao: jsonify({"grupos": bitly.listar_grupos(sessao)}))


# ---------------------------------------------------------- API: funcionarios


def montar_lista_funcionarios():
    """Junta funcionarios.csv com os links ja gerados."""
    links = bitly.links_por_identificador()
    lista = []
    for funcionario in bitly.ler_funcionarios(avisar=None):
        link = links.get(funcionario["identificador"], {})
        lista.append(
            {
                "nome": funcionario["nome"],
                "identificador": funcionario["identificador"],
                "url_utm": link.get("url_utm", ""),
                "link_curto": link.get("link_curto", ""),
                "bitlink_id": link.get("bitlink_id", ""),
            }
        )
    return lista


@app.get("/api/funcionarios")
def api_listar_funcionarios():
    try:
        return jsonify({"funcionarios": montar_lista_funcionarios(), **estado_token()})
    except ValueError as erro:
        return responder_erro(str(erro))


@app.post("/api/funcionarios")
def api_adicionar_funcionario():
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    identificador = (dados.get("identificador") or "").strip().lower()
    if not nome:
        return responder_erro("Informe o nome do funcionario")
    identificador = identificador or bitly.gerar_identificador(nome)
    if not bitly.identificador_valido(identificador):
        return responder_erro(
            "Identificador invalido: use apenas letras minusculas, numeros e hifens "
            "(ex.: ana-souza)"
        )

    funcionarios = bitly.ler_funcionarios(avisar=None)
    if any(f["identificador"] == identificador for f in funcionarios):
        return responder_erro(f"Ja existe um funcionario com o identificador '{identificador}'")

    funcionarios.append({"nome": nome, "identificador": identificador})
    bitly.salvar_funcionarios(funcionarios)
    return jsonify({"funcionarios": montar_lista_funcionarios(), "mensagem": f"{nome} adicionado."})


@app.put("/api/funcionarios/<identificador>")
def api_editar_funcionario(identificador):
    """So o nome e editavel: mudar o identificador quebraria o link ja distribuido."""
    dados = request.get_json(silent=True) or {}
    nome = (dados.get("nome") or "").strip()
    if not nome:
        return responder_erro("Informe o novo nome")

    funcionarios = bitly.ler_funcionarios(avisar=None)
    alvo = next((f for f in funcionarios if f["identificador"] == identificador), None)
    if alvo is None:
        return responder_erro(f"Funcionario '{identificador}' nao encontrado", 404)
    alvo["nome"] = nome
    bitly.salvar_funcionarios(funcionarios)

    # Mantem o nome sincronizado no CSV de links, se ja houver um.
    links = bitly.ler_links()
    if any(linha.get("identificador") == identificador for linha in links):
        for linha in links:
            if linha.get("identificador") == identificador:
                linha["nome"] = nome
        bitly.salvar_links(links)

    return jsonify({"funcionarios": montar_lista_funcionarios(), "mensagem": "Nome atualizado."})


@app.delete("/api/funcionarios/<identificador>")
def api_remover_funcionario(identificador):
    funcionarios = bitly.ler_funcionarios(avisar=None)
    restantes = [f for f in funcionarios if f["identificador"] != identificador]
    if len(restantes) == len(funcionarios):
        return responder_erro(f"Funcionario '{identificador}' nao encontrado", 404)
    bitly.salvar_funcionarios(restantes)

    links = [l for l in bitly.ler_links() if l.get("identificador") != identificador]
    bitly.salvar_links(links)

    return jsonify(
        {
            "funcionarios": montar_lista_funcionarios(),
            "mensagem": (
                "Funcionario removido do projeto. O link curto continua existindo no "
                "Bitly (a API nao foi chamada) e ainda funciona para quem ja o recebeu."
            ),
        }
    )


# ------------------------------------------------------------- API: gerar links


def _gerar_links(sessao, somente=None):
    config = bitly.carregar_config()
    funcionarios = bitly.ler_funcionarios(avisar=None)
    if somente:
        funcionarios = [f for f in funcionarios if f["identificador"] == somente]
        if not funcionarios:
            raise ValueError(f"Funcionario '{somente}' nao encontrado")

    existentes = bitly.links_por_identificador()
    avisos = []
    falhas = []
    criados = 0
    sem_keyword = 0

    for funcionario in funcionarios:
        identificador = funcionario["identificador"]
        if identificador in existentes and identificador != somente:
            continue

        url_utm = bitly.montar_url_utm(config["evento_url"], identificador, config)
        try:
            link_curto, bitlink_id, usou_keyword = bitly.criar_bitlink(
                sessao, url_utm, identificador, config, avisar=avisos.append
            )
        except (bitly.ErroBitly, requests.RequestException) as erro:
            falhas.append({"nome": funcionario["nome"], "identificador": identificador, "motivo": str(erro)})
            continue

        existentes[identificador] = {
            "nome": funcionario["nome"],
            "identificador": identificador,
            "url_utm": url_utm,
            "link_curto": link_curto,
            "bitlink_id": bitlink_id,
        }
        criados += 1
        if not usou_keyword:
            sem_keyword += 1

    # Grava na ordem do funcionarios.csv, mantendo so quem ainda esta cadastrado.
    ordenados = [
        existentes[f["identificador"]]
        for f in bitly.ler_funcionarios(avisar=None)
        if f["identificador"] in existentes
    ]
    bitly.salvar_links(ordenados)

    return jsonify(
        {
            "funcionarios": montar_lista_funcionarios(),
            "criados": criados,
            "sem_back_half_customizado": sem_keyword,
            "falhas": falhas,
            "avisos": avisos,
        }
    )


@app.post("/api/gerar-links")
def api_gerar_links():
    return executar_com_bitly(lambda sessao: _gerar_links(sessao))


@app.post("/api/gerar-links/<identificador>")
def api_gerar_link_individual(identificador):
    return executar_com_bitly(lambda sessao: _gerar_links(sessao, somente=identificador))


# ----------------------------------------------------------------- API: cliques


def _atualizar_cliques(sessao):
    links = [linha for linha in bitly.ler_links() if linha.get("bitlink_id")]
    if not links:
        raise ValueError("Nenhum link gerado ainda. Gere os links na tela Funcionarios.")

    resultados = []
    falhas = []
    for linha in links:
        try:
            cliques = bitly.consultar_cliques(sessao, linha["bitlink_id"])
        except (bitly.ErroBitly, requests.RequestException) as erro:
            cliques = None
            falhas.append({"nome": linha.get("nome", ""), "motivo": str(erro)})
        resultados.append(
            {
                "nome": linha.get("nome", ""),
                "identificador": linha.get("identificador", ""),
                "link_curto": linha.get("link_curto", ""),
                "cliques": cliques,
            }
        )

    bitly.ordenar_ranking(resultados)
    consultado_em = datetime.now().astimezone().isoformat(timespec="seconds")
    bitly.salvar_ranking(resultados, consultado_em)

    return jsonify(
        {
            "ranking": resultados,
            "total": sum(item["cliques"] or 0 for item in resultados),
            "consultado_em": consultado_em,
            "falhas": falhas,
        }
    )


@app.post("/api/atualizar")
def api_atualizar():
    return executar_com_bitly(_atualizar_cliques)


@app.get("/api/ranking")
def api_ranking():
    """Ultimo ranking salvo, sem chamar a API (carregamento instantaneo da tela)."""
    if not os.path.exists(bitly.ARQUIVO_RANKING):
        return jsonify({"ranking": [], "total": 0, "consultado_em": None})
    with open(bitly.ARQUIVO_RANKING, newline="", encoding="utf-8") as arquivo:
        linhas = list(csv.DictReader(arquivo))
    ranking = [
        {
            "posicao": int(linha.get("posicao") or 0),
            "nome": linha.get("nome", ""),
            "identificador": linha.get("identificador", ""),
            "link_curto": linha.get("link_curto", ""),
            "cliques": int(linha["cliques"]) if (linha.get("cliques") or "").strip() else None,
        }
        for linha in linhas
    ]
    return jsonify(
        {
            "ranking": ranking,
            "total": sum(item["cliques"] or 0 for item in ranking),
            "consultado_em": linhas[0].get("consultado_em") if linhas else None,
        }
    )


def _serie(sessao, dias):
    links = [linha for linha in bitly.ler_links() if linha.get("bitlink_id")]
    if not links:
        raise ValueError("Nenhum link gerado ainda. Gere os links na tela Funcionarios.")

    series = []
    falhas = []
    for linha in links:
        try:
            pontos = bitly.consultar_serie_diaria(sessao, linha["bitlink_id"], dias)
        except (bitly.ErroBitly, requests.RequestException) as erro:
            falhas.append({"nome": linha.get("nome", ""), "motivo": str(erro)})
            continue
        series.append(
            {
                "nome": linha.get("nome", ""),
                "identificador": linha.get("identificador", ""),
                "pontos": pontos,
            }
        )
    return jsonify({"series": series, "dias": dias, "falhas": falhas})


@app.get("/api/serie")
def api_serie():
    try:
        dias = int(request.args.get("dias", 30))
    except ValueError:
        return responder_erro("Parametro 'dias' precisa ser um numero inteiro")
    dias = max(1, min(dias, 365))
    return executar_com_bitly(lambda sessao: _serie(sessao, dias))


@app.get("/api/exportar")
def api_exportar():
    if not os.path.exists(bitly.ARQUIVO_RANKING):
        return responder_erro(
            "Nenhum ranking gerado ainda. Clique em 'Atualizar cliques' primeiro.", 404
        )
    return send_file(
        bitly.ARQUIVO_RANKING,
        as_attachment=True,
        download_name="ranking_cliques.csv",
        mimetype="text/csv",
    )


if __name__ == "__main__":
    print(f"Interface web em http://{HOST}:{PORTA}")
    if not bitly.obter_token():
        print("AVISO: BITLY_TOKEN nao definido. As telas abrem, mas as chamadas ao Bitly vao falhar.")
    app.run(host=HOST, port=PORTA, debug=False)
