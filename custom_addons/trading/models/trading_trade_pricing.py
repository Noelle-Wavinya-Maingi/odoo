from odoo import models, fields, api


class TradingTradePricing(models.Model):
    """Sales-price derivation and multi-currency conversion logic."""
    _inherit = 'trading.trade'

    # ═══════════════════ SALES PRICE / SALE CURRENCY (original ccy) ═════
    @api.depends('sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line','sale_order_ids.order_line.product_id', 'sale_order_ids.order_line.product_uom_qty',
        'sale_order_ids.order_line.price_unit', 'sale_order_ids.currency_id', 'sale_order_ids.date_order',
        'trade_type', 'product_id', 'currency_id',)
    def _compute_sales_price_and_currency(self):
        """Derive sales_price / sale_currency_id from confirmed Sale Orders, for long trades.

        - If all confirmed SOs share one currency: sales_price is the qty-weighted average
          in that ORIGINAL currency.
        - If confirmed SOs span multiple currencies: there's no single "original currency"
          price that means anything, so instead show the qty-weighted average converted to
          the REPORTING currency (each order converted at its own date) — this is preferable
          to silently freezing whatever single-currency value was last derivable, which would
          look current but actually be stale.
        - Short trades (or long trades with no confirmed SO yet) keep whatever value is
          already there — this is what makes the fields still manually editable in those
          cases via the inverse methods below."""
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

            if record.trade_type == 'long' and confirmed_orders and len(so_currencies) > 1:
                # Multiple sale currencies — average them in the reporting currency instead.
                company = record.company_id or self.env.company
                reporting_currency = record.currency_id or record.company_id.currency_id
                total_qty = 0.0
                total_value_reporting = 0.0
                for order in confirmed_orders:
                    order_currency = order.currency_id or reporting_currency
                    rate_date = order.date_order.date() if order.date_order else fields.Date.context_today(record)
                    for line in order.order_line:
                        if line.product_id == record.product_id:
                            qty = line.product_uom_qty
                            line_value = line.price_unit * qty
                            if order_currency != reporting_currency:
                                line_value = order_currency._convert(line_value, reporting_currency, company, rate_date)
                            total_qty += qty
                            total_value_reporting += line_value

                if total_qty > 0:
                    record.sales_price = total_value_reporting / total_qty
                    record.sale_currency_id = reporting_currency
                    continue

            # Not derivable — keep existing value
            record.sales_price = fallback_price
            record.sale_currency_id = fallback_currency


    # ═══════════════════ CURRENCY CONVERSION ══════════════════════════════
    @api.depends('price', 'purchase_currency_id', 'currency_id', 'purchase_date','sales_price', 'sale_currency_id', 'sale_order_ids', 'sale_order_ids.state', 'sale_order_ids.order_line', 'sale_order_ids.currency_id', 'current_price', 'current_price_currency_id')
    def _compute_currency_conversions(self):
        for record in self:
            if not record.currency_id:
                record.price_in_base_currency = record.price
                record.sales_price_in_base_currency = record.sales_price
                record.current_price_in_base_currency = record.currency_price
                continue

            company = record.company_id or self.env.company
            conv_date = record.purchase_date or fields.Date.context_today(record)

            # Purchase price conversion
            if record.purchase_currency_id and record.purchase_currency_id != record.currency_id:
                record.price_in_base_currency = record.purchase_currency_id._convert(record.price, record.currency_id, company, conv_date)
            else:
                record.price_in_base_currency = record.price

            # ── Sales price conversion ─────────────────────────────────────
            confirmed_orders = record.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done'])
            so_currencies = set(o.currency_id.id for o in confirmed_orders if o.currency_id)

            if confirmed_orders and len(so_currencies) == 1:
                # All SOs in same currency — convert average_sale_price to base
                record.sales_price_in_base_currency = record.average_sale_price
            elif record.sale_currency_id and record.sale_currency_id != record.currency_id:
                # Manual sales_price in a foreign currency (short trade pre-agreed price)
                record.sales_price_in_base_currency = record.sale_currency_id._convert(record.sales_price, record.currency_id, company, conv_date)
            else:
                record.sales_price_in_base_currency = record.sales_price
            # Current/market price conversion
            if record.current_price_currency_id and record.current_price_currency_id != record.currency_id:
                record.currency_in_base_currency = record.current_price_currency_id._convert(
                    record.current_price, record.currency_id, company, fields.Date.context_today(record)
                )
            else:
                record.current_price_in_base_currency = record.current_price