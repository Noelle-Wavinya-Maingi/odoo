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
            _logger.info(f"🔄 Reversing trade P&L contribution for invoice {self.name}: total_amount={total_amount} in trade currency")

            if total_amount > 0:
                trade.write({'additional_revenue': max(trade.additional_revenue - total_amount, 0)})
                trade._compute_all_trade_fields()

        elif self.move_type in ['in_invoice', 'in_refund'] and not self.is_from_purchase_order:
            total_costs = sum(to_trade_currency(line.price_unit * line.quantity) for line in self.invoice_line_ids if line.display_type not in ('line_section', 'line_note', 'tax') and line.product_id != trade.product_id)
            _logger.info(f"🔄 Reversing trade P&L contribution for bill {self.name}: total_costs={total_costs} in trade currency")

            if total_costs > 0:
                trade.write({'additional_costs': max(trade.additional_costs - total_costs, 0)})
                trade._compute_all_trade_fields()
                
        trade._remove_budget_line_for_move(self)

        self.trade_pnl_processed = False
                            

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(f"📝 Creating {len(vals_list)} invoice(s)/bill(s)")

        for vals in vals_list:
            if vals.get('move_type') in ['in_invoice', 'in_refund'] and not vals.get('trade_id'):
                purchase_id = vals.get('purchase_id')
                
                if purchase_id:
                    po = self.env['purchase.order'].browse(purchase_id)
                    
                    if po.trade_id:
                        _logger.info(f"🔄 Setting trade {po.trade_id.name} from purchase order to bill")
                        vals['trade_id'] = po.trade_id.id
                        
                elif vals.get('invoice_origin'):
                    po = self.env['purchase.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
                    
                    if po and po.trade_id:
                        _logger.info(f"🔄 Setting trade {po.trade_id.name} from purchase order (origin) to bill")
                        vals['trade_id'] = po.trade_id.id

            if vals.get('move_type') in ['out_invoice', 'out_refund'] and vals.get('invoice_origin'):
                sale_order = self.env['sale.order'].search([('name', '=', vals['invoice_origin'])], limit=1)
                
                if sale_order and sale_order.trade_id and not vals.get('trade_id'):
                    _logger.info(f"🔄 Setting trade {sale_order.trade_id.name} from sale order to invoice")
                    vals['trade_id'] = sale_order.trade_id.id

        records = super().create(vals_list)

        for record in records:
            if record.trade_id:
                _logger.info(f"✅ Invoice {record.name} has header trade: {record.trade_id.name}")
                record.trade_id._compute_invoice_count()
                
                if not record.is_from_purchase_order and not record.is_from_sale_order:
                    record._update_trade_pnl_from_invoice()
                    
                elif record.is_from_purchase_order:
                    _logger.info(f"💰 Processing purchase order additional costs")
                    
            else:
                _logger.info(f"🔍 Checking invoice {record.name} for line-level trades")
                record._process_line_level_trades()

        return records

    def write(self, vals):
        _logger.info(f"✏️ Writing to invoice: {vals}")

        if 'invoice_line_ids' in vals and 'trade_id' not in vals:
            for command in vals['invoice_line_ids']:
                if command[0] == 1 and isinstance(command[2], dict) and 'trade_id' in command[2]:
                    new_trade_id = command[2]['trade_id']
                    _logger.info(f"🔄 Syncing line trade_id={new_trade_id} → invoice header")
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
            _logger.info(f"🔄 trade_id changed in write, new trade ID: {new_trade_id}")

            for move in self:
                old_id = old_trade_ids.get(move.id)
                _logger.info(f"   Invoice {move.name}: old trade ID={old_id} → new trade ID={new_trade_id}")
                if old_id and old_id != new_trade_id:
                    old_trade = self.env['trading.trade'].browse(old_id)
                    _logger.info(f"🔁 Recomputing count on OLD trade: {old_trade.name}")
                    move._reverse_trade_pnl_contribution(old_trade)
                    old_trade._compute_invoice_count()

                if new_trade_id:
                    new_trade = self.env['trading.trade'].browse(new_trade_id)
                    _logger.info(f"🔁 Recomputing count on NEW trade: {new_trade.name}")
                    new_trade._compute_invoice_count()

                    if move.state == 'posted':
                        _logger.info(f"🔄 Invoice {move.name} is posted, reprocessing P&L for new trade {new_trade.name}")
                        
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
                _logger.info(f"   📋 Invoice {record.name} | state={record.state} | trade_pnl_processed={record.trade_pnl_processed} | trade_id={record.trade_id.name if record.trade_id else 'None'}")

                if record.id in processed_in_this_call:
                    _logger.info(f"⏭️ Invoice {record.name} already processed in this write call, skipping")
                    continue

                if not record.trade_pnl_processed:
                    has_trade = record.trade_id or any(line.trade_id for line in record.invoice_line_ids)

                    if has_trade:
                        if record.is_from_sale_order:
                            # SO invoice — revenue already captured via sale_order_ids,
                            # just link and recompute, do NOT add to additional_revenue
                            _logger.info(f"✅ SO invoice — calling _update_trade_pnl_from_sale_order")
                            record._update_trade_pnl_from_sale_order()
                            
                        elif record.is_from_purchase_order:
                            _logger.info(f"✅ PO invoice — calling _update_trade_additional_costs")
                            record._update_trade_additional_costs()
                            
                        elif record.trade_id:
                            # Direct invoice not from any order — additional revenue/cost
                            _logger.info(f"✅ Direct invoice — calling _update_trade_pnl_from_invoice")
                            record._update_trade_pnl_from_invoice()
                            
                        else:
                            # No header trade — propagate from lines then P&L fires via trade_id write
                            _logger.info(f"✅ No header trade, propagating from lines")
                            line_trades = record.invoice_line_ids.mapped('trade_id')
                            
                            if len(line_trades) >= 1:
                                record.trade_id = line_trades[0].id
                                record.trade_id._compute_invoice_count()
                                
                    else:
                        _logger.info(f"ℹ️ No trades found on invoice {record.name}")
                else:
                    _logger.info(f"⏭️ Invoice {record.name} trade_pnl_processed=True, skipping")

        return result

    def action_post(self):
        _logger.info(f"🚀 Posting invoice(s)")
        result = super().action_post()

        for move in self:
            _logger.info(f"📄 Processing posted invoice: {move.name}")

            if move.is_from_sale_order and move.invoice_origin:
                sale_order = self.env['sale.order'].search([('name', '=', move.invoice_origin)], limit=1)
                if sale_order and sale_order.trade_id:
                    _logger.info(f"🔄 Processing sale order invoice from {sale_order.name}")
                    
                    if not move.trade_id:
                        _logger.info(f"📌 Setting invoice trade from sale order")
                        move.trade_id = sale_order.trade_id.id
                        move.trade_id._compute_invoice_count()

                    for invoice_line in move.invoice_line_ids:
                        if invoice_line.product_id and not invoice_line.trade_id:
                            sale_order_line = sale_order.order_line.filtered(lambda l: l.product_id == invoice_line.product_id)
                            
                            if sale_order_line and sale_order_line.trade_id:
                                _logger.info(f"📌 Setting line trade from sale order line")
                                invoice_line.trade_id = sale_order_line.trade_id.id
                                
                            elif sale_order.trade_id:
                                _logger.info(f"📌 Setting line trade from sale order")
                                invoice_line.trade_id = sale_order.trade_id.id

            if move.is_from_purchase_order and move.invoice_origin:
                purchase_order = self.env['purchase.order'].search([('name', '=', move.invoice_origin)], limit=1)
                if purchase_order and purchase_order.trade_id:
                    _logger.info(f"🔄 Processing purchase order invoice from {purchase_order.name}")
                    
                    if not move.trade_id:
                        _logger.info(f"📌 Setting bill trade from purchase order")
                        move.trade_id = purchase_order.trade_id.id
                        move.trade_id._compute_invoice_count()

                    for invoice_line in move.invoice_line_ids:
                        if invoice_line.product_id and not invoice_line.trade_id:
                            purchase_order_line = purchase_order.order_line.filtered(lambda l: l.product_id == invoice_line.product_id)
                            
                            if purchase_order_line and purchase_order_line.trade_id:
                                _logger.info(f"📌 Setting line trade from purchase order line")
                                invoice_line.trade_id = purchase_order_line.trade_id.id
                                
                            elif purchase_order.trade_id:
                                _logger.info(f"📌 Setting line trade from purchase order")
                                invoice_line.trade_id = purchase_order.trade_id.id

        for move in self:
            _logger.info(f"🔍 Checking invoice {move.name} for trade updates")

            if move.trade_id:
                _logger.info(f"📊 Header trade found: {move.trade_id.name}")
                move.trade_id._compute_invoice_count()
                
                if move.is_from_sale_order:
                    _logger.info(f"💰 Updating P&L from sale order")
                    move._update_trade_pnl_from_sale_order()
                    
                elif move.is_from_purchase_order:
                    _logger.info(f"💰 Updating additional costs from purchase order")
                    move._update_trade_additional_costs()
                    
                else:
                    _logger.info(f"💰 Updating P&L from direct invoice")
                    move._update_trade_pnl_from_invoice()
                    
            else:
                _logger.info(f"🔍 No header trade, checking line-level trades")
                move._process_line_level_trades()

        return result

    def button_draft(self):
        """Reverse trade P&L contribution when invoice is reset to draft."""
        for move in self:
            move._reverse_trade_pnl_contribution(move.trade_id)

        return super().button_draft()