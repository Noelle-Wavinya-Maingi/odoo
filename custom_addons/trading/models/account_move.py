import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    """Core field definitions and shared helpers for trade-linked invoices/bills."""
    _inherit = 'account.move'
    
    trade_id = fields.Many2one('trading.trade', string='Trade', help='Related trade for this move')
    is_from_purchase_order = fields.Boolean(string="From Purchase Order", compute='_compute_is_from_order', store=True)
    is_from_sale_order = fields.Boolean(string="From Sale Order", compute='_compute_is_from_order', store=True)
    trade_pnl_processed = fields.Boolean(string='Trade P&L Processed', default=False, copy=False, help='Whether this invoice has been processed for trade P&L')

    @api.depends('purchase_id', 'invoice_origin')
    def _compute_is_from_order(self):
        """Determine if the invoice is from a purchase order or sale order"""
        for move in self:

            # Purchase order detection: check purchase_id first, then invoice_origin as fallback
            _logger.info(f"🔍 Computing order source for invoice {move.name or 'Draft'}")
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
                _logger.info(f"🔄 Propagating trade from sale order {sale_order.name} to invoice {move.name}")
                move.trade_id = sale_order.trade_id.id

    def _convert_to_trade_currency(self, amount, trade):
        """Convert an amount from this invoice's currency to the trade's reporting currency
        using the invoice date as the rate date."""
        invoice_currency = self.currency_id
        trade_currency = trade.currency_id
        
        if not invoice_currency or not trade_currency or invoice_currency == trade_currency:
            return amount
        
        company = trade.company_id or self.env.company
        rate_date = self.invoice_date or fields.Date.context_today(self)
        
        converted = invoice_currency._convert(amount, trade_currency, company, rate_date)
        _logger.info(f"💱 Invoice {self.name}: {amount} {invoice_currency.name} " f"→ {converted} {trade_currency.name} (rate date: {rate_date})")
        return converted