-- Falha se um jogo aparecer mais de uma vez no mesmo dia.
select
    app_id,
    price_date,
    count(*) as rows_found
from {{ ref('stg_steam_prices') }}
group by app_id, price_date
having count(*) > 1
