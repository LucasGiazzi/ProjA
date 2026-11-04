-- Uma linha por jogo do catálogo. O preço base é o mais recente, então serve
-- para o app, não para features: isso seria vazamento no modelo.
with latest_price as (

    select
        app_id,
        initial_cents as base_price_cents
    from {{ ref('fct_price_daily') }}
    qualify price_date = max(price_date) over (partition by app_id)

)

select
    catalog.app_id,
    catalog.name as game_name,
    catalog.source as catalog_source,
    details.app_type,
    details.is_free,
    details.is_coming_soon,
    details.release_date,
    details.publisher,
    details.developer,
    details.genres,
    latest_price.base_price_cents
from {{ ref('catalog') }} as catalog
left join {{ ref('stg_steam_details') }} as details
    on catalog.app_id = details.app_id
left join latest_price
    on catalog.app_id = latest_price.app_id
