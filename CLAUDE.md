# CLAUDE.md

Instruções permanentes para o Claude Code neste repositório.

## Projeto

**Vale esperar a promoção?** Pipeline de dados ponta a ponta que coleta preços de jogos da Steam (Brasil), prevê a chance de cada jogo entrar em promoção nos próximos 30 dias e mostra o resultado num app Streamlit, com placar público de acertos.

A fonte da verdade é `docs/design.md`. Leia antes de qualquer tarefa nova. Se uma decisão do design precisar mudar, proponha a mudança ao Lucas e, aprovada, registre na seção "Registro de decisões" do design.

## Fase atual

**Fase 1: coleta diária.** A Fase 0 terminou e os resultados estão em `spikes/FINDINGS.md`. Nada de dbt, modelo ou app ainda.

Tarefas, uma por vez, nesta ordem:
1. Ambiente: `venv` com Python 3.12 e `requirements.txt`.
2. `ingestion/build_catalog.py`: gerar `dbt/seeds/catalog.csv` com os ~500 jogos pagos mais vendidos da loja Brasil, somando a wishlist do Lucas.
3. `ingestion/steam_prices.py`: coletar o preço do catálogo em lotes de 50 e gravar a bronze no Hugging Face, particionada por data, com testes em `tests/`.
4. `.github/workflows/daily.yml`: rodar a coleta todo dia, com `workflow_dispatch` para testes.
5. Acompanhar até completar 7 dias seguidos sem falha.

Ao fim da Fase 1, pare e peça confirmação antes da Fase 2. A coleta continua rodando nas fases seguintes.

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
