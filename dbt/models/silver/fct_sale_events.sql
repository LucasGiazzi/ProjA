-- Uma linha por promoção. Dias de desconto entre dois preços cheios observados
-- formam uma promoção; dia sem coleta não gera linha, então não a divide.
with daily as (

    select
        app_id,
        price_date,
        final_cents,
        discount_percent,
        is_on_sale,
        -- Cada preço cheio observado abre um novo grupo.
        count_if(not is_on_sale) over (
            partition by app_id
            order by price_date
        ) as full_price_days_seen
    from {{ ref('fct_price_daily') }}

),

latest as (

    select
        app_id,
        max(full_price_days_seen) as latest_group
    from daily
    group by app_id

),

sales as (

    select
        app_id,
        full_price_days_seen,
        min(price_date) as start_date,
        max(price_date) as last_sale_date,
        max(discount_percent) as max_discount_percent,
        min(final_cents) as min_final_cents,
        count(*) as days_observed
    from daily
    where is_on_sale
    group by app_id, full_price_days_seen

)

select
    sales.app_id || '-' || strftime(sales.start_date, '%Y%m%d') as sale_id,
    sales.app_id,
    sales.start_date,
    -- Sem preço cheio depois da promoção, ela ainda está aberta.
    case
        when sales.full_price_days_seen < latest.latest_group then sales.last_sale_date
    end as end_date,
    sales.max_discount_percent,
    sales.min_final_cents,
    sales.days_observed,
    -- Sem preço cheio antes, a promoção já existia na primeira observação.
    sales.full_price_days_seen > 0 as start_is_known,
    sales.full_price_days_seen = latest.latest_group as is_open
from sales
inner join latest
    on sales.app_id = latest.app_id
