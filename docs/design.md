# Vale esperar a promoção? Documento de design

> Fonte da verdade do projeto. Toda decisão que mudar deve ser registrada aqui, na seção "Registro de decisões".

## 1. Problema

Jogos de PC no Brasil passaram da barreira dos R$ 400, e a Valve alterou as ferramentas de preço regional em 2026. Quem quer um jogo hoje não sabe se compra agora ou espera: a Steam só avisa **depois** que a promoção começa, e ferramentas como SteamDB e IsThereAnyDeal mostram **o que já aconteceu**.

Este projeto responde à pergunta: **"Este jogo vai entrar em promoção nos próximos 30 dias?"**, com uma probabilidade, o desconto típico esperado e um placar público de acertos.

## 2. Diferencial

| | Steam | SteamDB / IsThereAnyDeal | Este projeto |
|---|---|---|---|
| Quando ajuda | Promoção já começou | Consulta ao histórico | Antes de comprar |
| O que entrega | Notificação | Histórico, menor preço, alertas | Probabilidade + desconto típico |
| Prova de qualidade | Não se aplica | Não se aplica | Placar público de acertos |

Casos de uso centrais:
1. O jogo está com preço cheio: comprar agora ou esperar?
2. O jogo entrou numa promoção fraca: aproveitar ou esperar a promoção sazonal?

## 3. Escopo por versão

**V1 (alvo deste documento)**
- Região: somente Brasil (BRL).
- Catálogo de ~500 jogos relevantes, incluindo todos os jogos da wishlist do autor, coletado diariamente.
- Wishlist e biblioteca do próprio autor (perfil público).
- Modelo de previsão de promoção em 30 dias + baseline.
- Placar público de acertos.
- App Streamlit com 3 telas: Sua wishlist, Preço absurdo, Placar.

**V2**
- Qualquer pessoa informa um perfil público e recebe previsões para a própria wishlist.
- Busca de histórico sob demanda para jogos fora do catálogo.

**V3**
- Recomendações a partir da wishlist e da biblioteca.
- Comparação entre regiões (custo em horas de trabalho Brasil vs. outros países), com câmbio do Banco Central.
- Execução opcional dos modelos dbt no Databricks (adaptador `dbt-databricks`).

**Fora de escopo:** compra automática, notificações push, outras lojas além da Steam.

## 4. Arquitetura

```
FONTES                       BRONZE (HF Dataset)        SILVER / GOLD (dbt + DuckDB)          SAÍDA
Steam: preço BR ────────┐
IsThereAnyDeal: hist. ──┼──> JSON bruto → Parquet ──> silver: preço por jogo e dia ─────────> Streamlit
Steam: wishlist ────────┤    particionado por dia     silver: eventos de promoção            (3 telas)
Steam: biblioteca ──────┘                             gold: features do modelo
                                                      gold: previsões (append-only)          MLflow
Seeds no repo: catálogo, calendário de promoções,     gold: placar de acertos                (modelos)
salário mínimo                                        gold: tabelas do app
```

**Orquestração (GitHub Actions)**
- Diário: coleta → bronze → `dbt build` → aplica o modelo vigente → grava previsões.
- Semanal: retreino, registro no MLflow, comparação com o baseline, congelamento das previsões da semana.
- Execução única: carga do histórico via IsThereAnyDeal.

**Por que essa stack:** gratuita, totalmente visível no GitHub e composta por ferramentas comuns em vagas (dbt, MLflow, GitHub Actions). O volume (centenas de jogos, uma linha por dia) não justifica Spark; isso é uma decisão consciente, não uma limitação.

## 5. Fontes de dados

| Fonte | Uso | Acesso | Status |
|---|---|---|---|
| Steam Store `appdetails` | Preço diário BR (inicial, final, desconto) | Público, sem chave, ~200 req / 5 min | Validado na Fase 0: BRL fora do Brasil e consulta agrupada. Endpoint interno, sem garantia de estabilidade |
| IsThereAnyDeal API | Histórico de preços para treino | Chave gratuita | Validado na Fase 0: histórico em BRL, usado a partir de 2019-01-01 |
| Steam `IWishlistService/GetWishlist` | Wishlist do autor | Perfil público | Validado na Fase 0 |
| Steam `IPlayerService/GetOwnedGames` | Biblioteca (esconder jogos já comprados) | Chave da Steam Web API + perfil público | Validado na Fase 0 |
| Seed: catálogo | Lista dos ~500 jogos: pagos mais vendidos da loja Brasil + wishlist do autor | Arquivo no repo, revisão mensal | A montar |
| Seed: calendário de promoções | Datas das promoções sazonais da Steam | Arquivo no repo, manual | A montar |
| Seed: salário mínimo BR | Custo em horas de trabalho | Arquivo no repo | A montar |

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
- `ml_features`: uma linha por jogo e dia, features + rótulo.
- `predictions`: append-only, com `prediction_date` e `model_version`. Nunca sobrescrita.
- `scoreboard`: previsões já resolvidas, com acerto ou erro.
- `app_wishlist`, `app_deals`: tabelas prontas para o app.

**Testes de qualidade (dbt):** unicidade de jogo e dia, preços não negativos, desconto entre 0 e 100, e volume diário mínimo de ~95% das linhas esperadas.

## 7. Coleta

- Coletor em Python separado por fonte; não transforma dados, só busca e grava.
- Tratamento de limite de requisições: espera e nova tentativa com backoff.
- Falha de um jogo não derruba a execução; jogos com falha são registrados em log.
- Segredos (Hugging Face, IsThereAnyDeal, Steam Web API, SteamID) ficam nos Secrets do GitHub.
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

**Baseline obrigatório:** "sim se existe promoção sazonal dentro da janela". O modelo só é considerado útil se superar o baseline, e o resultado é publicado de qualquer forma.

**Validação**
- Dados a partir de 2019-01-01; preços em BRL anteriores a isso não são confiáveis.
- Divisão temporal (treina no passado, testa em meses posteriores). Nunca divisão aleatória.
- Métricas: precisão e recall da classe "promoção", Brier score e curva de calibração.

**Modelos:** regressão logística primeiro; gradient boosting (LightGBM) em seguida. Experimentos registrados no MLflow.

**Saída para o usuário:** Compre agora / Espere / Incerto, com probabilidade e desconto típico. Os limites de cada rótulo são definidos após a calibração.

## 9. App (V1)

Streamlit Community Cloud, lendo apenas a camada gold.

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
| Corte de 2019 no histórico do ITAD veio de apenas 3 jogos | Confirmar no catálogo completo na Fase 3 |
| Catálogo gerado pelos mais vendidos pode favorecer jogos em promoção na data da geração (225 de 497 no primeiro dia) | Avaliar o efeito no modelo na Fase 4 |
| Onde gravar silver e gold para o app ler? O DuckDB do Actions é apagado a cada execução | Decidir antes da Fase 5; candidato natural: Parquet no Hugging Face |
| `dim_games` está na silver, mas não entrou na Fase 2; lançamento, publisher e gêneros exigem nova coleta, e a consulta agrupada só funciona com `price_overview` | Decidir antes da Fase 4, porque as features dependem desses campos |
| Endpoint da Steam pode mudar sem aviso | Testes de volume no dbt alertam; coletor isolado facilita ajuste |
| Onde persistir o MLflow (a máquina do Actions é apagada a cada execução)? | Decidir na Fase 4: MLflow hospedado gratuito (ex.: DagsHub) ou diretório de runs salvo no Hugging Face |
| Termos de uso para publicar o dataset | Revisar termos da Steam e do ITAD antes de tornar o dataset público; começar privado |

## 11. Fases de execução

| Fase | Entrega | Critério de pronto |
|---|---|---|
| 0. Testes de viabilidade | Scripts em `spikes/` respondendo às 3 perguntas da seção 10 | Cumprido em 2026-11-04: respostas registradas neste documento e em `spikes/FINDINGS.md` |
| 1. Coleta diária | Coletor Steam BR + workflow diário gravando bronze no HF | 7 dias seguidos sem falha |
| 2. Silver e gold básicos | Projeto dbt com `stg`, `fct_price_daily`, `fct_sale_events`, testes | Cumprido em 2026-11-04: `dbt build` verde no Actions |
| 3. Histórico | Carga única do ITAD integrada à silver | Histórico unificado por jogo |
| 4. Modelo | Features, baseline, logística, MLflow | Relatório modelo vs. baseline |
| 5. Previsões e placar | Previsões diárias append-only + placar | Primeira previsão resolvida |
| 6. App V1 | 3 telas no Streamlit Cloud | Link público funcionando |
| 7. V2 | Perfil de qualquer usuário | Fora da V1 |

Regra: não iniciar uma fase sem a anterior cumprir o critério de pronto, exceto a Fase 1, que deve continuar rodando em paralelo a todas as outras. Exceção aprovada: as Fases 2 e 3 começaram durante a contagem de 7 dias da Fase 1, que ainda precisa cumprir seu critério.

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
