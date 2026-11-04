# CLAUDE.md

Instruções permanentes para o Claude Code neste repositório.

## Projeto

**Vale esperar a promoção?** Pipeline de dados ponta a ponta que coleta preços de jogos da Steam (Brasil), prevê a chance de cada jogo entrar em promoção nos próximos 30 dias e mostra o resultado num app Streamlit, com placar público de acertos.

A fonte da verdade é `docs/design.md`. Leia antes de qualquer tarefa nova. Se uma decisão do design precisar mudar, proponha a mudança ao Lucas e, aprovada, registre na seção "Registro de decisões" do design.

## Fase atual

**Fase 2: silver e gold básicos**, em paralelo à contagem da Fase 1. Nada de modelo ou app ainda.

**Fase 1 em acompanhamento:** a coleta precisa completar 7 dias seguidos sem falha nas execuções agendadas, a partir de 2026-11-05. Não altere `daily.yml` nem `dbt/seeds/catalog.csv` durante a contagem.

Tarefas da Fase 2, uma por vez, nesta ordem:
1. Projeto dbt em `dbt/`: `dbt-duckdb`, perfil, seed do catálogo e fonte da bronze no Hugging Face.
2. `stg_steam_prices`: extrair e tipar os campos de `raw_json`, com testes.
3. `fct_price_daily`: uma linha por jogo e dia, com testes de qualidade.
4. `fct_sale_events`: cada promoção com início, fim e desconto máximo.
5. `.github/workflows/dbt.yml`: `dbt build` no Actions em workflow separado, com `workflow_dispatch`.

Ao fim da Fase 2, pare e peça confirmação antes da Fase 3.

## Stack

- Python 3.12, ambiente virtual `venv`, dependências em `requirements.txt`
- Orquestração: GitHub Actions
- Armazenamento: Hugging Face Datasets (Parquet particionado por data)
- Transformação: dbt com adaptador `dbt-duckdb`
- ML: scikit-learn, LightGBM, MLflow
- App: Streamlit (Streamlit Community Cloud)
- Testes: pytest

Não adicione ferramentas fora desta lista sem aprovação.

## Estrutura de pastas

```
.
├── CLAUDE.md
├── README.md
├── docs/design.md
├── spikes/            # testes de viabilidade (Fase 0)
├── ingestion/         # coletores Python, um módulo por fonte
├── dbt/               # projeto dbt: models/staging, models/silver, models/gold, seeds
├── ml/                # features, treino, previsão
├── app/               # Streamlit
├── tests/             # pytest
├── .github/workflows/
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
- Identificadores de código em inglês; documentação e comentários em português.

## Como trabalhar com o Lucas

- Explique o conceito e o porquê antes de mostrar código.
- Uma tarefa por vez. Ao terminar, mostre o resultado e espere confirmação antes de seguir.
- Prefira edições cirúrgicas a reescrever arquivos inteiros.
- Não implemente nada de fases futuras nem funcionalidades fora do escopo da V1, mesmo que pareça rápido. Se tiver uma ideia, anote em `docs/design.md` como pergunta em aberto.
- Respostas diretas e concisas.
- Não use travessões (—) em textos e documentação.
