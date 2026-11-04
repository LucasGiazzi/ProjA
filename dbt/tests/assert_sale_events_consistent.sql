-- Falha se as datas ou o desconto de uma promoção forem incoerentes.
select *
from {{ ref('fct_sale_events') }}
where (is_open and end_date is not null)
    or (not is_open and end_date is null)
    or end_date < start_date
    or max_discount_percent not between 1 and 100
