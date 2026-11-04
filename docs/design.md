# Vale esperar a promoção? Documento de design

> Fonte da verdade do projeto. Toda decisão que mudar deve ser registrada aqui, na seção "Registro de decisões".

## 1. Problema

Jogos de PC no Brasil passaram da barreira dos R$ 400, e a Valve alterou as ferramentas de preço regional em 2026. Quem quer um jogo hoje não sabe se compra agora ou espera: a Steam só avisa **depois** que a promoção começa, e as ferramentas de preço focam sobretudo em histórico, alertas e calendário.

Este projeto responde à pergunta: **"Este jogo vai entrar em promoção nos próximos 30 dias?"**, com uma probabilidade, o desconto típico esperado e um placar de acertos.

**Natureza do projeto:** estudo e portfólio, sem fins comerciais. O código e os resultados agregados ficam no repositório público. O app roda localmente, e os dados coletados ficam em dataset privado.

## 2. Contexto

O projeto serve para praticar o ciclo completo de dados com um tema de interesse pessoal, não para substituir ferramentas existentes. A Steam e o IsThereAnyDeal são fontes de dados deste estudo.

A ideia não é inédita: há ferramentas com recomendações de comprar ou esperar, como o steamAF, além de calendários de promoções e estudos acadêmicos. O foco aqui é o método: previsão por jogo no mercado brasileiro, comparada com regras simples em dados que o modelo não viu.

Casos de uso centrais:
1. O jogo está com preço cheio: comprar agora ou esperar?
2. O jogo entrou numa promoção fraca: aproveitar ou esperar a promoção sazonal?

## 3. Escopo por versão

**V1 (alvo deste documento)**
- Região: somente Brasil (BRL).
- Catálogo de ~500 jogos relevantes, incluindo todos os jogos da wishlist do autor, coletado diariamente.
- Wishlist e biblioteca do próprio autor (perfil público).
- Modelo de previsão de promoção em 30 dias + baseline.
- Placar de acertos, publicado no repositório só com resultados agregados.
- App Streamlit local, sem deploy público, com 3 telas: Sua wishlist, Preço absurdo, Placar.

**V2** (suspensa: depende de um app público, fora dos planos)
- Qualquer pessoa informa um perfil público e recebe previsões para a própria wishlist.
- Busca de histórico sob demanda para jogos fora do catálogo.

**V3**
- Recomendações a partir da wishlist e da biblioteca.
- Comparação entre regiões (custo em horas de trabalho Brasil vs. outros países), com câmbio do Banco Central.
- Execução opcional dos modelos dbt no Databricks (adaptador `dbt-databricks`).

**Fora de escopo:** compra automática, notificações push, outras lojas além da Steam, app público e publicação dos dados coletados.

## 4. Arquitetura

```
FONTES                       BRONZE (HF Dataset)        SILVER / GOLD (dbt + DuckDB)          SAÍDA
Steam: preço BR ────────┐
IsThereAnyDeal: hist. ──┼──> JSON bruto → Parquet ──> silver: preço por jogo e dia ─────────> Streamlit
Steam: dados cadastrais ┤    particionado por dia     silver: eventos de promoção            (3 telas)
Steam: wishlist ────────┤                             silver: dados dos jogos
Steam: biblioteca ──────┘                             gold: features do modelo
                                                      gold: previsões (append-only)          MLflow
Seeds no repo: catálogo, calendário de promoções      gold: placar de acertos                (modelos)
                                                      gold: tabelas do app
```

**Orquestração hoje (GitHub Actions)**
- `daily.yml`, todo dia às 09:07 UTC: testes e coleta de preços para a bronze.
- `ci.yml`, a cada push: testes e `dbt build`.
- Cargas únicas, locais: histórico do ITAD e dados cadastrais da Steam. Treino também local.

**Orquestração planejada**
- Diário: coleta → bronze → `dbt build` → aplica o modelo vigente → grava previsões. Juntar os workflows só depois da contagem da Fase 1.
- Semanal: retreino, registro no MLflow, comparação com o baseline, congelamento das previsões da semana.

**Por que essa stack:** gratuita, totalmente visível no GitHub e composta por ferramentas comuns em vagas (dbt, MLflow, GitHub Actions). O volume (centenas de jogos, uma linha por dia) não justifica Spark; isso é uma decisão consciente, não uma limitação.

## 5. Fontes de dados

| Fonte | Uso | Acesso | Status |
|---|---|---|---|
| Steam Store `appdetails` | Preço diário BR (inicial, final, desconto) | Público, sem chave, ~200 req / 5 min | Validado na Fase 0: BRL fora do Brasil e consulta agrupada. Endpoint interno, sem garantia de estabilidade |
| IsThereAnyDeal API | Histórico de preços para treino | Chave gratuita | Validado na Fase 0: histórico em BRL, usado a partir de 2019-01-01 |
| Steam Store `appdetails`, dados cadastrais | Lançamento, publisher, gêneros | Público, uma chamada por jogo | Carga única feita na Fase 4 |
| Steam `IWishlistService/GetWishlist` | Wishlist do autor | Perfil público | Validado na Fase 0. Usada no catálogo; coleta para a bronze ainda não implementada |
| Steam `IPlayerService/GetOwnedGames` | Biblioteca (esconder jogos já comprados) | Chave da Steam Web API + perfil público | Validado na Fase 0. Coleta para a bronze ainda não implementada |
| Seed: catálogo | Lista dos ~500 jogos: pagos mais vendidos da loja Brasil + wishlist do autor | Arquivo no repo, revisão mensal | Pronto: 500 jogos |
| Seed: calendário de promoções | Datas das promoções sazonais da Steam | Arquivo no repo, manual | Pronto: 38 eventos, de 2019 a 2027 |
| Seed: salário mínimo BR | Custo em horas de trabalho | Arquivo no repo | Fora da V1: só para a comparação regional da V3 |

## 6. Camadas de dados

**Bronze** (Hugging Face Datasets, Parquet particionado por data)
- Resposta da fonte como veio, mais metadados: `collected_at`, `source`, `http_status`.
- Imutável e idempotente: reexecutar o mesmo dia sobrescreve a partição do dia, nunca duplica.

**Silver** (dbt)
- `stg_*`: limpeza e tipagem de cada fonte.
- `fct_price_daily`: uma linha por jogo e dia, unindo histórico do ITAD (a partir de 2019-01-01) e coleta diária da Steam. O ITAD é um log de mudanças de preço, então os dias entre registros são preenchidos com o último preço conhecido.
- `fct_sale_events`: cada promoção com início, fim e desconto máximo. Mudança de preço cheio sem desconto é reajuste, não promoção.
- `dim_games`: dados cadastrais do jogo (lançamento, publisher, gêneros, preço base).

**Gold** (dbt + Python)
- `ml_features`: uma linha por jogo e dia, features + rótulo. Pronta.
- `predictions` (planejada): append-only, com `prediction_date` e `model_version`. Nunca sobrescrita.
- `scoreboard` (planejada): previsões já resolvidas, com acerto ou erro.
- `app_wishlist`, `app_deals` (planejadas): tabelas prontas para o app.

**Testes de qualidade (dbt):** unicidade de jogo e dia, preços não negativos, desconto entre 0 e 100, volume diário mínimo de ~95% das linhas esperadas e aviso de dia sem coleta. Testes unitários do dbt cobrem as regras de negócio, incluindo a ausência de vazamento.

## 7. Coleta

- Coletor em Python separado por fonte; não transforma dados, só busca e grava.
- Tratamento de limite de requisições: espera e nova tentativa com backoff.
- Falha de um jogo não derruba a execução; jogos com falha são registrados em log.
- Segredos ficam nos Secrets do GitHub (`HF_TOKEN`, `HF_DATASET_REPO`) ou só no `.env` local, para as cargas que rodam na máquina do autor (ITAD, Steam Web API, SteamID).
- Consulta agrupada em lotes de 50: ~10 chamadas por dia para ~500 jogos.
- HTTP 500 em um lote: dividir o lote ao meio e tentar de novo, registrando a falha em log. Lotes grandes podem falhar sem resposta parcial.
- `data: []` na resposta da Steam significa jogo sem preço, não erro.

**Prioridade de calendário:** a coleta diária deve entrar em produção o quanto antes. Cada dia sem coleta é um dia de dado real perdido para o placar.

## 8. Modelo

**Pergunta:** o jogo terá desconto nos próximos 30 dias? Classificação binária com saída em probabilidade.

**Grão:** uma linha por jogo e dia. Features usam apenas informação disponível até aquele dia; o rótulo olha os 30 dias seguintes.

**Features iniciais**
- Histórico: dias desde a última promoção, intervalo médio entre promoções, número de promoções nos últimos 12 meses, maior desconto já dado, desconto típico.
- Calendário: dias até a próxima promoção sazonal da Steam, mês.
- Jogo: dias desde o lançamento, preço base, taxa histórica de promoção da publisher.
- Estado atual: está em promoção hoje? Desconto atual vs. desconto típico.

**Baseline obrigatório:** "sim se existe promoção sazonal dentro da janela". O modelo só é considerado útil se superar o baseline, e o resultado é publicado de qualquer forma. A regra ingênua "sempre sim" também entra na comparação, porque acerta mais que o baseline.

**Validação**
- Dados a partir de 2019-01-01; preços em BRL anteriores a isso não são confiáveis.
- Divisão temporal (treina no passado, testa em meses posteriores). Nunca divisão aleatória. Treino até 2024-12-31; teste de 2025-01-31 a 2026-10-05.
- Métricas: precisão e recall da classe "promoção", Brier score e curva de calibração, com resultado principal nos jogos a preço cheio. Jogo já em promoção tende a continuar nela, o que infla as métricas.
- Intervalo de 30 dias entre treino e teste, porque o rótulo olha 30 dias à frente.

**Modelos:** regressão logística primeiro; gradient boosting (LightGBM) em seguida. Experimentos registrados no MLflow local.

**Resultado atual:** a regressão logística acerta 79,1% a preço cheio, contra 60,7% do baseline e 66,7% do "sempre sim". Detalhes em `docs/model_report.md`. LightGBM ainda não testado.

**Saída para o usuário:** Compre agora / Espere / Incerto, com probabilidade e desconto típico. Os limites de cada rótulo são definidos após a calibração.

## 9. App (V1)

Streamlit local, lendo apenas a camada gold, sem deploy público. As telas abaixo dependem da resposta do ITAD sobre o uso dos dados.

1. **Sua wishlist:** preço atual, menor preço histórico, probabilidade em 30 dias, rótulo e desconto típico. Jogos da biblioteca ficam ocultos.
2. **Preço absurdo:** jogos do catálogo no menor preço histórico ou perto dele, ordenados por relevância.
3. **Placar:** taxa de acerto ao longo do tempo, modelo vs. baseline, curva de calibração.

## 10. Riscos e perguntas em aberto

| Risco / pergunta | Como resolver |
|---|---|
| Steam devolve BRL quando a chamada vem de servidor do GitHub (fora do Brasil)? | Respondido: sim, testado com runner nos EUA (`spikes/FINDINGS.md`) |
| Consulta agrupada de vários jogos funciona? | Respondido: sim, sem máximo fixo; adotados lotes de 50 (`spikes/FINDINGS.md`) |
| Quanto histórico o ITAD fornece, e em BRL? | Respondido: desde o lançamento, em BRL, confiável a partir de 2019 (`spikes/FINDINGS.md`) |
| Steam devolve HTTP 500 em alguns lotes grandes, por causa desconhecida | Lotes de 50, divisão do lote em caso de falha e falhas registradas em log |
| Corte de 2019 no histórico do ITAD veio de apenas 3 jogos | Respondido: confirmado no catálogo; mudanças de preço cheio menores que 3% caem de 147 em dez/2018 para 4 em jan/2019 |
| Preço cheio do ITAD diverge da Steam em 20 de 484 jogos na data da união, por causa desconhecida | Afeta nível de preço, não o rótulo de promoção. Registrado como limitação em `docs/model_report.md` |
| 10 jogos do catálogo não têm histórico no ITAD | Só entram no treino depois de 30 dias de coleta diária |
| Histórico desigual: 130 jogos com promoção iniciada em 2019 e 447 em 2026 | Reflete sobretudo jogos mais novos no catálogo. O teste separa jogos fora do treino, com 73,6% de acerto |
| Catálogo contém itens que parecem não ser jogos comuns, como EA Play e iRacing | Avaliar na revisão do catálogo, depois da contagem da Fase 1. O campo `type` da Steam não separa esses casos |
| Catálogo gerado pelos mais vendidos pode favorecer jogos em promoção na data da geração (225 de 497 no primeiro dia) | Registrado como limitação. Medir o efeito na revisão do catálogo |
| Onde gravar previsões e gold? O DuckDB do Actions é apagado a cada execução | Decidir antes da Fase 5; candidato natural: Parquet no dataset privado do Hugging Face |
| `dim_games` exige uma chamada por jogo, porque a consulta agrupada só aceita `price_overview` | Resolvido na Fase 4 com carga única; na revisão do catálogo, buscar só os jogos novos |
| Endpoint da Steam pode mudar sem aviso | Testes de volume no dbt alertam; coletor isolado facilita ajuste |
| Onde persistir o MLflow (a máquina do Actions é apagada a cada execução)? | Decidir na Fase 5, se o retreino for automático: MLflow hospedado gratuito (ex.: DagsHub) ou runs salvos no Hugging Face |
| `daily.yml` instala as dependências de ML e roda todos os testes antes de coletar, então uma falha alheia à coleta a impediria | `ci.yml` testa o mesmo ambiente a cada push. Separar as dependências e os passos depois da contagem da Fase 1 |
| `itad_history.py` e `steam_details.py` importam funções de `steam_prices.py` | Mover para um módulo `bronze.py` depois da contagem da Fase 1 |
| Termos de uso para publicar o dataset | Resolvido: o dataset fica privado. Termos lidos em 2026-11-04; os da Steam licenciam a distribuição a usuários finais pelo app, sem cláusula sobre datasets públicos |
| Termos do ITAD proíbem app que possa ser visto como concorrente, e uso privado pede contato prévio | E-mail enviado pelo autor em 2026-11-04, aguardando resposta. Sem app público, o risco de concorrência cai. Fases 5 e 6 em espera até lá |

## 11. Fases de execução

| Fase | Entrega | Critério de pronto |
|---|---|---|
| 0. Testes de viabilidade | Scripts em `spikes/` respondendo às 3 perguntas da seção 10 | Cumprido em 2026-11-04: respostas registradas neste documento e em `spikes/FINDINGS.md` |
| 1. Coleta diária | Coletor Steam BR + workflow diário gravando bronze no HF | 7 dias seguidos sem falha |
| 2. Silver e gold básicos | Projeto dbt com `stg`, `fct_price_daily`, `fct_sale_events`, testes | Cumprido em 2026-11-04: `dbt build` verde no Actions |
| 3. Histórico | Carga única do ITAD integrada à silver | Cumprido em 2026-11-04: histórico unificado por jogo, com `dbt build` verde no Actions |
| 4. Modelo | Features, baseline, logística, MLflow | Cumprido em 2026-11-04: `docs/model_report.md`. Modelo superou o baseline e a regra "sempre sim" |
| 5. Previsões e placar | Previsões diárias append-only + placar agregado no repositório | Em espera pela resposta do ITAD. Critério: primeira previsão resolvida |
| 6. App V1 | 3 telas no Streamlit local | Em espera pela resposta do ITAD. Critério: app funcionando localmente |
| 7. V2 | Perfil de qualquer usuário | Suspensa |

Regra: não iniciar uma fase sem a anterior cumprir o critério de pronto, exceto a Fase 1, que deve continuar rodando em paralelo a todas as outras. Exceção aprovada: as Fases 2, 3 e 4 começaram durante a contagem de 7 dias da Fase 1, que ainda precisa cumprir seu critério.

## 12. Registro de decisões

| Data | Decisão | Motivo |
|---|---|---|
| 2026-11-04 | Tema: previsão de promoções da Steam | Problema atual, ligado a interesse pessoal, com diferencial preditivo |
| 2026-11-04 | V1 apenas Brasil | A decisão de compra do usuário é no Brasil; reduz consultas em 5x |
| 2026-11-04 | Stack: GitHub Actions + DuckDB + dbt + MLflow + Streamlit | Gratuita, visível no GitHub, ferramentas de mercado |
| 2026-11-04 | Databricks fora da V1 | Free Edition restringe acesso à internet de saída, não tem SLA e o workspace é privado |
| 2026-11-04 | Armazenamento no Hugging Face Datasets | Papel de object storage, gratuito, permite publicar o dataset |
| 2026-11-04 | Janela de previsão de 30 dias | Casa com a decisão real e gera exemplos positivos suficientes |
| 2026-11-04 | Coleta ampla, vitrine enxuta | O modelo precisa de muitos exemplos; o app mostra só o relevante |
| 2026-11-04 | Recomendações na V3 | Segundo modelo com outra lógica; evita inflar o escopo da V1 |
| 2026-11-04 | Coleta de preços em lotes de 50, com divisão do lote em caso de HTTP 500 | Lotes grandes falham de forma imprevisível e sem resposta parcial |
| 2026-11-04 | Histórico do ITAD usado a partir de 2019-01-01 | Preços em BRL anteriores oscilam e parecem convertidos |
| 2026-11-04 | Wishlist do autor faz parte do catálogo | Toda linha da tela "Sua wishlist" precisa de previsão na V1 |
| 2026-11-04 | Catálogo: jogos pagos mais vendidos da loja Brasil + wishlist; gratuitos fora | Critério simples e reproduzível; jogo gratuito não entra em promoção. Favorece títulos populares, aceitável na V1 |
| 2026-11-04 | Fase 2 iniciada durante a contagem de 7 dias da Fase 1 | O dbt só lê a bronze e não interfere na coleta; evita ficar parado até 2026-11-11 |
| 2026-11-04 | Fase 3 iniciada durante a contagem de 7 dias da Fase 1 | A carga do ITAD é única, grava em outra pasta da bronze e não toca na coleta diária |
| 2026-11-04 | Carga do ITAD roda uma vez, localmente | Execução única, sem necessidade de mais um secret no GitHub |
| 2026-11-04 | Nos dias com as duas fontes, vale o preço da Steam; preenchimento só no período do ITAD | A Steam é a medição direta, e buraco na coleta diária deve continuar visível como falha |
| 2026-11-04 | Fase 4 iniciada durante a contagem de 7 dias da Fase 1 | O modelo treina com o histórico já validado e não toca na coleta; falha na coleta tem prioridade |
| 2026-11-04 | MLflow local na Fase 4; persistência decidida na Fase 5 | A persistência só importa quando o retreino for automático |
| 2026-11-04 | Resultado principal do modelo medido em jogos a preço cheio, comparando também com "sempre sim" | É o caso de uso central, e a regra ingênua acerta mais que o baseline |
| 2026-11-04 | README em inglês | É o padrão em portfólios técnicos; o restante da documentação segue em português |
| 2026-11-04 | Projeto de estudo: sem app público nem dataset público. Substitui a publicação prevista nas decisões anteriores | Decisão do Lucas; o objetivo é aprendizado e portfólio |
| 2026-11-04 | Repositório público só com código e resultados agregados; app local | Mantém o portfólio visível sem publicar os dados coletados, como informado ao ITAD |
| 2026-11-04 | `ci.yml` substitui `dbt.yml` e passa a rodar o pytest; `spike.yml` removido | Testa no Linux o mesmo ambiente da coleta, sem alterar `daily.yml` |
