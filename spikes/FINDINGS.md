# Fase 0: resultados dos testes de viabilidade

Testes feitos em 2026-11-04, na máquina local (Windows, Python 3.14) e no GitHub Actions (`ubuntu-latest`, Python 3.12.16, runner nos EUA).

## Resumo

| Pergunta | Resposta |
|---|---|
| A Steam devolve BRL para um servidor fora do Brasil? | Sim. Com `cc=br`, todos os preços vieram em BRL no runner dos EUA |
| A consulta agrupada funciona? | Sim, mas sem máximo fixo. Lotes de 50 e de 100 funcionaram; a partir de 186 jogos, alguns conjuntos falham com HTTP 500 |
| Quanto histórico o ITAD fornece, e em BRL? | Desde o lançamento, em BRL, mas só parece confiável a partir de 2019 |
| Wishlist e biblioteca funcionam? | Sim, no perfil público do autor |

## Steam: preço (`appdetails`)

Script: `spikes/steam_prices.py`. Parâmetros: `cc=br` e `filters=price_overview`.

```json
{
  "3240220": {
    "success": true,
    "data": {
      "price_overview": {
        "currency": "BRL",
        "initial": 14990,
        "final": 7495,
        "discount_percent": 50,
        "initial_formatted": "R$ 149,90",
        "final_formatted": "R$ 74,95"
      }
    }
  }
}
```

- A chave da raiz é o appid, como texto.
- `initial` e `final` são inteiros em centavos. `initial` é o preço sem desconto e `final` é o preço pago.
- Sem desconto, `initial` é igual a `final`, `discount_percent` é 0 e `initial_formatted` vem vazio.
- Sem preço, a entrada é `{"success": true, "data": []}`: `data` vira lista vazia em vez de objeto. Visto em jogos gratuitos como CS2 e Dota 2; o motivo não foi verificado em todos os casos.
- Na resposta, os campos úteis para a coleta são `initial`, `final`, `discount_percent` e `currency`.

## Steam: consulta agrupada

Mesmo endpoint, com `appids=a,b,c`.

- Os 8 jogos comparados, inclusive 3 em promoção, tiveram preço idêntico ao da consulta individual, na máquina local e no Actions.
- Nas consultas de degraus, nenhuma entrada veio com `success: false`, e todos os preços retornados estavam em BRL.

Cobertura de ~990 appids reais, dos mais vendidos, divididos em lotes:

| Lote | Local (993 appids) | Actions (990 appids) |
|---|---|---|
| 100 por chamada | 10 de 10 chamadas ok | 10 de 10 chamadas ok |
| 50 por chamada | 20 de 20 chamadas ok | 20 de 20 chamadas ok |

Tamanhos maiores:

| Conjunto | Tamanho | Resultado |
|---|---|---|
| Primeiros 185 da amostra | 185 | HTTP 200, repetível |
| Primeiros 186 da amostra | 186 | HTTP 500, repetível |
| Sem o 1º da amostra (posições 2 a 186) | 185 | HTTP 200 |
| Posições 101 a 286 | 186 | HTTP 200 |
| Posições 301 a 500 | 200 | HTTP 200 |
| 213 appids de menor número | 213 | HTTP 200 |
| Primeiros 200, 300, 500 e 750 da amostra | 200 a 750 | HTTP 500, local e Actions |

**Causa não identificada.** Hipóteses descartadas:
- Só a quantidade: 213 passou e 186 falhou.
- Tamanho da URL: 1.528 caracteres em `appids` passaram, assim como poucos appids com 2.000 caracteres de enchimento na URL.
- Um appid isolado: o suspeito (1174180) funciona sozinho e em lotes pequenos, e retirá-lo não resolveu.

Não foi descartada uma combinação específica de jogos. Quando um lote falha, ele não devolve nenhum jogo.

## Steam: servidor fora do Brasil

Workflow: `.github/workflows/spike.yml`, executado manualmente.

- País do runner: `US`, consultado em `ipinfo.io`.
- Moeda e preços dos 8 jogos iguais aos da execução local.
- Sem bloqueio nem HTTP 429 em cerca de 60 requisições.
- A falha de lotes grandes se repetiu, então não vem da rede local.

## IsThereAnyDeal: histórico

Script: `spikes/itad_history.py`.

- `POST /lookup/id/shop/61/v1` traduz `app/<appid>` para o ID do ITAD. Funciona sem chave. A loja Steam é a 61.
- `GET /games/history/v2` exige chave, aceita o cabeçalho `ITAD-API-Key` e, sem `since`, traz só 3 meses.
- A resposta é um log de **mudanças de preço**, não uma linha por dia.
- Limite padrão: 1.000 requisições a cada 5 minutos.

```json
{
  "timestamp": "2026-09-25T19:17:47+02:00",
  "shop": {"id": 61, "name": "Steam"},
  "deal": {
    "price": {"amount": 79.99, "amountInt": 7999, "currency": "BRL"},
    "regular": {"amount": 159.99, "amountInt": 15999, "currency": "BRL"},
    "cut": 50
  }
}
```

| Jogo | Registros BR | Registros US | Primeiro registro BR | Último registro BR |
|---|---|---|---|---|
| The Witcher 3 | 259 | 229 | 2014-06-07 | 2026-10-08 |
| Stardew Valley | 122 | 121 | 2016-02-27 | 2026-10-08 |
| Cyberpunk 2077 | 117 | 119 | 2019-06-12 | 2026-10-26 |

- Todos os registros com `country=BR` vieram em BRL.
- O último preço dos 3 jogos é igual ao da Steam no dia do teste.

**Dados anteriores a 2019 não são confiáveis.** Quantidade de preços cheios (`regular`) distintos em BRL por ano:

| Ano | Witcher 3 BRL | Witcher 3 USD | Stardew BRL | Stardew USD |
|---|---|---|---|---|
| 2016 | 22 | 3 | 8 | 1 |
| 2017 | 15 | 1 | 8 | 1 |
| 2018 | 16 | 1 | 7 | 1 |
| 2019 | 1 | 1 | 1 | 1 |

- Até novembro de 2018, o preço cheio em BRL oscila quase a cada registro (7.994, 7.937, 7.998), o que sugere conversão cambial. É uma inferência: a documentação consultada não confirma a causa.
- A partir de 2019, só aparecem reajustes reais, como o Witcher 3 de R$ 79,99 para R$ 129,99 (2023) e para R$ 159,99 (2026).
- A conclusão vem de 3 jogos e deve ser confirmada no catálogo completo na Fase 3.
- Períodos longos sem registro, como 173 dias no Stardew em 2019, podem ser preço estável ou falha de captura. O log não permite distinguir.

## Steam: wishlist e biblioteca

Script: `spikes/steam_profile.py`.

| Endpoint | Resultado | Chave |
|---|---|---|
| `IWishlistService/GetWishlist/v1` | 12 jogos | Não precisa |
| `IPlayerService/GetOwnedGames/v1` | 204 jogos | `STEAM_API_KEY`, aceita no cabeçalho `x-webapi-key` |

- Wishlist: `{"response": {"items": [{"appid": 12200, "priority": 0, "date_added": 1649772663}]}}`. Traz só o appid, sem nome nem preço.
- Biblioteca: `{"response": {"game_count": 204, "games": [{"appid": 10, "name": "Counter-Strike", "playtime_forever": 327}]}}`, com outros campos de tempo de jogo e ícone.
- Nenhum jogo estava nas duas listas.
- Não foram testados perfil privado nem paginação.

## Reprodutibilidade

Os três scripts em `spikes/` reproduzem os resultados principais. A busca binária entre 100 e 200 jogos e a análise por ano do ITAD foram feitas em scripts temporários, fora do repositório. Os jogos em promoção e a amostra da busca mudam com o tempo, então os números exatos podem variar.

## Ajustes propostos no `docs/design.md`

Aprovados pelo Lucas e aplicados em 2026-11-04.

| Seção | Ajuste | Motivo |
|---|---|---|
| 3 e 5 | Incluir todos os jogos da wishlist no seed do catálogo | O app mostra previsões da wishlist, e a busca sob demanda é da V2 |
| 5 | Atualizar o status das fontes de "validar na Fase 0" para validado | Resultados acima |
| 6 | `fct_price_daily` preenche os dias entre registros do ITAD com o último preço conhecido | O ITAD é um log de mudanças |
| 6 | Mudança de `regular` sem desconto é reajuste, não promoção | Evita falsos eventos em `fct_sale_events` |
| 7 | Coleta diária em lotes de 50, ~10 chamadas para ~500 jogos | Mantém distância da faixa de falha, por poucas chamadas a mais que lotes de 100 |
| 7 | Em HTTP 500, dividir o lote ao meio e tentar de novo; registrar falhas de lote em log | A falha derruba o lote inteiro e a causa é desconhecida |
| 7 | Tratar `data: []` como jogo sem preço, sem erro | Formato real da resposta |
| 8 | Usar o histórico do ITAD só a partir de `2019-01-01` | Dados anteriores parecem convertidos; restam quase 8 anos |
| 10 | Marcar as 3 perguntas como respondidas; registrar como riscos o HTTP 500 em lotes grandes e a qualidade do histórico antigo | Resultados acima |
| 11 | Considerar o critério de pronto da Fase 0 cumprido | As respostas passam a constar no design |

Linhas propostas para o "Registro de decisões":

| Data | Decisão | Motivo |
|---|---|---|
| 2026-11-04 | Coleta de preços em lotes de 50, com divisão do lote em caso de HTTP 500 | Lotes grandes falham de forma imprevisível e sem resposta parcial |
| 2026-11-04 | Histórico do ITAD usado a partir de 2019-01-01 | Preços em BRL anteriores oscilam e parecem convertidos |
| 2026-11-04 | Wishlist do autor faz parte do catálogo | Toda linha da tela "Sua wishlist" precisa de previsão na V1 |

## Pendências antes da Fase 1

- Instalar o Python 3.12 na máquina local.
- Criar o token de escrita do Hugging Face e o dataset, começando privado.
- Cadastrar os segredos necessários no GitHub, porque o `.env` local não vai para o Actions.
