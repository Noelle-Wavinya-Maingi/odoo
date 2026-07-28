import logging
from odoo import models

_logger = logging.getLogger(__name__)


class AccountMoveTradePnl(models.Model):
    """The actual business logic that pushes invoice/bill amounts into a trade's additional_costs / additional_revenue and triggers P&L recomputation."""
    _inherit = 'account.move'

    def _update_trade_additional_costs(self):
        """Update trade with additional costs from a PO-linked vendor bill. The trade quantity/price are already set from PO confirmation. Only pick up non-product lines as additional costs, converted to trade reporting currency."""
        self.ensure_one()

        if not self.trade_id:
            _logger.warning(f"⚠️ No trade on bill {self.name}, skipping")
            return
        if self.state != 'posted':
            _logger.info(f"⏭️ Bill {self.name} not posted yet, skipping")
            return
        if self.trade_pnl_processed:
            _logger.info(f"⏭️ Bill {self.name} already processed, skipping")
            return

        trade = self.trade_id
        _logger.info(f"💰 Processing PO bill {self.name} for trade {trade.name}")

        total_additional_cost = 0.0
        for line in self.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note', 'tax'):
                continue
            # Skip the trade product line — quantity/price already set from PO confirmation
            if line.product_id == trade.product_id:
                _logger.info(
                    f"  ⏭️ Skipping trade product line: {line.product_id.name} "
                    f"(quantity/price already set from PO confirmation)"
                )
                continue
            # Only add non-product lines as additional costs
            line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
            if line_total > 0:
                total_additional_cost += line_total
                _logger.info(
                    f"  🚚 Additional cost line: {line.product_id.name if line.product_id else 'Unknown'} "
                    f"- {line_total} {trade.currency_id.name if trade.currency_id else ''}"
                )

        if total_additional_cost > 0:
            old_costs = trade.additional_costs
            trade.write({'additional_costs': trade.additional_costs + total_additional_cost})
            _logger.info(f"✅ Additional costs: {old_costs} → {trade.additional_costs} (+{total_additional_cost})")
            trade._sync_budget_line_for_move(self, 'additional_costs', total_additional_cost)
            trade._compute_all_trade_fields()
            self.trade_pnl_processed = True
            _logger.info(f"✅ Trade recalculation complete")
        else:
            # No additional costs on this bill — still mark as processed so it doesn't re-fire
            _logger.info(f"ℹ️ No additional cost lines on bill {self.name} (product lines skipped — handled by PO confirmation)")
            self.trade_pnl_processed = True

        if trade.is_fully_matched and trade.status == 'confirmed':
            trade.status = 'closed'
            _logger.info(f"🔒 Trade {trade.name} auto-closed as fully matched")

    def _update_trade_pnl_from_invoice(self):
        """Update trade P&L based on direct invoice/bill (not from a SO or PO). All amounts are converted to the trade's reporting currency."""
        self.ensure_one()

        if not self.trade_id:
            _logger.warning(f"⚠️ No trade found on invoice {self.name}")
            return
        if self.trade_pnl_processed:
            _logger.info(f"⏭️ Invoice {self.name} already processed, skipping")
            return

        trade = self.trade_id
        is_bill = self.move_type in ['in_invoice', 'in_refund']
        is_invoice = self.move_type in ['out_invoice', 'out_refund']

        _logger.info(f"💰 Updating trade {trade.name} from {'Bill' if is_bill else 'Invoice'} {self.name}")

        if is_bill:
            if self.state == 'posted':
                _logger.info(f"📊 Processing bill in posted state")

                total_quantity = 0.0
                total_amount = 0.0
                total_additional_cost = 0.0

                for line in self.invoice_line_ids:
                    if line.display_type in ('line_section', 'line_note', 'tax'):
                        continue
                    if line.product_id == trade.product_id:
                        total_quantity += line.quantity
                        total_amount += self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                        _logger.info(f"  📦 Product line: {line.product_id.name} - Qty: {line.quantity}, Price: {line.price_unit}")
                    else:
                        line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                        if line_total > 0:
                            total_additional_cost += line_total
                            _logger.info(f"  🚚 Additional cost line: {line.product_id.name if line.product_id else 'Unknown'} - {line_total}")

                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({'additional_costs': trade.additional_costs + total_additional_cost})
                    _logger.info(f"✅ Additional costs: {old_costs} → {trade.additional_costs} (+{total_additional_cost})")
                    trade._sync_budget_line_for_move(self, 'additional_costs', total_additional_cost)

                if total_quantity > 0:
                    avg_price = total_amount / total_quantity
                    _logger.info(f"📊 Purchase update: Qty={total_quantity}, Avg Price={avg_price} {trade.currency_id.name if trade.currency_id else ''}")

                    if trade.quantity > 0:
                        total_cost = (trade.quantity * trade.price_in_base_currency) + total_amount
                        total_qty = trade.quantity + total_quantity
                        trade.write({'quantity': total_qty, 'price': total_cost / total_qty if total_qty > 0 else 0})
                        _logger.info(f"✅ Trade updated (existing): Qty={trade.quantity}, Price={trade.price}")
                    else:
                        trade.write({'quantity': total_quantity, 'price': avg_price})
                        _logger.info(f"✅ Trade updated (new): Qty={trade.quantity}, Price={trade.price}")

                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True
                    _logger.info(f"✅ Trade recalculation complete")
                elif total_additional_cost > 0:
                    _logger.info(f"🔄 Only additional costs added, recalculating...")
                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True

        elif is_invoice and not self.is_from_sale_order:
            if self.state == 'posted':
                _logger.info(f"💵 Processing direct sale invoice → adding to additional revenue")
                _logger.info(f"   Invoice currency: {self.currency_id.name if self.currency_id else 'None'}")
                _logger.info(f"   Trade currency: {trade.currency_id.name if trade.currency_id else 'None'}")
                _logger.info(f"   Invoice date: {self.invoice_date}")
                _logger.info(f"   Total invoice lines: {len(self.invoice_line_ids)}")

                total_amount = 0.0
                for line in self.invoice_line_ids:
                    _logger.info(f"   Line: display_type={line.display_type}, product={line.product_id.name if line.product_id else 'None'}, price={line.price_unit}, qty={line.quantity}")
                    if line.display_type in ('line_section', 'line_note', 'tax'):
                        _logger.info(f"   → Skipping (display_type={line.display_type})")
                        continue
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    _logger.info(f"   → line_total after conversion: {line_total}")
                    if line_total > 0:
                        total_amount += line_total

                if total_amount > 0:
                    old_revenue = trade.additional_revenue
                    trade.write({'additional_revenue': trade.additional_revenue + total_amount})
                    _logger.info(f"✅ Additional revenue: {old_revenue} → {trade.additional_revenue} (+{total_amount}) [{trade.currency_id.name if trade.currency_id else ''}]")
                    trade._sync_budget_line_for_move(self, 'additional_revenue', total_amount)
                    trade._compute_all_trade_fields()
                    self.trade_pnl_processed = True
                    _logger.info(f"✅ Trade recalculation complete")
                else:
                    _logger.info(f"ℹ️ No revenue found on invoice {self.name}")

        if trade.is_fully_matched and trade.status == 'confirmed':
            trade.status = 'closed'
            _logger.info(f"🔒 Trade {trade.name} auto-closed as fully matched")

    def _update_trade_pnl_from_sale_order(self):
        """Update trade P&L based on sale order invoice. Revenue is already captured via sale_order_ids — just link and recompute."""
        self.ensure_one()

        if not self.trade_id or not self.is_from_sale_order:
            _logger.warning(f"⚠️ Cannot update from sale order: No trade or not from SO")
            return
        if self.trade_pnl_processed:
            _logger.info(f"⏭️ Invoice {self.name} already processed, skipping")
            return

        trade = self.trade_id

        if self.state == 'posted':
            _logger.info(f"💰 Updating trade {trade.name} from sale order invoice {self.name}")
            sale_order = self.env['sale.order'].search([('name', '=', self.invoice_origin)], limit=1)
            if not sale_order:
                _logger.warning(f"⚠️ Sale order {self.invoice_origin} not found")
                return

            # Ensure sale order is linked to the trade
            if sale_order not in trade.sale_order_ids:
                _logger.info(f"🔗 Linking sale order {sale_order.name} to trade")
                trade.write({'sale_order_ids': [(4, sale_order.id)]})

            if not sale_order.trade_id:
                sale_order.trade_id = trade.id

            _logger.info(f"🔄 Recalculating trade fields (revenue from SO, not from invoice lines)...")
            trade._compute_all_trade_fields()
            self.trade_pnl_processed = True
            _logger.info(f"✅ Trade recalculation complete")

    def _process_line_level_trades(self):
        """Process trades from invoice lines for direct invoices/bills with no SO/PO origin. All amounts are converted to the trade's reporting currency."""
        self.ensure_one()

        if self.state != 'posted':
            _logger.info(f"⏭️ Skipping line-level trades for invoice {self.name} (state={self.state}, not posted)")
            return
        if self.trade_pnl_processed:
            _logger.info(f"⏭️ Invoice {self.name} already processed, skipping")
            return

        _logger.info(f"🔍 Processing line-level trades for invoice {self.name} (Type: {self.move_type}, State: {self.state})")

        trades_to_update = {}
        for line in self.invoice_line_ids:
            if line.display_type in ('line_section', 'line_note', 'tax'):
                continue
            if line.trade_id:
                trade = line.trade_id
                _logger.info(f"🎯 Found line with trade: {trade.name} - Product: {line.product_id.name if line.product_id else 'No product'} - Qty: {line.quantity} - Price: {line.price_unit}")
                if trade.id not in trades_to_update:
                    trades_to_update[trade.id] = {
                        'trade': trade,
                        'lines': [],
                        'is_bill': self.move_type in ['in_invoice', 'in_refund'],
                        'is_customer_invoice': self.move_type in ['out_invoice', 'out_refund']
                    }
                trades_to_update[trade.id]['lines'].append(line)

        _logger.info(f"📊 Found {len(trades_to_update)} unique trades to process")

        for trade_id, trade_data in trades_to_update.items():
            trade = trade_data['trade']
            lines = trade_data['lines']
            is_bill = trade_data['is_bill']
            is_customer_invoice = trade_data['is_customer_invoice']

            _logger.info(f"{'💰' if is_bill else '💵'} Processing trade {trade.name} from {len(lines)} invoice lines")

            if is_bill:
                total_additional_cost = 0.0
                for line in lines:
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    total_additional_cost += line_total
                    _logger.info(f"   🚚 Vendor Bill line: {line_total} {trade.currency_id.name if trade.currency_id else ''} - adding to additional costs")

                if total_additional_cost > 0:
                    old_costs = trade.additional_costs
                    trade.write({'additional_costs': trade.additional_costs + total_additional_cost})
                    _logger.info(f"➕ ADDITIONAL COSTS: {old_costs} → {trade.additional_costs} (+{total_additional_cost})")
                    trade._sync_budget_line_for_move(self, 'additional_costs', total_additional_cost)
                    trade._compute_all_trade_fields()
                    _logger.info(f"✅ Trade recalculated - New Total P&L: {trade.total_pnl}")

            elif is_customer_invoice:
                total_additional_revenue = 0.0
                for line in lines:
                    line_total = self._convert_to_trade_currency(line.price_unit * line.quantity, trade)
                    total_additional_revenue += line_total
                    _logger.info(f"   💵 Customer Invoice line: {line_total} {trade.currency_id.name if trade.currency_id else ''} - adding to additional revenue")

                if total_additional_revenue > 0:
                    old_revenue = trade.additional_revenue
                    trade.write({'additional_revenue': trade.additional_revenue + total_additional_revenue})
                    _logger.info(f"➕ ADDITIONAL REVENUE: {old_revenue} → {trade.additional_revenue} (+{total_additional_revenue})")
                    trade.sync_budget_line_for_move(self, 'additional_revenue', total_additional_revenue)
                    trade._compute_all_trade_fields()
                    _logger.info(f"✅ Trade recalculated - New Total P&L: {trade.total_pnl}")

        if trades_to_update:
            self.trade_pnl_processed = True

        for trade_data in trades_to_update.values():
            trade = trade_data['trade']
            if trade.is_fully_matched and trade.status == 'confirmed':
                trade.status = 'closed'
                _logger.info(f"🔒 Trade {trade.name} auto-closed as fully matched")