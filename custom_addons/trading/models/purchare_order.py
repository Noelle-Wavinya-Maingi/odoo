from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)

class PurchaseOrder(models.Model):
    _inherit = 'purchase.order'

    trade_id = fields.Many2one('trading.trade', string='Related Trade', ondelete='set null')
    
    # Add a smart button to view the trade
    trade_count = fields.Integer(
        string="Trade Count",
        compute="_compute_trade_count"
    )
    
    def _compute_trade_count(self):
        for order in self:
            order.trade_count = 1 if order.trade_id else 0

    def button_confirm(self):
        _logger.warning("🔘🔘🔘 button_confirm STARTED for %s 🔘🔘🔘", self.name)

        for order in self:
            _logger.warning("Before super - Order: %s, State: %s, Trade: %s",
                          order.name, order.state, order.trade_id.name if order.trade_id else None)

        result = super().button_confirm()

        _logger.warning("🔘🔘🔘 AFTER super() call - Processing trades 🔘🔘🔘")

        for order in self:
            _logger.warning("Processing order: %s", order.name)
            _logger.warning("Order state after confirmation: %s", order.state)

            trade_lines = order.order_line.filtered(lambda l: l.product_id.is_tradeable)

            if not trade_lines:
                _logger.info('Purchase order %s has no trade products, skipping trade creation.', order.name)
                continue

            trade_products = trade_lines.mapped('product_id')
            if len(trade_products) > 1:
                _logger.warning(
                    'Purchase order %s has multiple distinct trade products (%s) — '
                    'only %s will be used for this trade. Split trade products across '
                    'separate orders if they need independent trades.',
                    order.name, trade_products.mapped('name'), trade_products[0].name
                )

            # Everything below is a SIBLING of the multi-product check above, not
            # nested inside it — this must run for every PO with trade lines,
            # whether it has one trade product or several.
            total_qty = sum(trade_lines.mapped('product_qty'))
            total_value = sum(line.product_qty * line.price_unit for line in trade_lines)
            avg_price = total_value / total_qty if total_qty else 0.0

            _logger.warning("Total Quantity: %s, Total Value: %s, Avg Price: %s", total_qty, total_value, avg_price)

            if order.trade_id:
                _logger.warning('Purchase order %s already has a trade (%s), updating trade with purchase order...',
                              order.name, order.trade_id.name)

                trade = order.trade_id
                update_vals = {}
                if not trade.purchase_id:
                    update_vals['purchase_id'] = order.id
                    _logger.warning(f"Setting purchase_id on trade {trade.name} to {order.name}")

                # These two must be updated together with price — price is stored
                # in whatever currency purchase_currency_id says it's in. Updating
                # price without also syncing the currency (as this branch used to)
                # silently mislabels a foreign-currency amount as being in whatever
                # currency the trade happened to default to before a purchase existed.
                if trade.purchase_currency_id != order.currency_id:
                    _logger.warning(
                        f"Currency mismatch: Trade has {trade.purchase_currency_id.name}, "
                        f"PO is in {order.currency_id.name}. Updating trade purchase currency."
                    )
                    update_vals['purchase_currency_id'] = order.currency_id.id

                po_date = order.date_order.date() if order.date_order else fields.Date.context_today(self)
                if trade.purchase_date != po_date:
                    update_vals['purchase_date'] = po_date

                if trade.quantity != total_qty:
                    _logger.warning(f"Quantity mismatch: Trade has {trade.quantity}, PO has {total_qty}. Updating trade quantity.")
                    update_vals['quantity'] = total_qty

                if trade.price != avg_price:
                    _logger.warning(f"Price mismatch: Trade has {trade.price}, PO has {avg_price}. Updating trade price.")
                    update_vals['price'] = avg_price

                if not trade.product_id and trade_lines:
                    product = trade_lines[0].product_id
                    update_vals['product_id'] = product.id
                    _logger.warning(f"Setting product on trade {trade.name} to {product.name}")

                if update_vals:
                    trade.write(update_vals)
                    _logger.warning(f"✅ Updated trade {trade.name} with: {update_vals}")
                else:
                    _logger.warning(f"✅ Trade {trade.name} already has correct values")

                trade._compute_all_trade_fields()
                
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary='Purchase Order Confirmed - Trade Complete',
                    note=f"""
                        <p>The following purchase order has been confirmed:</p>
                        <ul>
                            <li><strong>Trade:</strong> <a href=# data-oe-model=trading.trade data-oe-id={trade.id}>{trade.name}</a></li>
                            <li><strong>Vendor:</strong> {order.partner_id.name}</li>
                            <li><strong>Date:</strong> {fields.Datetime.now()}</li>
                            <li><strong>Total:</strong> {order.amount_total}</li>
                        </ul>
                        <p>Trade has been fully sold and closed.</p>
                    """,
                    user_id=order.user_id.id or self.env.user.id
                )
                continue

            if total_qty <= 0:
                _logger.warning('Purchase order %s has no quantity, skipping trade creation.', order.name)
                continue

            lot = False
            if order.picking_ids:
                _logger.warning("Picking IDs found: %s", order.picking_ids.ids)
                move_lines = order.picking_ids.mapped('move_line_ids').filtered(
                    lambda ml: ml.product_id == trade_lines[0].product_id
                )
                if move_lines:
                    lot = move_lines.mapped('lot_id')[:1] if move_lines else False
                    if lot:
                        _logger.warning("Found lot: %s (ID: %s)", lot.name, lot.id)
                    else:
                        _logger.warning("No lot found in pickings")
                else:
                    _logger.warning("No move lines found in pickings for trade product")
            else:
                _logger.warning("No pickings found for this order")

            trade_vals = {
                'trade_type': 'long',
                'quantity': total_qty,
                'price': avg_price,
                'purchase_currency_id': order.currency_id.id,
                'purchase_date': order.date_order.date() if order.date_order else fields.Date.context_today(self),
                'purchase_id': order.id,
                'status': 'confirmed',
            }

            product = trade_lines[0].product_id
            trade_vals['product_id'] = product.id
            _logger.warning(f"Setting product to: {product.name}")

            if lot:
                trade_vals['lot_ids'] = [(4, lot.id)]
                _logger.warning(f"Adding lot {lot.name} to trade")

            _logger.warning("Creating new trade with values: %s", trade_vals)

            try:
                trade = self.env['trading.trade'].create(trade_vals)
                order.trade_id = trade.id
                _logger.warning('✅✅✅ SUCCESS: Created trade %s (ID: %s) from purchase %s ✅✅✅',
                              trade.name, trade.id, order.name)
                trade._compute_all_trade_fields()
                
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary='Purchase Order Confirmed - New Trade Created',
                    note=f"""
                            <p>A new trade has been automatically created for this purchase order:</p>
                            <ul>
                                <li><strong>Trade:</strong> {trade.name}</li>
                                <li><strong>Product:</strong> {product.name if product else 'N/A'}</li>
                                <li><strong>Quantity:</strong> {trade.quantity}</li>
                                <li><strong>Price:</strong> {trade.price} {trade.purchase_currency_id.symbol}</li>
                            </ul>
                            <p><strong>Note:</strong> This is a purchase trade. If you need to link to a sales trade, please update the trade field manually.</p>
                        """,
                        user_id=order.user_id.id or self.env.user.id
                )

            except Exception as e:
                _logger.error('❌❌❌ ERROR creating trade: %s ❌❌❌', str(e))
                _logger.error('Traceback:', exc_info=True)

        # Outside the for loop — runs once per button click, not once per order,
        # and doesn't cut the loop short for a multi-order confirm.
        _logger.warning("🔘🔘🔘 button_confirm FINISHED for %s 🔘🔘🔘", self.name)
        return result
    
    def action_view_trade(self):
        """Action to view the related trade"""
        self.ensure_one()
        if not self.trade_id:
            return False
        
        return {
            'type': 'ir.actions.act_window',
            'name': 'Trade',
            'res_model': 'trading.trade',
            'view_mode': 'form',
            'res_id': self.trade_id.id,
            'target': 'current',
        }