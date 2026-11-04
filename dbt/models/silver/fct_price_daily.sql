-- Uma linha por jogo e dia. Antes da primeira coleta da Steam, vale o histórico
-- do ITAD, com os dias entre registros preenchidos pelo último preço conhecido.
-- Depois dela, só a Steam: buraco na coleta diária é falha e continua visível.
with steam as (

    select
        app_id,
        price_date,
        collected_at as observed_at,
        currency,
        initial_cents,
        final_cents,
        discount_percent,
        'steam' as price_source,
        false as is_filled
    from {{ ref('stg_steam_prices') }}
    where has_price

),

first_steam as (

    select
        app_id,
        min(price_date) as first_steam_date
    from steam
    group by app_id

),

-- Com várias mudanças no mesmo dia, vale a última.
itad_daily as (

    select *
    from {{ ref('stg_itad_history') }}
    qualify row_number() over (
        partition by app_id, change_date
        order by changed_at desc
    ) = 1

),

itad_spans as (

    select
        itad_daily.*,
        greatest(
            itad_daily.change_date,
            cast('{{ var("itad_history_start_date") }}' as date)
        ) as span_start,
        -- Registro sem deal não vira linha, mas encerra o preenchimento anterior.
        least(
            coalesce(
                lead(itad_daily.change_date) over (
                    partition by itad_daily.app_id
                    order by itad_daily.change_date
                ),
                first_steam.first_steam_date,
                itad_daily.change_date + 1
            ),
            first_steam.first_steam_date
        ) as span_end
    from itad_daily
    left join first_steam
        on itad_daily.app_id = first_steam.app_id

),

itad as (

    select
        app_id,
        cast(
            unnest(range(
                cast(span_start as timestamp),
                cast(span_end as timestamp),
                interval 1 day
            )) as date
        ) as price_date,
        changed_at as observed_at,
        currency,
        initial_cents,
        final_cents,
        discount_percent,
        change_date
    from itad_spans
    where has_deal
        and span_start < span_end

),

unified as (

    select * from steam

    union all

    select
        app_id,
        price_date,
        observed_at,
        currency,
        initial_cents,
        final_cents,
        discount_percent,
        'itad' as price_source,
        price_date <> change_date as is_filled
    from itad

)

select
    unified.*,
    catalog.name as game_name,
    unified.discount_percent > 0 as is_on_sale
from unified
left join {{ ref('catalog') }} as catalog
    on unified.app_id = catalog.app_id
