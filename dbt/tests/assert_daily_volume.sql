-- Falha se a Steam respondeu para menos jogos que o mínimo em algum dia.
-- Compara com as linhas do próprio dia, porque o catálogo muda nas revisões.
select
    price_date,
    count(*) as expected_games,
    count_if(has_response) as collected_games
from {{ ref('stg_steam_prices') }}
group by price_date
having count_if(has_response) < count(*) * {{ var('min_daily_volume_rate') }}
