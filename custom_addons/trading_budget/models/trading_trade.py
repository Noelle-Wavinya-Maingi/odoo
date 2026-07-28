# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class TradingTradeBudgetBridge(models.Model):
    """Adds the optional Trade Budget feature onto trading.trade. Lives in
    the 'trading_budget' bridge module (depends on both 'trading' and
    'budgets') so that installing/uninstalling this feature never touches
    core Trading."""
    _inherit = 'trading.trade'

    # ── Budget header (trading_trade_budget.py) -- exactly one per trade ──
    budget_ids = fields.One2many('trading.trade.budget', 'trade_id', string='Budgets')
    budget_id = fields.Many2one(
        'trading.trade.budget',
        string='Budget',
        compute='_compute_budget_id',
        store=True
    )
    has_budget = fields.Boolean('Has Budget', compute='_compute_has_budget', store=True)
    budget_state = fields.Selection(related='budget_id.state', string='Budget Status', readonly=True)

    @api.depends('budget_ids')
    def _compute_has_budget(self):
        for record in self:
            record.has_budget = bool(record.budget_ids)

    @api.depends('budget_ids')
    def _compute_budget_id(self):
        for record in self:
            record.budget_id = record.budget_ids[:1].id if record.budget_ids else False

    def action_create_budget(self):
        """Create the (single) budget for this trade."""
        self.ensure_one()
        if self.budget_ids:
            raise ValidationError(_("This trade already has a budget."))

        budget = self.env['trading.trade.budget'].create({
            'trade_id': self.id,
            'currency_id': self.currency_id.id,
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget'),
            'res_model': 'trading.trade.budget',
            'res_id': budget.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_budget(self):
        """View this trade's budget."""
        self.ensure_one()
        if not self.budget_id:
            raise ValidationError(_("No budget found for this trade."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Budget'),
            'res_model': 'trading.trade.budget',
            'res_id': self.budget_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _sync_budget_line_for_move(self, move, field_name, amount):
        """Real implementation, overriding the no-op stub in core trading.trade.
        Auto-create/update a budget line representing this invoice/bill's
        contribution, so the Budget tab's line list reflects real postings
        without manual entry. Only runs if this trade already has a budget --
        never creates one on someone's behalf just because a bill posted.
        Safe against double-counting: account_move_id being set makes the
        line's own _get_pnl_target() return None, so it never separately
        contributes to additional_costs/additional_revenue -- the move's own
        posting (already reflected in `amount`) is the only contribution.
        """
        self.ensure_one()
        if not self.budget_id:
            return

        BudgetLine = self.env['operations.budget.line']
        existing = BudgetLine.search([
            ('budget_id', '=', self.budget_id.id),
            ('account_move_id', '=', move.id),
        ], limit=1)

        line_type = 'charge' if field_name == 'additional_revenue' else 'expense'

        vals = {
            'name': move.name or move.ref or 'Invoice/Bill',
            'line_type': line_type,
            'actual_amount': abs(amount),
            'account_move_id': move.id,
            'partner_id': move.partner_id.id if move.partner_id else False,
            'date_actual': move.invoice_date or move.date,
        }

        if existing:
            existing.write(vals)
        else:
            vals['budget_id'] = self.budget_id.id
            BudgetLine.create(vals)

    def _remove_budget_line_for_move(self, move):
        """Real implementation, overriding the no-op stub in core trading.trade.
        Drop the auto-created budget line when a move's contribution is
        reversed (Draft/unlinked from trade)."""
        self.ensure_one()

        if not self.budget_id:
            return

        self.env['operations.budget.line'].search([
            ('budget_id', '=', self.budget_id.id),
            ('account_move_id', '=', move.id)
        ]).unlink()