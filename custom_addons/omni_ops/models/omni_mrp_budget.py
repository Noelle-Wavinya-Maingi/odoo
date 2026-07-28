# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from .mixins.currency_conversion_mixin import CurrencyConversionMixin
from .mixins.budget_cost_computation_mixin import BudgetCostComputationMixin
import logging

_logger = logging.getLogger(__name__)


class OmniMrpBudget(models.Model, CurrencyConversionMixin, BudgetCostComputationMixin):
    _name = 'omni.mrp.budget'
    _description = 'Manufacturing Order Budget'
    _order = 'sequence, create_date desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # === BASIC FIELDS ===
    sequence = fields.Integer('Sequence', default=10, help='Order of budgets')
    name = fields.Char(
        'Budget Reference', 
        required=True, 
        copy=False, 
        readonly=True, 
        default=lambda self: _('New'),
        index=True
    )
    production_id = fields.Many2one(
        'mrp.production', 
        string='Manufacturing Order', 
        required=True, 
        ondelete='cascade',
        index=True
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        compute='_compute_sale_order_id',
        store=True,
        help='Connected sale order from production'
    )
    # Service scope flags from production order
    has_fob_service = fields.Boolean(
        string='Has FOB Service',
        related='production_id.has_fob_service',
        store=True,
        readonly=True
    )
    has_freight_service = fields.Boolean(
        string='Has Freight Service',
        related='production_id.has_freight_service',
        store=True,
        readonly=True
    )
    has_lod_service = fields.Boolean(
        string='Has LOD Service',
        related='production_id.has_lod_service',
        store=True,
        readonly=True
    )
    currency_id = fields.Many2one(
        'res.currency', 
        string='Currency', 
        required=True, 
        default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        'res.company', 
        string='Company', 
        required=True, 
        default=lambda self: self.env.company
    )
    
    # === BUDGET STATUS ===
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('closed', 'Closed')
    ], string='Status', default='draft', tracking=True, required=True)
    
    # === OPTIONAL ACCOUNTING INTEGRATION ===
    analytic_account_id = fields.Many2one(
        'account.analytic.account',
        string='Analytic Account',
        tracking=True,
        help='Optional analytic account for future accounting integration'
    )
    
    # === CHARGES FROM QUOTATION ===
    fob_charged_amount = fields.Float(
        'FOB Charged', 
        compute='_compute_charged_amounts', 
        store=True,
        digits=(16, 2)
    )
    freight_charged_amount = fields.Float(
        'Freight Charged', 
        compute='_compute_charged_amounts', 
        store=True,
        digits=(16, 2)
    )
    lod_charged_amount = fields.Float(
        'LOD Charged', 
        compute='_compute_charged_amounts', 
        store=True,
        digits=(16, 2)
    )
    total_charged_amount = fields.Float(
        'Total Charged', 
        compute='_compute_charged_amounts', 
        store=True,
        digits=(16, 2)
    )
    
    # === QUOTATION PRICE (GLOBAL MARKUP) ===
    quotation_price = fields.Float(
        'Quotation Price', 
        compute='_compute_quotation_price', 
        store=True,
        digits=(16, 2),
        help='The set price (full_service_cost) from quotation, includes global markup'
    )
    quotation_margin = fields.Float(
        'Quotation Margin', 
        compute='_compute_quotation_price', 
        store=True,
        digits=(16, 2),
        help='Global markup amount (quotation_price - total_charged_amount)'
    )
    quotation_margin_percentage = fields.Float(
        'Quotation Margin %', 
        compute='_compute_quotation_price', 
        store=True,
        digits=(16, 4),  # 4 decimal places for percentage precision (0.0001% = 0.000001 stored)
        help='Global markup percentage'
    )
    
    # === BUDGETED COSTS ===
    fob_budgeted_cost = fields.Float(
        'FOB Budgeted Cost', 
        compute='_compute_budgeted_costs', 
        store=True,
        digits=(16, 2)
    )
    freight_budgeted_cost = fields.Float(
        'Freight Budgeted Cost', 
        compute='_compute_budgeted_costs', 
        store=True,
        digits=(16, 2)
    )
    lod_budgeted_cost = fields.Float(
        'LOD Budgeted Cost', 
        compute='_compute_budgeted_costs', 
        store=True,
        digits=(16, 2)
    )
    total_budgeted_cost = fields.Float(
        'Total Budgeted Cost', 
        compute='_compute_budgeted_costs', 
        store=True,
        digits=(16, 2)
    )
    
    # === REALISED COSTS ===
    fob_actual_cost = fields.Float(
        'FOB Realised Cost', 
        compute='_compute_actual_costs', 
        store=True,
        digits=(16, 2)
    )
    freight_actual_cost = fields.Float(
        'Freight Realised Cost', 
        compute='_compute_actual_costs', 
        store=True,
        digits=(16, 2)
    )
    lod_actual_cost = fields.Float(
        'LOD Realised Cost', 
        compute='_compute_actual_costs', 
        store=True,
        digits=(16, 2)
    )
    total_actual_cost = fields.Float(
        'Total Realised Cost', 
        compute='_compute_actual_costs', 
        store=True,
        digits=(16, 2)
    )
    
    # === BUDGET LINES ===
    fob_budget_lines = fields.One2many(
        'operations.budget.line',
        'budget_id',
        string='FOB Budget Lines',
        domain=[('service_type', '=', 'fob')]
    )
    freight_budget_lines = fields.One2many(
        'operations.budget.line',
        'budget_id',
        string='Freight Budget Lines',
        domain=[('service_type', '=', 'freight')]
    )
    lod_budget_lines = fields.One2many(
        'operations.budget.line',
        'budget_id',
        string='LOD Budget Lines',
        domain=[('service_type', '=', 'lod')]
    )
    all_budget_lines = fields.One2many(
        'operations.budget.line',
        'budget_id',
        string='All Budget Lines'
    )
    
    # === PROJECTED REVENUE (ALLOCATED FROM QUOTATION PRICE) ===
    fob_projected_revenue = fields.Float(
        'FOB Projected Revenue', 
        compute='_compute_projected_revenue', 
        store=True,
        digits=(16, 2),
        help='Revenue allocated to FOB service from quotation price (divided by number of active services)'
    )
    freight_projected_revenue = fields.Float(
        'Freight Projected Revenue', 
        compute='_compute_projected_revenue', 
        store=True,
        digits=(16, 2),
        help='Revenue allocated to Freight service from quotation price (divided by number of active services)'
    )
    lod_projected_revenue = fields.Float(
        'LOD Projected Revenue', 
        compute='_compute_projected_revenue', 
        store=True,
        digits=(16, 2),
        help='Revenue allocated to LOD service from quotation price (divided by number of active services)'
    )
    
    # === MARGIN DISPLAY (FORMATTED AS "250 (+8%)" OR "-250 (-8%)") ===
    fob_margin_display = fields.Html(
        'FOB Margin', 
        compute='_compute_margin_display', 
        store=True,
        sanitize=False,
        help='Margin displayed as amount with percentage, e.g., "250 (+8%)" or "-250 (-8%)"'
    )
    fob_expected_margin_display = fields.Html(
        'FOB Expected Margin',
        compute='_compute_expected_margin_display',
        store=True,
        sanitize=False,
        help='Expected margin displayed as amount with percentage, e.g., "250 (+8%)" or "-250 (-8%)"'
    )
    freight_margin_display = fields.Html(
        'Freight Margin', 
        compute='_compute_margin_display', 
        store=True,
        sanitize=False,
        help='Margin displayed as amount with percentage, e.g., "250 (+8%)" or "-250 (-8%)"'
    )
    freight_expected_margin_display = fields.Html(
        'Freight Expected Margin',
        compute="_compute_expected_margin_display",
        store=True,
        sanitize=False,
        help="Expected Margin displayed as amount with percentage, e.g., '250 (+8%)' or '-250 (-8%)'"
    )
    lod_margin_display = fields.Html(
        'LOD Margin', 
        compute='_compute_margin_display', 
        store=True,
        sanitize=False,
        help='Margin displayed as amount with percentage, e.g., "250 (+8%)" or "-250 (-8%)"'
    )
    lod_expected_margin_display = fields.Html(
        'LOD Expected Margin',
        compute="_compute_expected_margin_display",
        store=True,
        sanitize=False,
        help="Expected Margin displayed as amount with percentage, e.g., '250 (+8%)' or '-250 (-8%)'"
    )
    total_margin_display = fields.Html(
        'Total Margin', 
        compute='_compute_margin_display', 
        store=True,
        sanitize=False,
        help='Total margin displayed as amount with percentage, e.g., "250 (+8%)" or "-250 (-8%)"'
    )
    total_expected_margin_display = fields.Html(
        'Total Expected Margin',
        compute="_compute_expected_margin_display",
        store=True,
        sanitize=False,
        help="Total Expected Margin displayed as amount with percentage, e.g., '250 (+8%)' or '-250 (-8%)'"
    )
    
    # === METHODS ===
    
    @api.depends('production_id')
    def _compute_sale_order_id(self):
        """Compute sale order from production order."""
        for budget in self:
            budget.sale_order_id = (
                budget.production_id.sale_line_id.order_id
                if budget.production_id.sale_line_id else False
            )
    
    def _get_order(self):
        """Get the connected sale order."""
        return self.sale_order_id
    
    @api.model_create_multi
    def create(self, vals_list):
        """Generate budget reference number (batch-safe)."""
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('omni.mrp.budget') or _('New')
        return super().create(vals_list)
    
    def action_confirm(self):
        """Confirm the budget."""
        self.ensure_one()
        self.write({'state': 'confirmed'})
    
    def action_close(self):
        """Close the budget."""
        self.ensure_one()
        self.write({'state': 'closed'})
    
    def action_copy_charges_from_quotation(self):
        """Copy charges and expenses from the connected quotation to create initial budget lines."""
        self.ensure_one()
        
        order = self._get_order()
        if not order:
            raise ValidationError(_("No quotation found to copy charges from."))
        
        # Clear existing budget lines
        self.all_budget_lines.unlink()
        
        # Create budget lines from quotation charges and expenses
        budget_lines = []
        
        # FOB Service Charge (use base cost as budgeted amount)
        # Note: fob_base_cost already includes special costs via fob_misc_cost
        fob_base_cost = getattr(order, 'fob_base_cost', 0.0)
        if fob_base_cost > 0:
            budget_lines.append({
                'budget_id': self.id,
                'service_type': 'fob',
                'name': 'FOB Service Charges',
                'budgeted_amount': fob_base_cost,
                'actual_amount': 0.0,
                'line_type': 'expense',
                'currency_id': order.currency_id.id,
            })
        
        # Freight Service Charge (use base cost as budgeted amount)
        # Note: freight_base_cost already includes special costs via misc_costs
        freight_base_cost = getattr(order, 'freight_base_cost', 0.0)
        if freight_base_cost > 0:
            budget_lines.append({
                'budget_id': self.id,
                'service_type': 'freight',
                'name': 'Freight Service Charges',
                'budgeted_amount': freight_base_cost,
                'actual_amount': 0.0,
                'line_type': 'expense',
                'currency_id': order.currency_id.id,
            })
        
        # LOD/DAP Service Charge (use base cost as budgeted amount)
        # Note: lod_total_cost already includes special costs via lod_misc_cost
        lod_base_cost = getattr(order, 'lod_total_cost', 0.0)
        if lod_base_cost > 0:
            budget_lines.append({
                'budget_id': self.id,
                'service_type': 'lod',
                'name': 'DAP Service Charges',
                'budgeted_amount': lod_base_cost,
                'actual_amount': 0.0,
                'line_type': 'expense',
                'currency_id': order.currency_id.id,
            })
        
        if budget_lines:
            self.env['operations.budget.line'].create(budget_lines)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

