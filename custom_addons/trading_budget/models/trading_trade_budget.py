# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class TradingTradeBudget(models.Model):
    """Budget header for a trade. Exactly one per trade."""
    _name = 'trading.trade.budget'
    _description = 'Trade Budget'
    _order = 'create_date desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _trade_uniq = models.Constraint('unique(trade_id)', 'A trade can only have one budget.')

    name = fields.Char(
        'Budget Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
        index=True
    )
    trade_id = fields.Many2one(
        'trading.trade',
        string='Trade',
        required=True,
        ondelete='cascade',
        index=True
    )
    trade_type = fields.Selection(
        related='trade_id.trade_type',
        string='Trade Type',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    is_fully_matched = fields.Boolean(
        related='trade_id.is_fully_matched',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        tracking=True,
        help='Optional analytic account for future accounting integration'
    )

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('closed', 'Closed'),
    ], string='Status', default='draft', tracking=True, required=True)

    budget_line_ids = fields.One2many(
        'operations.budget.line',
        'budget_id',
        string='Budget Lines'
    )

    # === BUDGETED (PLANNED) ===
    total_budgeted_cost = fields.Monetary(
        string='Budgeted Cost',
        compute='_compute_budgeted_totals',
        store=True,
        currency_field='currency_id',
        help='Sum of budgeted_amount across Cost/Other budget lines'
    )
    total_budgeted_revenue = fields.Monetary(
        string='Budgeted Revenue',
        compute='_compute_budgeted_totals',
        store=True,
        currency_field='currency_id',
        help='Sum of budgeted_amount across Revenue budget lines'
    )

    # === ACTUAL (from the trade's own additional_costs/additional_revenue ledger) ===
    actual_cost = fields.Monetary(
        string='Actual Cost',
        compute='_compute_actuals',
        currency_field='currency_id',
        help='The trade\'s Additional Costs -- kept in sync by the budget lines themselves '
             '(and by any invoices/bills linked directly to the trade)'
    )
    actual_revenue = fields.Monetary(
        string='Actual Revenue',
        compute='_compute_actuals',
        currency_field='currency_id',
        help='The trade\'s Additional Revenue -- kept in sync by the budget lines themselves '
             '(and by any invoices/bills linked directly to the trade)'
    )
    cost_variance = fields.Monetary(
        string='Cost Variance',
        compute='_compute_variances',
        store=True,
        currency_field='currency_id',
        help='Actual Cost minus Budgeted Cost -- positive means over budget'
    )
    revenue_variance = fields.Monetary(
        string='Revenue Variance',
        compute='_compute_variances',
        store=True,
        currency_field='currency_id',
        help='Actual Revenue minus Budgeted Revenue'
    )
    
    target_margin_percent = fields.Float(
        related='trade_id.target_margin_percent',
        readonly=True
    )
    
    target_pnl = fields.Monetary(related='trade_id.target_pnl', readonly=True, currency_field='currency_id')
    total_pnl = fields.Monetary(related='trade_id.total_pnl', readonly=True, currency_field='currency_id', string='Realized Margin')
    margin_pnl_variance = fields.Monetary(related='trade_id.margin_pnl_variance', readonly=True, currency_field='currency_id')
    margin_pnl_variance_percent = fields.Float(related='trade_id.margin_pnl_variance_percent', readonly=True)

    # @api.depends('budget_line_ids.budgeted_amount', 'budget_line_ids.line_type')
    # def _compute_budgeted_totals(self):
    #     for budget in self:
    #         cost_lines = budget.budget_line_ids.filtered(lambda l: l.line_type in ('expense', 'other'))
    #         revenue_lines = budget.budget_line_ids.filtered(lambda l: l.line_type == 'charge')
    #         budget.total_budgeted_cost = sum(cost_lines.mapped('budgeted_amount'))
    #         budget.total_budgeted_revenue = sum(revenue_lines.mapped('budgeted_amount'))
    
    @api.depends('trade_id.total_purchase_cost', 'trade_id.additional_costs', 'trade_id.total_sales_value', 'trade_id.additional_revenue')
    def _compute_actuals(self):
        for budget in self:
            trade = budget.trade_id
            budget.actual_cost = trade.total_purchase_cost + trade.additional_costs
            budget.actual_revenue = trade.total_sales_value + trade.additional_revenue
    
    @api.depends('budget_line_ids.budgeted_amount', 'budget_line_ids.line_type', 'trade_id.trade_type', 'trade_id.quantity', 'trade_id.price', 'trade_id.sales_price', 'trade_id.target_margin_percent')
    def _compute_budgeted_totals(self):
        for budget in self:
            cost_lines = budget.budget_line_ids.filtered(lambda l: l.line_type in ('expense', 'other'))
            revenue_lines = budget.budget_line_ids.filtered(lambda l: l.line_type == 'charge')
            line_cost = sum(cost_lines.mapped('budgeted_amount'))
            line_revenue = sum(revenue_lines.mapped('budgeted_amount'))
            
            trade = budget.trade_id
            margin_fraction = (trade.target_margin_percent / 100.0) if trade.target_margin_percent else 0.0
            
            quoted_cost = 0.0
            quoted_revenue = 0.0
            
            if trade.trade_type == 'long':
                
                quoted_cost = trade.price_in_base_currency * trade.quantity
                
                if margin_fraction:
                    quoted_revenue = quoted_cost * (1 + margin_fraction)
                
            elif trade.trade_type == 'short':
                
                quoted_revenue = trade.sales_price_in_base_currency * trade.quantity
                
                if margin_fraction and (1 + margin_fraction) != 0:
                    quoted_cost = quoted_revenue / (1 + margin_fraction)
                    
                        
            budget.total_budgeted_cost = line_cost or quoted_cost
            
            budget.total_budgeted_revenue = line_revenue or quoted_revenue
            
            

    @api.depends('total_budgeted_cost', 'total_budgeted_revenue', 'trade_id.additional_costs', 'trade_id.additional_revenue')
    def _compute_variances(self):
        for budget in self:
            budget.cost_variance = budget.actual_cost - budget.total_budgeted_cost
            budget.revenue_variance = budget.actual_revenue - budget.total_budgeted_revenue

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('trading.budget') or _('New')
        return super().create(vals_list)

    def action_confirm(self):
        self.ensure_one()
        self.write({'state': 'confirmed'})

    def action_close(self):
        self.ensure_one()
        self.write({'state': 'closed'})
