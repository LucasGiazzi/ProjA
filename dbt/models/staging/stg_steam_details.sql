-- Extrai e tipa os dados cadastrais, usando a carga mais recente de cada jogo.
with bronze as (

    select
        app_id,
        raw_json,
        cast("date" as date) as load_date
    from {{ source('bronze', 'steam_details') }}
    where raw_json is not null

),

latest_load as (

    select *
    from bronze
    qualify load_date = max(load_date) over (partition by app_id)

)

select
    app_id,
    load_date,
    coalesce(cast(raw_json ->> '$.success' as boolean), false) as is_success,
    raw_json ->> '$.data.type' as app_type,
    raw_json ->> '$.data.name' as store_name,
    cast(raw_json ->> '$.data.is_free' as boolean) as is_free,
    cast(raw_json ->> '$.data.release_date.coming_soon' as boolean) as is_coming_soon,
    raw_json ->> '$.data.release_date.date' as release_date_text,
    -- Datas imprecisas, como "Q1 2027", ficam nulas.
    cast(try_strptime(raw_json ->> '$.data.release_date.date', '%d %b, %Y') as date) as release_date,
    raw_json ->> '$.data.publishers[0]' as publisher,
    raw_json ->> '$.data.developers[0]' as developer,
    json_extract_string(raw_json, '$.data.genres[*].description') as genres
from latest_load
