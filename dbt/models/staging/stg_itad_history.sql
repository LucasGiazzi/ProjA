-- Abre o histórico do ITAD em uma linha por mudança de preço, usando a carga
-- mais recente de cada jogo. Sem corte de data: isso fica no fct_price_daily.
with bronze as (

    select
        app_id,
        itad_id,
        raw_json,
        cast("date" as date) as load_date
    from {{ source('bronze', 'itad_history') }}
    where raw_json is not null

),

latest_load as (

    select *
    from bronze
    qualify load_date = max(load_date) over (partition by app_id)

),

records as (

    select
        app_id,
        itad_id,
        load_date,
        unnest(cast(raw_json as json[])) as record
    from latest_load

),

typed as (

    select
        app_id,
        itad_id,
        load_date,
        cast(record ->> '$.timestamp' as timestamptz) as changed_at,
        (record -> '$.deal.price') is not null as has_deal,
        record ->> '$.deal.price.currency' as currency,
        cast(record ->> '$.deal.regular.amountInt' as integer) as initial_cents,
        cast(record ->> '$.deal.price.amountInt' as integer) as final_cents,
        cast(record ->> '$.deal.cut' as integer) as discount_percent
    from records

)

select
    *,
    -- Data em UTC, igual à coleta diária.
    cast(timezone('UTC', changed_at) as date) as change_date
from typed
