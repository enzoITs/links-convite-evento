#!/usr/bin/env python3
"""Nucleo compartilhado do projeto: configuracao, CSVs e chamadas a API do Bitly.

Usado pelos scripts de terminal (criar_links.py, relatorio_cliques.py) e pela
interface web (app.py), para que os dois caminhos se comportem exatamente igual.

Configuracao: os valores vem de config.json, com precedencia
    variavel de ambiente > config.json > padrao embutido.
O token do Bitly e a unica excecao: vem SOMENTE da variavel de ambiente
BITLY_TOKEN e nunca e gravado em disco.
"""

import csv
import json
import os
import re
import time
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ARQUIVO_CONFIG = os.path.join(BASE_DIR, "config.json")
ARQUIVO_FUNCIONARIOS = os.path.join(BASE_DIR, os.getenv("ARQUIVO_FUNCIONARIOS", "funcionarios.csv"))
ARQUIVO_LINKS = os.path.join(BASE_DIR, os.getenv("ARQUIVO_LINKS", "links_funcionarios.csv"))
ARQUIVO_RANKING = os.path.join(BASE_DIR, os.getenv("ARQUIVO_RANKING", "ranking_cliques.csv"))

API_BASE = "https://api-ssl.bitly.com/v4"
API_BITLINKS = f"{API_BASE}/bitlinks"
TIMEOUT = 15
MAX_TENTATIVAS_RATE_LIMIT = 3

COLUNAS_FUNCIONARIOS = ["nome", "identificador"]
COLUNAS_LINKS = ["nome", "identificador", "url_utm", "link_curto", "bitlink_id"]
COLUNAS_RANKING = ["posicao", "nome", "identificador", "link_curto", "cliques", "consultado_em"]

# Padroes de configuracao. Cada chave aceita override pela variavel de ambiente
# de mesmo nome em maiusculas (EVENTO_URL, UTM_CAMPAIGN, BITLY_GROUP_GUID...).
CONFIG_PADRAO = {
    "evento_url": "https://exemplo.com/evento/inscricao",
    "utm_source": "funcionario",
    "utm_medium": "convite",
    "utm_campaign": "evento-2026",
    "bitly_domain": "bit.ly",
    "bitly_group_guid": "",
    "prefixo_keyword": "evento-",
}


class TokenInvalido(Exception):
    """Erro fatal: sem token valido nenhuma chamada a API funciona."""


class ErroBitly(Exception):
    """Erro tratavel da API: o item falha, o processamento continua."""


# ---------------------------------------------------------------- configuracao


def carregar_config():
    """Junta padrao + config.json + variaveis de ambiente (nessa ordem)."""
    config = dict(CONFIG_PADRAO)
    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, encoding="utf-8") as arquivo:
                salvo = json.load(arquivo)
        except (ValueError, OSError) as erro:
            print(f"AVISO: nao consegui ler '{ARQUIVO_CONFIG}' ({erro}). Usando padroes.")
            salvo = {}
        for chave in CONFIG_PADRAO:
            if isinstance(salvo.get(chave), str) and salvo[chave].strip():
                config[chave] = salvo[chave].strip()
            elif chave in salvo and salvo[chave] == "":
                config[chave] = ""

    for chave in CONFIG_PADRAO:
        do_ambiente = os.getenv(chave.upper())
        if do_ambiente is not None:
            config[chave] = do_ambiente.strip()
    return config


def salvar_config(dados):
    """Grava apenas as chaves conhecidas, preservando o resto do padrao."""
    config = dict(CONFIG_PADRAO)
    for chave in CONFIG_PADRAO:
        if chave in dados and dados[chave] is not None:
            config[chave] = str(dados[chave]).strip()
    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as arquivo:
        json.dump(config, arquivo, ensure_ascii=False, indent=2)
        arquivo.write("\n")
    return config


def obter_token():
    """Token do Bitly, somente da variavel de ambiente. String vazia se ausente."""
    return os.getenv("BITLY_TOKEN", "").strip()


def sessao_autenticada(token=None):
    token = token or obter_token()
    if not token:
        raise TokenInvalido("variavel de ambiente BITLY_TOKEN nao definida")
    sessao = requests.Session()
    sessao.headers.update(
        {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )
    return sessao


# ------------------------------------------------------------------------ UTM


def gerar_identificador(nome):
    """Transforma 'Ana Souza' em 'ana-souza': minusculas, sem acento, com hifens."""
    sem_acento = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", sem_acento).strip("-").lower()
    return slug


def identificador_valido(identificador):
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9-]*", identificador or ""))


def montar_url_utm(url_base, identificador, config=None):
    """Adiciona os parametros UTM preservando a query string e o fragmento."""
    config = config or carregar_config()
    partes = urlsplit(url_base)
    params = dict(parse_qsl(partes.query, keep_blank_values=True))
    params.update(
        {
            "utm_source": config["utm_source"],
            "utm_medium": config["utm_medium"],
            "utm_campaign": config["utm_campaign"],
            "utm_content": identificador,
        }
    )
    return urlunsplit(
        (partes.scheme, partes.netloc, partes.path, urlencode(params), partes.fragment)
    )


# ------------------------------------------------------------------- API Bitly


def mensagem_erro_api(resposta):
    """Extrai a mensagem mais util do corpo de erro da API do Bitly."""
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text.strip()[:200] or f"HTTP {resposta.status_code}"
    partes = [corpo.get("message"), corpo.get("description")]
    for campo in corpo.get("errors") or []:
        partes.append(f"{campo.get('field')}: {campo.get('error_code')}")
    detalhe = " | ".join(p for p in partes if p)
    return detalhe or f"HTTP {resposta.status_code}"


def requisitar(sessao, metodo, url, **kwargs):
    """Requisicao com 401 fatal e retry com backoff em 429 (rate limit)."""
    kwargs.setdefault("timeout", TIMEOUT)
    espera = 2
    resposta = None
    for tentativa in range(1, MAX_TENTATIVAS_RATE_LIMIT + 1):
        resposta = sessao.request(metodo, url, **kwargs)
        if resposta.status_code == 401:
            raise TokenInvalido(mensagem_erro_api(resposta))
        if resposta.status_code == 429 and tentativa < MAX_TENTATIVAS_RATE_LIMIT:
            retry_after = resposta.headers.get("Retry-After")
            pausa = int(retry_after) if str(retry_after or "").isdigit() else espera
            print(
                f"  AVISO: rate limit do Bitly (429). Aguardando {pausa}s "
                f"(tentativa {tentativa}/{MAX_TENTATIVAS_RATE_LIMIT})..."
            )
            time.sleep(pausa)
            espera *= 2
            continue
        return resposta
    return resposta


def listar_grupos(sessao):
    """Devolve [{guid, name}] da conta, para preencher o group_guid."""
    resposta = requisitar(sessao, "GET", f"{API_BASE}/groups")
    if resposta.status_code >= 400:
        raise ErroBitly(mensagem_erro_api(resposta))
    grupos = resposta.json().get("groups") or []
    return [{"guid": g.get("guid", ""), "name": g.get("name", "")} for g in grupos]


def criar_bitlink(sessao, url_longa, identificador, config=None, avisar=print):
    """Cria o bitlink. Retorna (link_curto, bitlink_id, usou_keyword).

    Back-half customizado (campo "keyword") so funciona em contas Bitly pagas.
    Se a chamada com keyword falhar com 4xx, repetimos sem ela para cair no
    sufixo aleatorio do Bitly em vez de travar o processo.
    """
    config = config or carregar_config()
    corpo = {"long_url": url_longa, "domain": config["bitly_domain"]}
    if config["bitly_group_guid"]:
        corpo["group_guid"] = config["bitly_group_guid"]

    com_keyword = dict(corpo, keyword=f"{config['prefixo_keyword']}{identificador}")
    resposta = requisitar(sessao, "POST", API_BITLINKS, json=com_keyword)

    usou_keyword = True
    if 400 <= resposta.status_code < 500:
        if avisar:
            avisar(
                f"  AVISO: keyword customizada rejeitada ({mensagem_erro_api(resposta)}). "
                "Repetindo sem keyword (link com sufixo aleatorio)."
            )
        usou_keyword = False
        resposta = requisitar(sessao, "POST", API_BITLINKS, json=corpo)

    if resposta.status_code >= 400:
        raise ErroBitly(mensagem_erro_api(resposta))

    dados = resposta.json()
    return dados.get("link", ""), dados.get("id", ""), usou_keyword


def consultar_cliques(sessao, bitlink_id):
    """Total de cliques do bitlink desde a criacao (unit=day, units=-1)."""
    resposta = requisitar(
        sessao,
        "GET",
        f"{API_BITLINKS}/{bitlink_id}/clicks/summary",
        params={"unit": "day", "units": -1},
    )
    if resposta.status_code >= 400:
        raise ErroBitly(mensagem_erro_api(resposta))
    return int(resposta.json().get("total_clicks", 0))


def consultar_serie_diaria(sessao, bitlink_id, dias=30):
    """Serie diaria de cliques: [{'date': ISO, 'clicks': int}], do mais antigo ao mais novo."""
    resposta = requisitar(
        sessao,
        "GET",
        f"{API_BITLINKS}/{bitlink_id}/clicks",
        params={"unit": "day", "units": dias},
    )
    if resposta.status_code >= 400:
        raise ErroBitly(mensagem_erro_api(resposta))
    serie = resposta.json().get("link_clicks") or []
    pontos = [
        {"date": (item.get("date") or "")[:10], "clicks": int(item.get("clicks") or 0)}
        for item in serie
    ]
    pontos.sort(key=lambda p: p["date"])
    return pontos


# ------------------------------------------------------------------------ CSVs


def _ler_csv(caminho, colunas_obrigatorias):
    if not os.path.exists(caminho):
        return []
    with open(caminho, newline="", encoding="utf-8") as arquivo:
        leitor = csv.DictReader(arquivo)
        cabecalho = set(c.strip() for c in (leitor.fieldnames or []))
        faltando = set(colunas_obrigatorias) - cabecalho
        if faltando:
            raise ValueError(
                f"'{os.path.basename(caminho)}' precisa das colunas "
                f"{','.join(colunas_obrigatorias)} (faltando: {', '.join(sorted(faltando))})"
            )
        return [dict(linha) for linha in leitor]


def _salvar_csv(caminho, colunas, linhas):
    with open(caminho, "w", newline="", encoding="utf-8") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=colunas)
        escritor.writeheader()
        for linha in linhas:
            escritor.writerow({coluna: linha.get(coluna, "") for coluna in colunas})


def ler_funcionarios(caminho=None, avisar=print):
    """Le funcionarios.csv validando nome/identificador e descartando duplicados."""
    caminho = caminho or ARQUIVO_FUNCIONARIOS
    funcionarios = []
    vistos = set()
    for numero, linha in enumerate(_ler_csv(caminho, COLUNAS_FUNCIONARIOS), start=2):
        nome = (linha.get("nome") or "").strip()
        identificador = (linha.get("identificador") or "").strip()
        if not nome and not identificador:
            continue
        if not nome or not identificador:
            if avisar:
                avisar(f"  AVISO: linha {numero} incompleta, ignorada.")
            continue
        if identificador in vistos:
            if avisar:
                avisar(
                    f"  AVISO: identificador '{identificador}' repetido na linha "
                    f"{numero}, ignorado (deve ser unico por funcionario)."
                )
            continue
        vistos.add(identificador)
        funcionarios.append({"nome": nome, "identificador": identificador})
    return funcionarios


def salvar_funcionarios(funcionarios, caminho=None):
    _salvar_csv(caminho or ARQUIVO_FUNCIONARIOS, COLUNAS_FUNCIONARIOS, funcionarios)


def ler_links(caminho=None):
    """Le links_funcionarios.csv (lista de dicionarios)."""
    return _ler_csv(caminho or ARQUIVO_LINKS, COLUNAS_LINKS)


def links_por_identificador(caminho=None):
    """Mapa identificador -> linha, so para quem ja tem link curto."""
    return {
        linha["identificador"]: linha
        for linha in ler_links(caminho)
        if linha.get("identificador") and linha.get("link_curto")
    }


def salvar_links(linhas, caminho=None):
    _salvar_csv(caminho or ARQUIVO_LINKS, COLUNAS_LINKS, linhas)


def salvar_ranking(ranking, consultado_em, caminho=None):
    linhas = [
        {
            "posicao": item["posicao"],
            "nome": item["nome"],
            "identificador": item["identificador"],
            "link_curto": item["link_curto"],
            "cliques": "" if item["cliques"] is None else item["cliques"],
            "consultado_em": consultado_em,
        }
        for item in ranking
    ]
    _salvar_csv(caminho or ARQUIVO_RANKING, COLUNAS_RANKING, linhas)


def ordenar_ranking(resultados):
    """Ordena por cliques desc.; links com erro (None) vao para o fim, sem virar zero."""
    resultados.sort(
        key=lambda item: (item["cliques"] if item["cliques"] is not None else -1),
        reverse=True,
    )
    for posicao, item in enumerate(resultados, start=1):
        item["posicao"] = posicao
    return resultados
