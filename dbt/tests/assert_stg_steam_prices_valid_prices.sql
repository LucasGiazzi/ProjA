-- Falha se um jogo com preço tiver campo vazio ou valor fora da faixa válida.
select *
from {{ ref('stg_steam_prices') }}
where has_price
    and (
        currency is null
        or initial_cents is null
        or final_cents is null
        or discount_percent is null
        or initial_cents < 0
        or final_cents < 0
        or final_cents > initial_cents
        or discount_percent not between 0 and 100
    )
