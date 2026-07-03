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
        
        # Store existing trade info before confirmation
        for order in self:
            _logger.warning("Before super - Order: %s, State: %s, Trade: %s", 
                          order.name, order.state, order.trade_id.name if order.trade_id else None)
        
        # Call the original method
        result = super().button_confirm()
        
        _logger.warning("🔘🔘🔘 AFTER super() call - Processing trades 🔘🔘🔘")
        
        # Process after confirmation
        for order in self:
            _logger.warning("Processing order: %s", order.name)
            _logger.warning("Order state after confirmation: %s", order.state)
            
            # Calculate total quantity and value
            total_qty = sum(order.order_line.mapped('product_qty'))
            total_value = sum(line.product_qty * line.price_unit for line in order.order_line)
            avg_price = total_value / total_qty if total_qty else 0.0
            
            _logger.warning("Total Quantity: %s, Total Value: %s, Avg Price: %s", total_qty, total_value, avg_price)
            
            # Check if trade already exists
            if order.trade_id:
                _logger.warning('Purchase order %s already has a trade (%s), updating trade with purchase order...', 
                              order.name, order.trade_id.name)
                
                # Update the existing trade with this purchase order
                trade = order.trade_id
                
                # Update trade fields if they're not set
                update_vals = {}
                if not trade.purchase_id:
                    update_vals['purchase_id'] = order.id
                    _logger.warning(f"Setting purchase_id on trade {trade.name} to {order.name}")
                
                if trade.quantity != total_qty:
                    _logger.warning(f"Quantity mismatch: Trade has {trade.quantity}, PO has {total_qty}. Updating trade quantity.")
                    update_vals['quantity'] = total_qty
                
                if trade.price != avg_price:
                    _logger.warning(f"Price mismatch: Trade has {trade.price}, PO has {avg_price}. Updating trade price.")
                    update_vals['price'] = avg_price
                
                if not trade.product_id and order.order_line:
                    product = order.order_line[0].product_id
                    update_vals['product_id'] = product.id
                    _logger.warning(f"Setting product on trade {trade.name} to {product.name}")
                
                if update_vals:
                    trade.write(update_vals)
                    _logger.warning(f"✅ Updated trade {trade.name} with: {update_vals}")
                else:
                    _logger.warning(f"✅ Trade {trade.name} already has correct values")
                
                # Recompute trade fields
                trade._compute_all_trade_fields()
                continue
            
            # If no trade exists, create a new one
            if total_qty <= 0:
                _logger.warning('Purchase order %s has no quantity, skipping trade creation.', order.name)
                continue

            # Get lot from pickings if available
            lot = False
            if order.picking_ids:
                _logger.warning("Picking IDs found: %s", order.picking_ids.ids)
                move_lines = order.picking_ids.mapped('move_line_ids')
                if move_lines:
                    lot = move_lines.mapped('lot_id')[:1] if move_lines else False
                    if lot:
                        _logger.warning("Found lot: %s (ID: %s)", lot.name, lot.id)
                    else:
                        _logger.warning("No lot found in pickings")
                else:
                    _logger.warning("No move lines found in pickings")
            else:
                _logger.warning("No pickings found for this order")

            # Create new trade
            trade_vals = {
                'trade_type': 'long',
                'quantity': total_qty,
                'price': avg_price,
                'purchase_currency_id': order.currency_id.id,
                'purchase_date': order.date_order.date() if order.date_order else fields.Date.context_today(self),
                'purchase_id': order.id,
                'status': 'confirmed',
            }
            
            # Get product from first order line
            if order.order_line:
                product = order.order_line[0].product_id
                trade_vals['product_id'] = product.id
                _logger.warning(f"Setting product to: {product.name}")
            
            if lot:
                trade_vals['lot_ids'] = [(4, lot.id)]  # Use lot_ids (many2many)
                _logger.warning(f"Adding lot {lot.name} to trade")
            
            _logger.warning("Creating new trade with values: %s", trade_vals)
            
            try:
                trade = self.env['trading.trade'].create(trade_vals)
                order.trade_id = trade.id
                _logger.warning('✅✅✅ SUCCESS: Created trade %s (ID: %s) from purchase %s ✅✅✅', 
                              trade.name, trade.id, order.name)
                
                # Recompute trade fields
                trade._compute_all_trade_fields()
                
            except Exception as e:
                _logger.error('❌❌❌ ERROR creating trade: %s ❌❌❌', str(e))
                _logger.error('Traceback:', exc_info=True)
            
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