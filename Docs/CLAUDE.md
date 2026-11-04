# CLAUDE.md

Instruções permanentes para o Claude Code neste repositório.

## Projeto

**Vale esperar a promoção?** Pipeline de dados ponta a ponta que coleta preços de jogos da Steam (Brasil), prevê a chance de cada jogo entrar em promoção nos próximos 30 dias e mostra o resultado num app Streamlit, com placar público de acertos.

A fonte da verdade é `docs/design.md`. Leia antes de qualquer tarefa nova. Se uma decisão do design precisar mudar, proponha a mudança ao Lucas e, aprovada, registre na seção "Registro de decisões" do design.

## Fase atual

**Fase 0: testes de viabilidade.** Nada de pipeline, dbt ou modelo ainda.

Tarefas, uma por vez, nesta ordem:
1. `spikes/steam_prices.py`: consultar `https://store.steampowered.com/api/appdetails` com `cc=br` e `filters=price_overview` para 5 appids conhecidos. Confirmar que a moeda é BRL e registrar o formato da resposta.
2. No mesmo script, testar a consulta agrupada (`appids=a,b,c` com `filters=price_overview`). Registrar se funciona e qual o máximo por chamada.
3. Criar `.github/workflows/spike.yml` com `workflow_dispatch` rodando o script do item 1 no GitHub Actions. Confirmar que a moeda continua BRL vindo de um servidor fora do Brasil.
4. `spikes/itad_history.py`: buscar o histórico de preço de 3 jogos na API do IsThereAnyDeal. Registrar profundidade do histórico e se há preço em BRL na loja Steam.
5. `spikes/steam_profile.py`: buscar a wishlist (`IWishlistService/GetWishlist/v1`) e a biblioteca (`IPlayerService/GetOwnedGames/v1`) do perfil do Lucas.
6. Registrar as respostas em `spikes/FINDINGS.md` e propor os ajustes no `docs/design.md`.

Ao fim da Fase 0, pare e peça confirmação antes da Fase 1.

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
