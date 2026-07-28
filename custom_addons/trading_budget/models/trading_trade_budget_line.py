# -*- coding: utf-8 -*-
from odoo import fields, models


class TradingTradeBudgetLine(models.Model):
    """Trading-specific extension of the shared operations.budget.line: adds the
    budget_id anchor (the trading.trade.budget header -- one per trade) and pushes
    actual amounts into the trade's existing additional_costs/additional_revenue
    ledger (the same fields already maintained by account_move_trade_pnl.py /
    account_move_lifecycle.py for invoice/bill-driven P&L).
    """
    _inherit = 'operations.budget.line'

    budget_id = fields.Many2one(
        'trading.trade.budget',
        string='Budget',
        required=True,
        ondelete='cascade',
        index=True
    )
    trade_id = fields.Many2one(
        'trading.trade',
        string='Trade',
        related='budget_id.trade_id',
        store=True,
        index=True
    )

    pnl_contributed_amount = fields.Float(default=0.0)
    pnl_contributed_field = fields.Char(default=False)

    def _get_anchor_record(self):
        return self.budget_id

    def _get_anchor_expense_vals(self):
        if not self.trade_id:
            return {}
        return {'trade_id': self.trade_id.id}

    def _get_display_name_prefix(self):
        return self.trade_id.name or ''

    def _get_conversion_company(self):
        return self.trade_id.company_id or self.env.company

    def _get_target_currency(self):
        return self.trade_id.currency_id or self.currency_id

    def _notify_anchor_of_amount_change(self):
        self._sync_pnl_contribution()

    def _get_pnl_target(self):
        self.ensure_one()
        if not self.trade_id or self.account_move_id:
            return None
        if self.line_type == 'expense':
            return ('additional_costs', self.actual_amount)
        if self.line_type == 'other':
            return ('additional_costs', -self.actual_amount)
        if self.line_type == 'charge':
            return ('additional_revenue', self.actual_amount)
        return None

    def _sync_pnl_contribution(self):
        for line in self:
            if not isinstance(line.id, int):
                continue
            trade = line.trade_id
            if not trade:
                continue

            if line.pnl_contributed_amount and line.pnl_contributed_field:
                current = trade[line.pnl_contributed_field]
                trade.write({line.pnl_contributed_field: max(current - line.pnl_contributed_amount, 0.0)})

            target = line._get_pnl_target()
            bookkeeping_vals = {'pnl_contributed_amount': 0.0, 'pnl_contributed_field': False}
            if target:
                field_name, amount = target
                current = trade[field_name]
                trade.write({field_name: current + amount})
                bookkeeping_vals = {'pnl_contributed_amount': amount, 'pnl_contributed_field': field_name}

            if (line.pnl_contributed_amount, line.pnl_contributed_field) != (
                bookkeeping_vals['pnl_contributed_amount'], bookkeeping_vals['pnl_contributed_field']
            ):
                line.sudo().with_context(skip_expense_update=True).write(bookkeeping_vals)

            trade._compute_all_trade_fields()

    def unlink(self):
        for line in self:
            trade = line.trade_id
            if trade and line.pnl_contributed_amount and line.pnl_contributed_field:
                current = trade[line.pnl_contributed_field]
                trade.write({line.pnl_contributed_field: max(current - line.pnl_contributed_amount, 0.0)})
                trade._compute_all_trade_fields()
        return super().unlink()