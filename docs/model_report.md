# Relatório: modelo vs. baseline

Gerado por `python -m ml.train`.

## Dados

- Treino: até 2024-12-31, 380,502 linhas.
- Teste: 2025-01-31 a 2026-10-05, 202,433 linhas, sendo 149,388 a preço cheio.
- Intervalo de 30 dias entre treino e teste, porque o rótulo olha 30 dias à frente.

## Resultado principal: jogos a preço cheio

Este é o caso de uso central. Um jogo já em promoção tende a continuar nela no dia seguinte, o que inflaria as métricas.

| Abordagem | Acurácia | Precisão | Recall | F1 | Brier | ROC AUC |
|---|---|---|---|---|---|---|
| Sempre sim | 0.667 | 0.667 | 1.000 | 0.800 | 0.333 | 0.500 |
| Baseline sazonal | 0.607 | 0.850 | 0.498 | 0.628 | 0.393 | 0.661 |
| Baseline sazonal calibrado | 0.607 | 0.850 | 0.498 | 0.628 | 0.204 | 0.661 |
| Regressão logística | 0.791 | 0.801 | 0.913 | 0.854 | 0.144 | 0.852 |

- Contra Sempre sim: Brier melhor, F1 melhor.
- Contra Baseline sazonal: Brier melhor, F1 melhor.
- Contra Baseline sazonal calibrado: Brier melhor, F1 melhor.

## Todas as linhas

| Abordagem | Acurácia | Precisão | Recall | F1 | Brier | ROC AUC |
|---|---|---|---|---|---|---|
| Sempre sim | 0.743 | 0.743 | 1.000 | 0.852 | 0.257 | 0.500 |
| Baseline sazonal | 0.625 | 0.905 | 0.553 | 0.687 | 0.375 | 0.692 |
| Baseline sazonal calibrado | 0.625 | 0.905 | 0.553 | 0.687 | 0.178 | 0.692 |
| Regressão logística | 0.835 | 0.851 | 0.942 | 0.894 | 0.116 | 0.883 |

## Jogos fora do treino, a preço cheio

Cenário mais difícil: 137 jogos que o modelo nunca viu no treino.

| Abordagem | Acurácia | Precisão | Recall | F1 | Brier | ROC AUC |
|---|---|---|---|---|---|---|
| Sempre sim | 0.588 | 0.588 | 1.000 | 0.741 | 0.412 | 0.500 |
| Baseline sazonal | 0.623 | 0.754 | 0.533 | 0.625 | 0.377 | 0.643 |
| Baseline sazonal calibrado | 0.623 | 0.754 | 0.533 | 0.625 | 0.230 | 0.643 |
| Regressão logística | 0.736 | 0.782 | 0.764 | 0.773 | 0.171 | 0.821 |

## Por ano, a preço cheio

| Ano | Linhas | Positivos | Sempre sim (acurácia) | Baseline (acurácia) | Regressão logística (acurácia) | Regressão logística (Brier) |
|---|---|---|---|---|---|---|
| 2025 | 75299 | 67.2% | 0.672 | 0.620 | 0.796 | 0.139 |
| 2026 | 74089 | 66.1% | 0.661 | 0.594 | 0.787 | 0.149 |

## Calibração, a preço cheio

| Faixa | Linhas | Previsto | Observado |
|---|---|---|---|
| (-0.001, 0.1] | 9818 | 3.0% | 9.2% |
| (0.1, 0.2] | 2507 | 15.5% | 11.4% |
| (0.2, 0.3] | 5231 | 25.8% | 18.3% |
| (0.3, 0.4] | 8187 | 35.3% | 24.4% |
| (0.4, 0.5] | 10181 | 45.2% | 44.3% |
| (0.5, 0.6] | 18884 | 55.6% | 57.5% |
| (0.6, 0.7] | 24507 | 65.0% | 69.2% |
| (0.7, 0.8] | 17891 | 74.4% | 74.4% |
| (0.8, 0.9] | 9857 | 85.1% | 85.6% |
| (0.9, 1.0] | 42325 | 95.8% | 97.7% |

## Checagem de vazamento

Feita uma vez, com a mesma divisão: ao treinar com rótulos embaralhados, a ROC AUC a preço cheio oscilou entre 0.465 e 0.588 em 6 sementes, com média 0.516. Isso é compatível com o acaso.

## Limitações

- O catálogo veio dos mais vendidos de novembro de 2026, então o modelo só conhece jogos que continuam relevantes hoje. O desempenho em um jogo qualquer tende a ser pior.
- Em jogos sem nenhuma promoção anterior, o histórico quase não ajuda: a ROC AUC cai para 0.642, em 8.807 linhas de 74 jogos.
- Abaixo de 40%, o modelo superestima a chance de promoção, exceto na menor faixa.
- O calendário de 2019 a 2022 foi conferido com os próprios dados. Assume-se que essas datas eram conhecidas com antecedência.
- O preço cheio do ITAD diverge da Steam em 20 de 484 jogos na data da união.
