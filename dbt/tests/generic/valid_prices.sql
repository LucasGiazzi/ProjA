-- Falha se houver campo de preço vazio ou valor fora da faixa válida.
{% test valid_prices(model) %}

select *
from {{ model }}
where currency is null
    or initial_cents is null
    or final_cents is null
    or discount_percent is null
    or initial_cents < 0
    or final_cents < 0
    or final_cents > initial_cents
    or discount_percent not between 0 and 100

{% endtest %}
