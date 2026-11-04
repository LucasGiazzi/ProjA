# CLAUDE.md

Instruções permanentes para o Claude Code neste repositório.

## Projeto

**Vale esperar a promoção?** Pipeline de dados ponta a ponta que coleta preços de jogos da Steam (Brasil), prevê a chance de cada jogo entrar em promoção nos próximos 30 dias e compara o resultado com regras simples. É um projeto de estudo e portfólio: repositório público só com código e resultados agregados, app local e dados privados.

A fonte da verdade é `docs/design.md`. Leia antes de qualquer tarefa nova. Se uma decisão do design precisar mudar, proponha a mudança ao Lucas e, aprovada, registre na seção "Registro de decisões" do design.

## Fase atual

**Aguardando a coleta agendada.** As Fases 0, 2, 3 e 4 estão concluídas. O IsThereAnyDeal confirmou por e-mail que o uso no formato de estudo está liberado. A Fase 5 só começa com a confirmação do Lucas.

**Fase 1 em acompanhamento:** a coleta precisa completar 7 dias seguidos sem falha nas execuções agendadas, a partir de 2026-11-05. Não altere `daily.yml`, `ingestion/steam_prices.py` nem `dbt/seeds/catalog.csv` durante a contagem. Se a coleta falhar, ela tem prioridade sobre qualquer outra tarefa.

**Depois da contagem:** atualizar as actions; separar as dependências de ML das da coleta; mover as funções compartilhadas de `steam_prices.py` para um módulo `bronze.py`; juntar coleta e `dbt build` em um só fluxo; revisar o catálogo, buscando dados cadastrais só dos jogos novos.

**Decisões do Lucas em aberto:** licença do código e nome do repositório.

## Stack

- Python 3.12, ambiente virtual `venv`, dependências em `requirements.txt`
- Orquestração: GitHub Actions
- Armazenamento: Hugging Face Datasets (Parquet particionado por data)
- Transformação: dbt com adaptador `dbt-duckdb`
- ML: scikit-learn, LightGBM, MLflow
- App: Streamlit, somente local
- Testes: pytest

Não adicione ferramentas fora desta lista sem aprovação.

## Estrutura de pastas

```
.
├── CLAUDE.md
├── README.md
├── docs/             # design.md e model_report.md
├── spikes/            # testes de viabilidade (Fase 0)
├── ingestion/         # coletores Python, um módulo por fonte
├── dbt/               # projeto dbt: models/staging, models/silver, models/gold, seeds
├── ml/                # dataset, avaliação, treino e relatório
├── app/               # Streamlit (ainda não criado)
├── tests/             # pytest
├── .github/workflows/ # daily.yml (coleta) e ci.yml (testes e dbt)
└── requirements.txt
```

## Regras de engenharia

- **Coletores não transformam dados.** Buscam e gravam na bronze com metadados (`collected_at`, `source`, `http_status`). Toda transformação acontece no dbt.
- **Idempotência:** gravações particionadas por data; reexecutar o mesmo dia sobrescreve, nunca duplica.
- **Bronze é imutável:** nunca editar dado bruto já gravado.
- **`predictions` é append-only:** nunca sobrescrever previsões antigas; o placar depende disso.
- **Sem vazamento no modelo:** features usam apenas dados até a data da linha. Divisão de treino e teste sempre temporal.
- **Limites de requisição:** respeitar ~200 req / 5 min na Steam; backoff em erro 429; falha de um jogo não interrompe a execução.
- **Segredos** só por variável de ambiente (GitHub Secrets, `.env` local no `.gitignore`). Nunca no código ou em logs.
- Funções pequenas, com type hints e docstring curta. Use `logging`, não `print`, fora dos spikes.
- Identificadores de código em inglês; documentação e comentários em português. Exceção: o `README.md` é em inglês.

## Como trabalhar com o Lucas

- Explique o conceito e o porquê antes de mostrar código.
- Pode seguir tarefas da mesma fase em sequência, com commit e push. Pare em barreira, mudança de plano, sugestão, algo que o Lucas precise fazer ou fim de fase.
- Prefira edições cirúrgicas a reescrever arquivos inteiros.
- Não implemente nada de fases futuras nem funcionalidades fora do escopo da V1, mesmo que pareça rápido. Se tiver uma ideia, anote em `docs/design.md` como pergunta em aberto.
- Respostas diretas e concisas.
- Não use travessões (—) em textos e documentação.
