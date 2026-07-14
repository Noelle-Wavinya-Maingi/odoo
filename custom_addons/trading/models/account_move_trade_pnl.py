from odoo import models

class AccountMoveTradePnl(models.Model):
    """The actual business logic that pushes invoice/bill amounts into a trade's additional_costs / additional_revenue and triggers P&L recomputation."""
    _inherit = 'account.move'

    def _update_trade_additional_costs(self):
        """Update trade with additional costs from a PO-linked vendor bill. The trade quantity/price are already set from PO confirmation. Only pick up non-product lines as additional costs, converted to trade reporting currency."""
        self.ensure_one()

        if not self.trade_id:
            return
        if self.state != 'posted':
            return
        if self.trade_pnl_processed:
            return

        trade = self.trade_id

        total_additional_cost = 0.0
        for line in self.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note', 'tax'):
                continue
            # Skip the trade product line — quantity/price already set from PO confirmation
            if line.product_id == trade.product_id:
                continue
            # Only add non-product lines as additional costs
            line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
            if line_total > 0:
                total_additional_cost += line_total

        if total_additional_cost > 0:
            old_costs = trade.additional_costs
            trade.write({'additional_costs': trade.additional_costs + total_additional_cost})
            trade._compute_all_trade_fields()
            self.trade_pnl_processed = True
        else:
            # No additional costs on this bill — still mark as processed so it doesn't re-fire
            self.trade_pnl_processed = True

        if trade.is_fully_matched and trade.status == 'confirmed':
            trade.status = 'closed'

    def _update_trade_pnl_from_invoice(self):
        """Update trade P&L based on direct invoice/bill (not from a SO or PO). All amounts are converted to the trade's reporting currency."""
        self.ensure_one()

        if not self.trade_id:
            return
        if self.trade_pnl_processed:
            return

        trade = self.trade_id
        is_bill = self.move_type in ['in_invoice', 'in_refund']
        is_invoice = self.move_type in ['out_invoice', 'out_refund']


        if is_bill:
            if self.state == 'posted':

                total_quantity = 0.0
                total_amount = 0.0
                total_additional_cost = 0.0

                for line in self.invoice_line_ids:
                    if line.display_type in ('line_section', 'line_note', 'tax'):
                        continue
                    if line.product_id == trade.product_id:
                        total_quantity += line.quantity
                        total_amount += self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    else:
                        line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                        if line_total > 0:
                            total_additional_cost += line_total

                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({'additional_costs': trade.additional_costs + total_additional_cost})

                if total_quantity > 0:
                    avg_price = total_amount / total_quantity

                    if trade.quantity > 0:
                        total_cost = (trade.quantity * trade.price_in_base_currency) + total_amount
                        total_qty = trade.quantity + total_quantity
                        trade.write({'quantity': total_qty, 'price': total_cost / total_qty if total_qty > 0 else 0})
                    else:
                        trade.write({'quantity': total_quantity, 'price': avg_price})

                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True
                elif total_additional_cost > 0:
                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True

        elif is_invoice and not self.is_from_sale_order:
            if self.state == 'posted':

                total_amount = 0.0
                for line in self.invoice_line_ids:
                    if line.display_type in ('line_section', 'line_note', 'tax'):
                        continue
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    if line_total > 0:
                        total_amount += line_total

                if total_amount > 0:
                    old_revenue = trade.additional_revenue
                    trade.write({'additional_revenue': trade.additional_revenue + total_amount})
                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True

        if trade.is_fully_matched and trade.status == 'confirmed':
            trade.status = 'closed'

    def _update_trade_pnl_from_sale_order(self):
        """Update trade P&L based on sale order invoice. Revenue is already captured via sale_order_ids — just link and recompute."""
        self.ensure_one()

        if not self.trade_id or not self.is_from_sale_order:
            return
        if self.trade_pnl_processed:
            return

        trade = self.trade_id

        if self.state == 'posted':
            sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
            if not sale_order:
                return

            # Ensure sale order is linked to the trade
            if sale_order not in trade.sale_order_ids:
                trade.write({'sale_order_ids': [(4, sale_order.id)]})

            if not sale_order.trade_id:
                sale_order.trade_id = trade.id

            trade._compute_all_trade_fields()
            self.trade_pnl_processed = True

    def _process_line_level_trades(self):
        """Process trades from invoice lines for direct invoices/bills with no SO/PO origin. All amounts are converted to the trade's reporting currency."""
        self.ensure_one()

        if self.state != 'posted':
            return
        if self.trade_pnl_processed:
            return


        trades_to_update = {}
        for line in self.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note', 'tax'):
                continue
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


        for trade_id, trade_data in trades_to_update.items():
            trade = trade_data['trade']
            lines = trade_data['lines']
            is_bill = trade_data['is_bill']
            is_customer_invoice = trade_data['is_customer_invoice']


            if is_bill:
                total_additional_cost = 0.0
                for line in lines:
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    total_additional_cost += line_total

                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({'additional_costs': trade.additional_costs + total_additional_cost})
                    trade._compute_all_trade_fields()

            elif is_customer_invoice:
                total_additional_revenue = 0.0
                for line in lines:
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    total_additional_revenue += line_total

                if total_additional_revenue > 0:
                    old_revenue = trade.additional_revenue
                    trade.write({'additional_revenue': trade.additional_revenue + total_additional_revenue})
                    trade._compute_all_trade_fields()

        if trades_to_update:
            self.trade_pnl_processed = True

        for trade_data in trades_to_update.values():
            trade = trade_data['trade']
            if trade.is_fully_matched and trade.status == 'confirmed':
                trade.status = 'closed'
