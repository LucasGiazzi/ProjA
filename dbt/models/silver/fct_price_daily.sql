-- Uma linha por jogo e dia, só com preços reais. Falha de coleta e jogo sem
-- preço ficam fora. Dias sem coleta continuam ausentes: na coleta diária, um
-- buraco é falha real. O preenchimento entra na Fase 3, com o histórico do ITAD.
select
    app_id,
    price_date,
    collected_at,
    currency,
    initial_cents,
    final_cents,
    discount_percent,
    discount_percent > 0 as is_on_sale
from {{ ref('stg_steam_prices') }}
where has_price
