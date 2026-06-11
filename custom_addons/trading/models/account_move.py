from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    trade_id = fields.Many2one('trading.trade', string='Trade', help='Related trade for this move')
    is_from_purchase_order = fields.Boolean(string="From Purchase Order", compute='_compute_is_from_order', store=True)
    is_from_sale_order = fields.Boolean(string="From Sale Order", compute='_compute_is_from_order', store=True)
    
    @api.depends('purchase_id', 'invoice_origin')
    def _compute_is_from_order(self):
        """Determine if the invoice is from a purchase order or sale order"""
        for move in self:

            # Purchase order detection: check purchase_id first, then invoice_origin as fallback
            is_from_po = bool(move.move_type in ['in_invoice', 'in_refund'] and move.purchase_id)
            if not is_from_po and move.move_type in ['in_invoice', 'in_refund'] and move.invoice_origin:
                po = self.env['purchase.order'].search([('name', '=', move.invoice_origin)], limit=1)
                is_from_po = bool(po)
            move.is_from_purchase_order = is_from_po

            # Sale order detection
            sale_order = None
            if move.move_type in ['out_invoice', 'out_refund'] and move.invoice_origin:
                sale_order = self.env['sale.order'].search([('name', '=', move.invoice_origin)], limit=1)
            move.is_from_sale_order = bool(sale_order)

            # If this is a sale order invoice and the sale order has a trade, propagate it
            if move.is_from_sale_order and sale_order and sale_order.trade_id and not move.trade_id:
                move.trade_id = sale_order.trade_id.id
    
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to handle trade P&L updates when creating invoices/bills"""
        
        # Before creating, ensure trade_id is set from linked PO or sale order
        for vals in vals_list:
            if vals.get('move_type') in ['in_invoice', 'in_refund'] and not vals.get('trade_id'):
                purchase_id = vals.get('purchase_id')
                if purchase_id:
                    po = self.env['purchase.order'].browse(purchase_id)
                    if po.trade_id:
                        vals['trade_id'] = po.trade_id.id
                elif vals.get('invoice_origin'):
                    po = self.env['purchase.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
                    if po and po.trade_id:
                        vals['trade_id'] = po.trade_id.id

            if vals.get('move_type') in ['out_invoice', 'out_refund'] and vals.get('invoice_origin'):
                sale_order = self.env['sale.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
                if sale_order and sale_order.trade_id and not vals.get('trade_id'):
                    vals['trade_id'] = sale_order.trade_id.id
        
        records = super().create(vals_list)
        
        # Process each record that has a trade_id (header level)
        for record in records:
            if record.trade_id:
                if not record.is_from_purchase_order and not record.is_from_sale_order:
                    record._update_trade_pnl_from_invoice()
                elif record.is_from_purchase_order:
                    record._update_trade_additional_costs()
            else:
                # Check if any invoice lines have trade_id
                record._process_line_level_trades()
        
        return records
    
    def write(self, vals):
        """Override write to handle trade P&L updates when modifying invoices/bills"""
    
        # Check if we're moving to posted state
        is_moving_to_posted = 'state' in vals and vals['state'] == 'posted'
    
        result = super().write(vals)
    
        # Only process if we're moving to posted state and the invoice wasn't already posted
        if is_moving_to_posted:
            for record in self:
                # Only process if the invoice wasn't already posted before
                if not record.posted_before:

                    # Check if invoice has trade_id on header or lines
                    has_trade = record.trade_id or any(line.trade_id for line in record.invoice_line_ids)
                
                    if has_trade:
                        if record.trade_id and not record.is_from_purchase_order and not record.is_from_sale_order:
                            record._update_trade_pnl_from_invoice()
                        else:
                            # Check line level trades
                            record._process_line_level_trades()
    
        return result
    
    def action_post(self):
        """Override to update trades when invoice/bill is posted"""
        result = super().action_post()
        
        # First, ensure trade information from sale orders is propagated to invoice lines
        for move in self:
            
            if move.is_from_sale_order and move.invoice_origin:
                sale_order = self.env['sale.order'].search([('name', '=', move.invoice_origin)], limit=1)
                if sale_order and sale_order.trade_id:
                    # Ensure the invoice has the trade
                    if not move.trade_id:
                        move.trade_id = sale_order.trade_id.id
                    
                    # Ensure invoice lines have the product's trade information
                    for invoice_line in move.invoice_line_ids:
                        if invoice_line.product_id and not invoice_line.trade_id:
                            # Check if the sale order line had trade information
                            sale_order_line = sale_order.order_line.filtered(
                                lambda l: l.product_id == invoice_line.product_id
                            )
                            if sale_order_line and sale_order_line.trade_id:
                                invoice_line.trade_id = sale_order_line.trade_id.id
                            elif sale_order.trade_id:
                                invoice_line.trade_id = sale_order.trade_id.id
        
        # Update all invoices/bills that have trade_id (header or line level)
        for move in self:
            
            # Check header level trade
            if move.trade_id:
                if not move.is_from_purchase_order and not move.is_from_sale_order:
                    move._update_trade_pnl_from_invoice()
                elif move.is_from_purchase_order:
                    move._update_trade_additional_costs()
                elif move.is_from_sale_order and move.trade_id:
                    move._update_trade_pnl_from_sale_order()
            else:
                # Check line level trades
                move._process_line_level_trades()
        
        return result
    
    def _update_trade_additional_costs(self):
        """Update trade with additional costs from vendor bills (transportation, fees, etc.)"""
        self.ensure_one()
        
        if not self.trade_id or not self.is_from_purchase_order:
            return
        
        trade = self.trade_id
        
        if self.state == 'posted':
            
            # Calculate total additional costs from all bill lines
            total_additional_cost = 0.0
            
            for line in self.invoice_line_ids:
                line_total = line.price_unit * line.quantity
                total_additional_cost += line_total
            
            if total_additional_cost > 0:
                old_costs = trade.additional_costs
                trade.write({
                    'additional_costs': trade.additional_costs + total_additional_cost
                })
                
                
                # Recalculate trade P&L with new costs
                trade._compute_all_trade_fields()
    
    def _update_trade_pnl_from_invoice(self):
        """Update trade P&L based on invoice/bill (direct trades only)"""
        self.ensure_one()
    
        if not self.trade_id:
            return
    
        trade = self.trade_id
    
        # Determine if it's a bill (vendor bill) or invoice (customer invoice)
        is_bill = self.move_type in ['in_invoice', 'in_refund']
        is_invoice = self.move_type in ['out_invoice', 'out_refund']
    
        if is_bill:
            # This is a purchase (bill) - update purchase side of trade
            if self.state == 'posted':
                
                total_quantity = 0.0
                total_amount = 0.0
                has_matching_product = False
                total_additional_cost = 0.0
            
                for line in self.invoice_line_ids:
                    if line.product_id == trade.product_id:
                        has_matching_product = True
                        total_quantity += line.quantity
                        total_amount += line.price_unit * line.quantity
                    else:
                        if line_total > 0:
                            total_additional_cost += line_total
            
                # After processing all lines, update the trade with additional costs
                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({
                        'additional_costs': trade.additional_costs + total_additional_cost
                    })
            
                if total_quantity > 0:
                    avg_price = total_amount / total_quantity
                
                    if trade.quantity > 0:
                        total_cost = (trade.quantity * trade.price) + total_amount
                        total_qty = trade.quantity + total_quantity
                        trade.write({
                            'quantity': total_qty,
                            'price': total_cost / total_qty if total_qty > 0 else 0,
                        })
                    else:
                        trade.write({
                            'quantity': total_quantity,
                            'price': avg_price,
                        })
                
                    trade._compute_all_trade_fields()
                elif total_additional_cost > 0:
                    trade._compute_all_trade_fields()
                
        elif is_invoice and not self.is_from_sale_order:
            # This is a direct sale not from a sale order
            if self.state == 'posted':
                
                total_quantity = 0.0
                total_amount = 0.0
            
                for line in self.invoice_line_ids:
                    if line.product_id == trade.product_id:
                        total_quantity += line.quantity
                        total_amount += line.price_unit * line.quantity

                if total_quantity > 0:
                    avg_price = total_amount / total_quantity
                
                    # Create a minimal sale order for tracking
                    sale_order = self.env['sale.order'].create({
                        'partner_id': self.partner_id.id,
                        'company_id': self.company_id.id,
                        'state': 'sale',
                        'origin': f"Invoice {self.name}",
                        'client_order_ref': self.invoice_payment_ref or self.name,
                        'trade_id': trade.id,
                    })

                    self.env['sale.order.line'].create({
                        'order_id': sale_order.id,
                        'product_id': trade.product_id.id,
                        'product_uom_qty': total_quantity,
                        'price_unit': avg_price,
                        'name': f"Direct invoice sale for trade {trade.name} - Invoice {self.name}",
                        'trade_id': trade.id,
                    })

                    trade.write({
                        'sale_order_ids': [(4, sale_order.id)]
                    })
                
                    trade._compute_all_trade_fields()
    
        # After updating, check if trade should be auto-closed
        if trade.is_fully_matched and trade.status == 'confirmed':
            trade.status = 'closed'
    
    def _update_trade_pnl_from_sale_order(self):
        """Update trade P&L based on sale order invoice"""
        self.ensure_one()
        
        if not self.trade_id or not self.is_from_sale_order:
            return
        
        trade = self.trade_id
        
        if self.state == 'posted':
            
            # Get the sale order
            sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
            if not sale_order:
                return
            
            # Ensure the sale order is linked to the trade
            if trade not in sale_order.trade_id:
                trade.write({
                    'sale_order_ids': [(4, sale_order.id)]
                })
            
            # Process each invoice line
            for invoice_line in self.invoice_line_ids:
                if invoice_line.product_id == trade.product_id:
                    sale_order_line = sale_order.order_line.filtered(
                        lambda l: l.product_id == invoice_line.product_id
                    )
                    
                    if sale_order_line:
                        if not sale_order.trade_id:
                            sale_order.trade_id = trade.id
            
            trade._compute_all_trade_fields()
            
    def _process_line_level_trades(self):
        """Process trades from invoice lines instead of invoice header"""
        self.ensure_one()
    
        # Skip if invoice is not posted
        if self.state != 'posted':
            return
    
        # Check if we already processed this invoice by looking at a field
        if self.trade_id and self.trade_id.additional_revenue > 0:
            # Check if this specific invoice was already processed
            return
    
        # Group invoice lines by trade
        trades_to_update = {}
    
        for line in self.invoice_line_ids:
            if line.trade_id:
                trade = line.trade_id
            
                if trade.id not in trades_to_update:
                    trades_to_update[trade.id] = {
                        'trade': trade,
                        'lines': [],
                        'is_bill': self.move_type in ['in_invoice', 'in_refund'],
                        'is_customer_invoice': self.move_type in ['out_invoice', 'out_refund']
                    }
                trades_to_update[trade.id]['lines'].append(line)
    
    
        # Process each trade
        for trade_id, trade_data in trades_to_update.items():
            trade = trade_data['trade']
            lines = trade_data['lines']
            is_bill = trade_data['is_bill']
            is_customer_invoice = trade_data['is_customer_invoice']
        
        
            if is_bill:
                # This is a cost we pay (adds to additional_costs)
                total_additional_cost = 0.0
                for line in lines:
                    line_total = line.price_unit * line.quantity
                    total_additional_cost += line_total
            
                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({
                        'additional_costs': trade.additional_costs + total_additional_cost
                    })
                    trade._compute_all_trade_fields()
                
            elif is_customer_invoice:
                # This is revenue we charge (adds to additional_revenue)
                total_additional_revenue = 0.0
                for line in lines:
                    line_total = line.price_unit * line.quantity
                    total_additional_revenue += line_total
            
                if total_additional_revenue > 0:
                    old_revenue = trade.additional_revenue
                    trade.write({
                        'additional_revenue': trade.additional_revenue + total_additional_revenue
                    })
                    trade._compute_all_trade_fields()
    
        # Check if any trade should be auto-closed
        for trade_data in trades_to_update.values():
            trade = trade_data['trade']
            if trade.is_fully_matched and trade.status == 'confirmed':
                trade.status = 'closed'
