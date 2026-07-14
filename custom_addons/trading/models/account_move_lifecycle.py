import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AccountMoveLifecycle(models.Model):
    """create/write/action_post/button_draft overrides that wire invoices and bills into their related trade (trade_id propagation, triggering P&L updates at the right lifecycle moments)."""
    _inherit = 'account.move'
    
    def _reverse_trade_pnl_contribution(self, trade):
        """Reverse this move's already-applied contribution to the trade's additional costs or revenue, and clear the trade_pnl_processed so it can be reprocessed later"""
        self.ensure_one()

        if not self.trade_pnl_processed or not trade:
            return

        company = trade.company_id or self.env.company
        rate_date = self.invoice_date or fields.Date.context_today(self)
        invoice_currency = self.currency_id
        trade_currency = trade.currency_id

        def to_trade_currency(amount):
            if invoice_currency and trade_currency and invoice_currency != trade_currency:
                return invoice_currency._convert(amount, trade_currency, company, rate_date)
            return amount

        if self.move_type in ['out_invoice', 'out_refund'] and not self.is_from_sale_order:
            total_amount = sum(to_trade_currency(line.price_unit * line.quantity) for line in self.invoice_line_ids if line.display_type not in ('line_section', 'line_note', 'tax'))

            if total_amount > 0:
                trade.write({'additional_revenue': max(trade.additional_revenue - total_amount, 0)})
                trade._compute_all_trade_fields()

        elif self.move_type in ['in_invoice', 'in_refund'] and not self.is_from_purchase_order:
            total_costs = sum(to_trade_currency(line.price_unit * line.quantity) for line in self.invoice_line_ids if line.display_type not in ('line_section', 'line_note', 'tax') and line.product_id != trade.product_id)

            if total_costs > 0:
                trade.write({'additional_costs': max(trade.additional_costs - total_costs, 0)})
                trade._compute_all_trade_fields()

        self.trade_pnl_processed = False
                            

    @api.model_create_multi
    def create(self, vals_list):

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

        for record in records:
            if record.trade_id:
                record.trade_id._compute_invoice_count()
                
                if not record.is_from_purchase_order and not record.is_from_sale_order:
                    record._update_trade_pnl_from_invoice()
                    
                elif record.is_from_purchase_order:
                    _logger.info(f"💰 Processing purchase order additional costs")
                    
            else:
                record._process_line_level_trades()

        return records

    def write(self, vals):

        if 'invoice_line_ids' in vals and 'trade_id' not in vals:
            for command in vals['invoice_line_ids']:
                if command[0] == 1 and isinstance(command[2], dict) and 'trade_id' in command[2]:
                    new_trade_id = command[2]['trade_id']
                    vals['trade_id'] = new_trade_id or False
                    break

        old_trade_ids = {}
        if 'trade_id' in vals:
            for move in self:
                old_trade_ids[move.id] = move.trade_id.id

        is_moving_to_posted = 'state' in vals and vals['state'] == 'posted'

        result = super().write(vals)

        processed_in_this_call = set()

        if 'trade_id' in vals:
            new_trade_id = vals.get('trade_id')

            for move in self:
                old_id = old_trade_ids.get(move.id)
                if old_id and old_id != new_trade_id:
                    old_trade = self.env['trading.trade'].browse(old_id)
                    move._reverse_trade_pnl_contribution(old_trade)
                    old_trade._compute_invoice_count()

                if new_trade_id:
                    new_trade = self.env['trading.trade'].browse(new_trade_id)
                    new_trade._compute_invoice_count()

                    if move.state == 'posted':
                        
                        if move.is_from_sale_order:
                            move._update_trade_pnl_from_sale_order()
                            
                        elif move.is_from_purchase_order:
                            move._update_trade_additional_costs()
                            
                        else:
                            move._update_trade_pnl_from_invoice()
                            
                        processed_in_this_call.add(move.id)

        if is_moving_to_posted:
            for record in self:
                record.invalidate_recordset(['trade_pnl_processed'])

                if record.id in processed_in_this_call:
                    continue

                if not record.trade_pnl_processed:
                    has_trade = record.trade_id or any(line.trade_id for line in record.invoice_line_ids)

                    if has_trade:
                        if record.is_from_sale_order:
                            # SO invoice — revenue already captured via sale_order_ids,
                            # just link and recompute, do NOT add to additional_revenue
                            record._update_trade_pnl_from_sale_order()
                            
                        elif record.is_from_purchase_order:
                            record._update_trade_additional_costs()
                            
                        elif record.trade_id:
                            # Direct invoice not from any order — additional revenue/cost
                            record._update_trade_pnl_from_invoice()
                            
                        else:
                            # No header trade — propagate from lines then P&L fires via trade_id write
                            line_trades = record.invoice_line_ids.mapped('trade_id')
                            
                            if len(line_trades) >= 1:
                                record.trade_id = line_trades[0].id
                                record.trade_id._compute_invoice_count()
                                

        return result

    def action_post(self):
        result = super().action_post()

        for move in self:

            if move.is_from_sale_order and move.invoice_origin:
                sale_order = self.env['sale.order'].search([('name', '=', move.invoice_origin)], limit=1)
                if sale_order and sale_order.trade_id:
                    
                    if not move.trade_id:
                        move.trade_id = sale_order.trade_id.id
                        move.trade_id._compute_invoice_count()

                    for invoice_line in move.invoice_line_ids:
                        if invoice_line.product_id and not invoice_line.trade_id:
                            sale_order_line = sale_order.order_line.filtered(lambda l: l.product_id == invoice_line.product_id)
                            
                            if sale_order_line and sale_order_line.trade_id:
                                invoice_line.trade_id = sale_order_line.trade_id.id
                                
                            elif sale_order.trade_id:
                                invoice_line.trade_id = sale_order.trade_id.id

            if move.is_from_purchase_order and move.invoice_origin:
                purchase_order = self.env['purchase.order'].search([('name', '=', move.invoice_origin)], limit=1)
                if purchase_order and purchase_order.trade_id:
                    
                    if not move.trade_id:
                        move.trade_id = purchase_order.trade_id.id
                        move.trade_id._compute_invoice_count()

                    for invoice_line in move.invoice_line_ids:
                        if invoice_line.product_id and not invoice_line.trade_id:
                            purchase_order_line = purchase_order.order_line.filtered(lambda l: l.product_id == invoice_line.product_id)
                            
                            if purchase_order_line and purchase_order_line.trade_id:
                                invoice_line.trade_id = purchase_order_line.trade_id.id
                                
                            elif purchase_order.trade_id:
                                invoice_line.trade_id = purchase_order.trade_id.id

        for move in self:

            if move.trade_id:
                move.trade_id._compute_invoice_count()
                
                if move.is_from_sale_order:
                    move._update_trade_pnl_from_sale_order()
                    
                elif move.is_from_purchase_order:
                    move._update_trade_additional_costs()
                    
                else:
                    move._update_trade_pnl_from_invoice()
                    
            else:
                move._process_line_level_trades()

        return result

    def button_draft(self):
        """Reverse trade P&L contribution when invoice is reset to draft."""
        for move in self:
            move._reverse_trade_pnl_contribution(move.trade_id)

        return super().button_draft()