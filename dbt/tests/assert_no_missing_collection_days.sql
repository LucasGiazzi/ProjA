-- Avisa sobre dias sem coleta. Só avisa: um dia perdido não volta, e um erro
-- travaria todo build seguinte.
{{ config(severity='warn') }}

with collection_days as (

    select distinct price_date
    from {{ ref('stg_steam_prices') }}

),

with_previous as (

    select
        price_date,
        lag(price_date) over (order by price_date) as previous_date
    from collection_days

)

select
    previous_date,
    price_date,
    date_diff('day', previous_date, price_date) - 1 as missing_days
from with_previous
where date_diff('day', previous_date, price_date) > 1
