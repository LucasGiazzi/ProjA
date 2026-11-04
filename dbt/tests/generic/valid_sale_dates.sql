-- Falha se uma promoção terminar antes de começar ou se sobrepuser à seguinte.
{% test valid_sale_dates(model) %}

with ordered as (

    select
        *,
        lead(start_date) over (order by start_date) as next_start_date
    from {{ model }}

)

select *
from ordered
where last_sale_date < start_date
    or last_sale_date >= next_start_date

{% endtest %}
