from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    # Link directly to trade through sale order
    trade_id = fields.Many2one('trading.trade', string='Related Trade', related="sale_id.trade_id", store=True, readonly=True)
    picking_type_code = fields.Selection(related='picking_type_id.code', string='Picking Type Code', store=True, readonly=True)

    def button_validate(self):
        res = super().button_validate()

        for picking in self:
            # 📥 Incoming (PO Receipt) - Link lots to trade
            if picking.picking_type_code == 'incoming' and picking.purchase_id:
                self._process_incoming_picking(picking)
            
            # 📤 Outgoing (SO Delivery) - Just update trade (no need for delivery lines)
            elif picking.picking_type_code == 'outgoing' and picking.trade_id:
                self._process_outgoing_picking(picking)
                
        return res
    
    def _process_incoming_picking(self, picking):
        """Process incoming picking receipt - link lots to trade"""
        try:
            purchase = picking.purchase_id
            
            # Find the trade associated with this purchase order
            trade = self.env['trading.trade'].search([
                ('purchase_id', '=', purchase.id)
            ], limit=1)
            
            if not trade:
                _logger.warning(f"⚠️ No trade found for PO {purchase.name}, skipping lot linking.")
                return
            
            # Get all lots from this picking with their quantities
            lot_quantities = {}
            for move_line in picking.move_line_ids:
                if move_line.lot_id:
                    lot = move_line.lot_id
                    qty = move_line.quantity
                    if lot not in lot_quantities:
                        lot_quantities[lot] = 0
                    lot_quantities[lot] += qty
                    _logger.info(f"🔍 Found lot {lot.name} with quantity {qty} in picking {picking.name}")
            
            if not lot_quantities:
                _logger.warning(f"⚠️ No lots found in picking {picking.name}")
                return
            
            # Link all lots to the trade and update quantities
            for lot, qty in lot_quantities.items():
                if lot not in trade.lot_ids:
                    _logger.info(f"🔗 Linking lot {lot.name} (Qty: {qty}) to trade {trade.name}")
                    trade.write({'lot_ids': [(4, lot.id)]})
                    
                    # Update the lot's quantity if needed (Odoo automatically tracks this)
                    _logger.info(f"📦 Lot {lot.name} has quantity {lot.product_qty} in stock")
            
            _logger.info(f"✅ Successfully linked {len(lot_quantities)} lot(s) to trade {trade.name}")
            
            # Force recompute on-hand quantity
            trade._compute_on_hand_quantity()
            _logger.info(f"📊 Updated on-hand quantity for trade {trade.name}: {trade.on_hand_quantity}")
            
        except Exception as e:
            _logger.error(f"Error processing incoming picking {picking.name}: {str(e)}", exc_info=True)
    
    def _process_outgoing_picking(self, picking):
        """Process outgoing picking delivery - just log and recompute trade"""
        try:
            trade = picking.trade_id
            
            if not trade:
                _logger.info(f"⚠️ No trade linked to picking {picking.name}")
                return
            
            if trade.status != 'confirmed' and trade.status != 'open':
                _logger.info(f"⚠️ Trade {trade.name} is {trade.status}, skipping.")
                return
            
            _logger.info(f"📦 Processing outgoing delivery for trade {trade.name}")
            
            # Log quantities being delivered
            for move_line in picking.move_line_ids:
                if move_line.lot_id and move_line.lot_id in trade.lot_ids:
                    _logger.info(f"   Delivering {move_line.quantity} units from lot {move_line.lot_id.name}")
            
            # Recompute trade totals (sold quantity already tracked through sale orders)
            trade._compute_all_trade_fields()
            
            # Recompute on-hand quantity
            trade._compute_on_hand_quantity()
            _logger.info(f"📊 Updated on-hand quantity for trade {trade.name}: {trade.on_hand_quantity}")
            
            # Check if trade should be closed
            if trade.remaining_quantity <= 0:
                trade.write({
                    'status': 'closed',
                })
                _logger.info(f"✅ Trade {trade.name} closed after full delivery")
            else:
                _logger.info(f"⏳ Trade {trade.name} partially delivered, remaining: {trade.remaining_quantity}")
                    
        except Exception as e:
            _logger.error(f"Error processing outgoing picking {picking.name}: {str(e)}", exc_info=True)