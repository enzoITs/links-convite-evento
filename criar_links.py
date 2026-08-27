#!/usr/bin/env python3
"""Gera um link curto Bitly por funcionario, com parametros UTM de atribuicao.

Le funcionarios.csv, monta a URL do evento com UTMs (utm_content = identificador
do funcionario), encurta cada uma via API do Bitly e grava o resultado em
links_funcionarios.csv.

Configuracao: config.json (editavel pela interface web ou na mao), com override
por variavel de ambiente. O token do Bitly vem SOMENTE de BITLY_TOKEN.
A logica de API e CSV fica em bitly.py, compartilhada com a interface web.
"""

import argparse
import sys

import requests

import bitly


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--forcar",
        action="store_true",
        help="recria os links mesmo para funcionarios que ja constam no CSV de saida",
    )
    args = parser.parse_args()

    config = bitly.carregar_config()
    if not bitly.obter_token():
        sys.exit(
            "ERRO: variavel de ambiente BITLY_TOKEN nao definida.\n"
            "      Gere um token em https://dev.bitly.com/docs/getting-started/authentication/\n"
            '      e rode: export BITLY_TOKEN="seu_token_aqui"'
        )
    if not config["bitly_group_guid"]:
        print(
            "AVISO: bitly_group_guid vazio. O Bitly vai usar o grupo padrao da conta.\n"
            "       Para fixar o grupo, veja o README (GET /v4/groups).\n"
        )

    try:
        funcionarios = bitly.ler_funcionarios()
    except ValueError as erro:
        sys.exit(f"ERRO: {erro}.")
    if not funcionarios:
        sys.exit(
            f"ERRO: nenhum funcionario valido em '{bitly.ARQUIVO_FUNCIONARIOS}'.\n"
            "      Preencha o CSV (colunas nome,identificador) ou use a interface web."
        )

    existentes = {} if args.forcar else bitly.links_por_identificador()

    print(f"Evento: {config['evento_url']}")
    print(f"Campanha: {config['utm_campaign']}")
    print(f"Funcionarios: {len(funcionarios)}\n")

    sessao = bitly.sessao_autenticada()
    resultados = []
    falhas = []
    reaproveitados = 0
    sem_keyword = 0

    for funcionario in funcionarios:
        nome = funcionario["nome"]
        identificador = funcionario["identificador"]

        if identificador in existentes:
            resultados.append(existentes[identificador])
            reaproveitados += 1
            print(f"- {nome}: ja existe ({existentes[identificador]['link_curto']}), pulando.")
            continue

        url_utm = bitly.montar_url_utm(config["evento_url"], identificador, config)
        print(f"- {nome} ({identificador})")
        try:
            link_curto, bitlink_id, usou_keyword = bitly.criar_bitlink(
                sessao, url_utm, identificador, config
            )
        except bitly.TokenInvalido as erro:
            print(f"\nERRO FATAL: token do Bitly invalido ou expirado ({erro}).")
            print("Gere um novo token e exporte em BITLY_TOKEN.")
            if resultados:
                bitly.salvar_links(resultados)
                print(f"Resultados parciais salvos em '{bitly.ARQUIVO_LINKS}'.")
            sys.exit(1)
        except requests.RequestException as erro:
            falhas.append((nome, identificador, f"falha de rede: {erro}"))
            print(f"  ERRO: falha de rede ({erro}). Pulando este funcionario.")
            continue
        except (bitly.ErroBitly, ValueError) as erro:
            falhas.append((nome, identificador, str(erro)))
            print(f"  ERRO: {erro}. Pulando este funcionario.")
            continue

        if not usou_keyword:
            sem_keyword += 1
        resultados.append(
            {
                "nome": nome,
                "identificador": identificador,
                "url_utm": url_utm,
                "link_curto": link_curto,
                "bitlink_id": bitlink_id,
            }
        )
        print(f"  OK: {link_curto}")

    if resultados:
        bitly.salvar_links(resultados)

    print("\n" + "=" * 60)
    print(f"Criados agora ....... {len(resultados) - reaproveitados}")
    print(f"Ja existentes ....... {reaproveitados}")
    print(f"Sem back-half custom  {sem_keyword} (conta Bitly gratuita nao permite)")
    print(f"Falhas .............. {len(falhas)}")
    if falhas:
        print("\nFuncionarios que falharam:")
        for nome, identificador, motivo in falhas:
            print(f"  - {nome} ({identificador}): {motivo}")
        print("\nCorrija o motivo e rode de novo: quem ja tem link sera pulado.")
    if resultados:
        print(f"\nArquivo gerado: {bitly.ARQUIVO_LINKS}")
    print("=" * 60)


if __name__ == "__main__":
    main()
