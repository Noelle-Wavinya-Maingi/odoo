from odoo import models, fields, api


class TradingTradePricing(models.Model):
    """Sales-price derivation and multi-currency conversion logic."""
    _inherit = 'trading.trade'

    # ═══════════════════ SALES PRICE / SALE CURRENCY (original ccy) ═════
    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line','sale_order_ids.order_line.product_id', 'sale_order_ids.order_line.product_uom_qty',
        'sale_order_ids.order_line.price_unit', 'sale_order_ids.currency_id',
        'trade_type', 'product_id',)
    def _compute_sales_price_and_currency(self):
        """Derive sales_price / sale_currency_id from confirmed Sale Orders, in their ORIGINAL currency, for long trades. Short trades (or long trades with no confirmed SO yet, or
        SOs split across multiple currencies) keep whatever value is already there — this is what makes the fields still manually editable in those cases via the inverse methods below."""
        for record in self:
            # Preserve current value by default (covers short trades / not-yet-derivable long trades / manual entries).
            fallback_price = record.sales_price
            fallback_currency = record.sale_currency_id or record.company_id.currency_id

            confirmed_orders = record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            so_currencies = set(o.currency_id.id for o in confirmed_orders if o.currency_id)

            if record.trade_type == 'long' and confirmed_orders and len(so_currencies) == 1:
                total_qty = 0.0
                total_value_original = 0.0
                for order in confirmed_orders:
                    for line in order.order_line:
                        if line.product_id == record.product_id:
                            total_qty += line.product_uom_qty
                            total_value_original += line.price_unit * line.product_uom_qty

                if total_qty > 0:
                    record.sales_price = total_value_original / total_qty
                    record.sale_currency_id = confirmed_orders[0].currency_id
                    continue

            # Not derivable — keep existing value
            record.sales_price = fallback_price
            record.sale_currency_id = fallback_currency


    # ═══════════════════ CURRENCY CONVERSION ══════════════════════════════
    @api.depends('price', 'purchase_currency_id', 'currency_id', 'purchase_date','sales_price', 'sale_currency_id', 'sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line', 'sale_order_ids.currency_id')
    def _compute_currency_conversions(self):
        for record in self:
            if not record.currency_id:
                record.price_in_base_currency = record.price
                record.sales_price_in_base_currency = record.sales_price
                continue

            company = record.company_id or self.env.company
            conv_date = record.purchase_date or fields.Date.context_today(record)

            # Purchase price conversion
            if record.purchase_currency_id and record.purchase_currency_id != record.currency_id:
                record.price_in_base_currency = record.purchase_currency_id._convert(record.price, record.currency_id, company, conv_date)
            else:
                record.price_in_base_currency = record.price

            # ── Sales price conversion ─────────────────────────────────────
            # For long trades with SO lines: check if all SOs use the same currency
            # If yes and it differs from reporting currency, convert sales_price
            # using the average rate across SOs for display purposes.
            # For short trades or manual sales_price: use sale_currency_id directly.
            confirmed_orders = record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            so_currencies = set(o.currency_id.id for o in confirmed_orders if o.currency_id)

            if confirmed_orders and len(so_currencies) == 1:
                # All SOs in same currency — convert average_sale_price to base
                # (average_sale_price is already in reporting currency from
                # _compute_sales_totals, see trading_trade_pnl.py)
                record.sales_price_in_base_currency = record.average_sale_price
            elif record.sale_currency_id and record.sale_currency_id != record.currency_id:
                # Manual sales_price in a foreign currency (short trade pre-agreed price)
                record.sales_price_in_base_currency = record.sale_currency_id._convert(record.sales_price, record.currency_id, company, conv_date)
            else:
                record.sales_price_in_base_currency = record.sales_price