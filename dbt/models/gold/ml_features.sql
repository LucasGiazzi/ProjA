-- Uma linha por jogo e dia, com features e rótulo. Toda feature usa só dados
-- até a data da linha. Não use fct_sale_events aqui: ele conhece o fim e o
-- desconto máximo de promoções em andamento, o que seria vazamento.
with daily as (

    select
        app_id,
        price_date,
        initial_cents,
        discount_percent,
        is_on_sale,
        is_on_sale
            and not coalesce(
                lag(is_on_sale) over (partition by app_id order by price_date),
                false
            ) as is_sale_start
    from {{ ref('fct_price_daily') }}

),

game_history as (

    select
        *,
        max(case when is_on_sale then price_date end) over past_days as last_sale_day,
        min(case when is_sale_start then price_date end) over past_days as first_sale_start,
        max(case when is_sale_start then price_date end) over past_days as last_sale_start,
        count_if(is_sale_start) over past_days as sales_to_date,
        count_if(is_sale_start) over last_year as sales_last_12_months,
        max(discount_percent) over past_days as max_discount_to_date,
        avg(discount_percent) filter (where is_on_sale) over past_days as typical_discount,
        -- O rótulo olha para frente de propósito: é a resposta, não uma feature.
        count(*) over next_days as observed_days_next_30,
        count_if(is_on_sale) over next_days as sale_days_next_30
    from daily
    window
        past_days as (
            partition by app_id
            order by price_date
            rows between unbounded preceding and current row
        ),
        last_year as (
            partition by app_id
            order by price_date
            range between interval 364 days preceding and current row
        ),
        next_days as (
            partition by app_id
            order by price_date
            range between interval 1 day following and interval 30 days following
        )

),

calendar_days as (

    select
        days.price_date,
        min(calendar.start_date) filter (
            where calendar.start_date > days.price_date
        ) as next_seasonal_start,
        coalesce(
            bool_or(
                calendar.start_date <= days.price_date
                and calendar.last_sale_date >= days.price_date
            ),
            false
        ) as is_seasonal_sale_today,
        -- A janela do baseline: a promoção sazonal cruza os próximos 30 dias.
        coalesce(
            bool_or(
                calendar.start_date <= days.price_date + 30
                and calendar.last_sale_date >= days.price_date + 1
            ),
            false
        ) as seasonal_sale_in_window
    from (select distinct price_date from daily) as days
    cross join {{ ref('steam_sale_calendar') }} as calendar
    group by days.price_date

),

publisher_days as (

    select
        games.publisher,
        daily.price_date,
        count(*) as game_days,
        count_if(daily.is_on_sale) as sale_game_days
    from daily
    inner join {{ ref('dim_games') }} as games
        on daily.app_id = games.app_id
    where games.publisher is not null
    group by games.publisher, daily.price_date

),

publisher_history as (

    select
        publisher,
        price_date,
        -- Termina no dia anterior, para o dia atual não entrar na própria taxa.
        sum(sale_game_days) over earlier_days * 1.0
            / nullif(sum(game_days) over earlier_days, 0) as publisher_sale_rate
    from publisher_days
    window earlier_days as (
        partition by publisher
        order by price_date
        rows between unbounded preceding and 1 preceding
    )

)

select
    history.app_id,
    history.price_date,

    -- Histórico
    date_diff('day', history.last_sale_day, history.price_date) as days_since_last_sale,
    case
        when history.sales_to_date >= 2
            then date_diff('day', history.first_sale_start, history.last_sale_start) * 1.0
                / (history.sales_to_date - 1)
    end as avg_days_between_sales,
    history.sales_to_date,
    history.sales_last_12_months,
    history.max_discount_to_date,
    history.typical_discount,

    -- Calendário
    date_diff('day', history.price_date, calendar_days.next_seasonal_start) as days_to_next_seasonal,
    calendar_days.is_seasonal_sale_today,
    month(history.price_date) as month,

    -- Jogo
    date_diff('day', games.release_date, history.price_date) as days_since_release,
    history.initial_cents as base_price_cents,
    publisher_history.publisher_sale_rate,

    -- Estado atual
    history.is_on_sale,
    history.discount_percent,
    history.discount_percent - history.typical_discount as discount_vs_typical,

    -- Baseline obrigatório do design
    calendar_days.seasonal_sale_in_window as baseline_prediction,

    -- Rótulo: vazio enquanto os 30 dias seguintes não estiverem todos observados.
    case
        when history.observed_days_next_30 = 30 then history.sale_days_next_30 > 0
    end as has_sale_next_30d
from game_history as history
inner join calendar_days
    on history.price_date = calendar_days.price_date
inner join {{ ref('dim_games') }} as games
    on history.app_id = games.app_id
left join publisher_history
    on games.publisher = publisher_history.publisher
    and history.price_date = publisher_history.price_date
-- Antes do lançamento o jogo não está à venda de forma normal.
where games.release_date is null
    or history.price_date >= games.release_date
