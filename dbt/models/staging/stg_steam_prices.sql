-- Extrai e tipa os campos da resposta da Steam. Sem regra de negócio.
-- Uma linha por jogo e dia; preços em centavos, como vieram.
with bronze as (

    select
        app_id,
        raw_json,
        collected_at,
        source,
        http_status,
        cast("date" as date) as price_date
    from {{ source('bronze', 'steam_prices') }}

)

select
    app_id,
    price_date,
    collected_at,
    source,
    http_status,
    raw_json is not null as has_response,
    coalesce(cast(raw_json ->> '$.success' as boolean), false) as is_success,
    -- Jogo sem preço vem com "data": [], então o caminho abaixo fica nulo.
    (raw_json -> '$.data.price_overview') is not null as has_price,
    raw_json ->> '$.data.price_overview.currency' as currency,
    cast(raw_json ->> '$.data.price_overview.initial' as integer) as initial_cents,
    cast(raw_json ->> '$.data.price_overview.final' as integer) as final_cents,
    cast(raw_json ->> '$.data.price_overview.discount_percent' as integer) as discount_percent
from bronze
