#!/usr/bin/env python3
"""Consulta os cliques de cada bitlink e monta o ranking de funcionarios.

Le links_funcionarios.csv (gerado por criar_links.py ou pela interface web),
consulta o total de cliques de cada link na API do Bitly e imprime/salva o
ranking. Pode ser rodado quantas vezes quiser ate o dia do evento: o total e
sempre recalculado do zero.

A logica de API e CSV fica em bitly.py, compartilhada com a interface web.
"""

import os
import sys
from datetime import datetime

import requests

import bitly


def imprimir_tabela(ranking):
    cabecalho = ("#", "NOME", "IDENTIFICADOR", "LINK", "CLIQUES")
    linhas = [
        (
            str(item["posicao"]),
            item["nome"],
            item["identificador"],
            item["link_curto"],
            str(item["cliques"]) if item["cliques"] is not None else "erro",
        )
        for item in ranking
    ]

    larguras = [
        max(len(linha[coluna]) for linha in [cabecalho, *linhas])
        for coluna in range(len(cabecalho))
    ]

    def formatar(valores):
        celulas = [
            valores[i].rjust(larguras[i]) if i in (0, 4) else valores[i].ljust(larguras[i])
            for i in range(len(valores))
        ]
        return "  ".join(celulas)

    separador = "-" * (sum(larguras) + 2 * (len(larguras) - 1))
    print("\n" + formatar(cabecalho))
    print(separador)
    for linha in linhas:
        print(formatar(linha))
    print(separador)

    total = sum(item["cliques"] or 0 for item in ranking)
    print(f"TOTAL DE CLIQUES: {total}")


def main():
    if not bitly.obter_token():
        sys.exit(
            "ERRO: variavel de ambiente BITLY_TOKEN nao definida.\n"
            "      Gere um token em https://dev.bitly.com/docs/getting-started/authentication/\n"
            '      e rode: export BITLY_TOKEN="seu_token_aqui"'
        )

    if not os.path.exists(bitly.ARQUIVO_LINKS):
        sys.exit(
            f"ERRO: arquivo '{bitly.ARQUIVO_LINKS}' nao encontrado.\n"
            "      Rode 'python3 criar_links.py' primeiro para gerar os links."
        )
    try:
        links = [linha for linha in bitly.ler_links() if linha.get("bitlink_id")]
    except ValueError as erro:
        sys.exit(f"ERRO: {erro}.")
    if not links:
        sys.exit(f"ERRO: nenhum link com bitlink_id em '{bitly.ARQUIVO_LINKS}'.")

    sessao = bitly.sessao_autenticada()
    print(f"Consultando cliques de {len(links)} links...\n")

    resultados = []
    falhas = []
    for linha in links:
        nome = linha.get("nome", "")
        try:
            cliques = bitly.consultar_cliques(sessao, linha["bitlink_id"])
        except bitly.TokenInvalido as erro:
            sys.exit(
                f"\nERRO FATAL: token do Bitly invalido ou expirado ({erro}).\n"
                "Gere um novo token e exporte em BITLY_TOKEN."
            )
        except requests.RequestException as erro:
            cliques = None
            falhas.append((nome, f"falha de rede: {erro}"))
            print(f"- {nome}: ERRO de rede ({erro})")
        except (bitly.ErroBitly, ValueError) as erro:
            cliques = None
            falhas.append((nome, str(erro)))
            print(f"- {nome}: ERRO ({erro})")
        else:
            print(f"- {nome}: {cliques} cliques")

        resultados.append(
            {
                "nome": nome,
                "identificador": linha.get("identificador", ""),
                "link_curto": linha.get("link_curto", ""),
                "cliques": cliques,
            }
        )

    bitly.ordenar_ranking(resultados)
    imprimir_tabela(resultados)

    consultado_em = datetime.now().astimezone().isoformat(timespec="seconds")
    bitly.salvar_ranking(resultados, consultado_em)
    print(f"\nRanking salvo em '{bitly.ARQUIVO_RANKING}' (consultado em {consultado_em}).")

    if falhas:
        print(f"\n{len(falhas)} link(s) nao puderam ser consultados:")
        for nome, motivo in falhas:
            print(f"  - {nome}: {motivo}")


if __name__ == "__main__":
    main()
