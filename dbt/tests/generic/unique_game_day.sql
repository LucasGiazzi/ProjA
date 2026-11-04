-- Falha se um jogo aparecer mais de uma vez no mesmo dia.
{% test unique_game_day(model) %}

select
    app_id,
    price_date,
    count(*) as rows_found
from {{ model }}
group by app_id, price_date
having count(*) > 1

{% endtest %}
