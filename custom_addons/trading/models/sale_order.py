from odoo import models, fields, api, _
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    trade_id = fields.Many2one('trading.trade', string="Related Trade")
    
    @api.onchange('trade_id')
    def _onchange_trade_id(self):
        """When trade is selected, you can show trade info"""
        if self.trade_id:
            _logger.info(f"✨ Linking sale order to trade: {self.trade_id.name}")

    def action_confirm(self):
        """Override confirm method to update trade when sales order is confirmed"""
        result = super().action_confirm()

        for order in self:
            if not order.trade_id:
                # If no trade selected, try to create one
                _logger.info(f"📝 No trade selected for sale order {order.name}, checking if trade needs to be created...")
                total_qty = sum(order.order_line.mapped('product_uom_qty'))
                if total_qty > 0:
                    trade = self._create_trade_from_sale_order(order)
                    if trade:
                        order.write({'trade_id': trade.id})
                        _logger.info(f"✅ Created new trade {trade.name} for sale order {order.name}")
                continue
            
            # Update the trade with this sale order
            trade = order.trade_id
            _logger.info(f"🌼 Processing sale order {order.name} for trade {trade.name}")
            
            # Add this sale order to the trade's sale orders if not already linked
            if order not in trade.sale_order_ids:
                trade.write({'sale_order_ids': [(4, order.id)]})
            
            # Recompute all trade calculations
            trade._compute_all_trade_fields()
            
            # Check if trade should be closed based on quantity
            total_sold_qty = sum(trade.sale_order_ids.filtered(lambda so: so.state in ['sale', 'done']).mapped('order_line.product_uom_qty'))
            if total_sold_qty >= trade.quantity:
                _logger.info(f"🏁 Trade {trade.name} fully sold ({total_sold_qty}/{trade.quantity}), closing...")
                trade.write({'status': 'closed'})
                trade._compute_all_trade_fields()
                
                # Post activity
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary='Sales Order Confirmed - Trade Completed',
                    note=f"""
                        <p>The following sales order has been confirmed:</p>
                        <ul>
                            <li><strong>Trade:</strong> <a href=# data-oe-model=trading.trade data-oe-id={trade.id}>{trade.name}</a></li>
                            <li><strong>Customer:</strong> {order.partner_id.name}</li>
                            <li><strong>Date:</strong> {fields.Datetime.now()}</li>
                            <li><strong>Total:</strong> {order.amount_total}</li>
                        </ul>
                        <p>Trade has been fully sold and closed.</p>
                    """,
                    user_id=order.user_id.id or self.env.user.id
                )
            else:
                _logger.info(f"⏳ Trade {trade.name} partially sold ({total_sold_qty}/{trade.quantity})")

        return result
    
    def _create_trade_from_sale_order(self, order):
        """Create a new trade from a sale order"""
        try:
            total_qty = sum(order.order_line.mapped('product_uom_qty'))
            total_value = sum(line.price_unit * line.product_uom_qty for line in order.order_line)
            avg_price = total_value / total_qty if total_qty > 0 else 0.0
            
            product = order.order_line[0].product_id if order.order_line else False
            
            # Determine trade type based on sale order type (default to long for sales)
            trade_type = 'short'
            
            trade_vals = {
                'trade_type': trade_type,
                'quantity': total_qty,
                'sales_price': avg_price,
                'currency_id': order.currency_id.id,
                'status': 'confirmed',
                'product_id': product.id if product else False,
                'sale_order_ids': [(4, order.id)],
            }
            
            trade = self.env['trading.trade'].create(trade_vals)
            trade._compute_all_trade_fields()
            
            order.message_post(body=f"""
                <p>✅ A new trade has been automatically created for this sale order:</p>
                <ul>
                    <li><strong>Trade:</strong> {trade.name}</li>
                    <li><strong>Product:</strong> {product.name if product else 'N/A'}</li>
                    <li><strong>Quantity:</strong> {trade.quantity}</li>
                    <li><strong>Price:</strong> {trade.price} {trade.currency_id.symbol}</li>
                </ul>
                <p><strong>Note:</strong> This is a sales trade. If you need to link to a purchase trade, please update the trade field manually.</p>
            """)
            
            return trade
            
        except Exception as e:
            order.message_post(body=f"""
                <p>❌ <strong>Error creating trade:</strong></p>
                <p>{str(e)}</p>
                <p>Please create the trade manually.</p>
            """)
            return False