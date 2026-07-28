# -*- coding: utf-8 -*-
from odoo import models, fields, api
from markupsafe import Markup


class BudgetCostComputationMixin(models.AbstractModel):
    """Mixin for budget cost computation methods.
    
    Provides all cost calculation methods for budget models.
    Models using this mixin should have:
    - sale_order_id: Many2one to sale.order
    - currency_id: Many2one to res.currency
    - company_id: Many2one to res.company
    - fob_budget_lines, freight_budget_lines, lod_budget_lines: One2many to budget lines
    - has_fob_service, has_freight_service, has_lod_service: Boolean fields
    - All the computed fields that these methods populate
    """
    _name = 'budget.cost.computation.mixin'
    _description = 'Budget Cost Computation Mixin'

    def _get_order(self):
        """Get the connected sale order. Override in models using this mixin."""
        return getattr(self, 'sale_order_id', False)

    @api.depends('sale_order_id', 'currency_id', 'company_id')
    def _compute_charged_amounts(self):
        """Compute charged amounts from the connected quotation, converted to budget currency."""
        for budget in self:
            order = budget._get_order()
            if order:
                order_date = order.date_order or fields.Date.today()
                budget.fob_charged_amount = budget._convert_to_target_currency(
                    getattr(order, 'fob_total_cost_est', 0.0) or 0.0,
                    order.currency_id,
                    order_date
                )
                budget.freight_charged_amount = budget._convert_to_target_currency(
                    getattr(order, 'total_cost_est', 0.0) or 0.0,
                    order.currency_id,
                    order_date
                )
                budget.lod_charged_amount = budget._convert_to_target_currency(
                    getattr(order, 'lod_total_cost_est', 0.0) or 0.0,
                    order.currency_id,
                    order_date
                )
                budget.total_charged_amount = (
                    budget.fob_charged_amount + 
                    budget.freight_charged_amount + 
                    budget.lod_charged_amount
                )
            else:
                budget.fob_charged_amount = 0.0
                budget.freight_charged_amount = 0.0
                budget.lod_charged_amount = 0.0
                budget.total_charged_amount = 0.0

    @api.depends('sale_order_id.full_service_cost', 'total_charged_amount', 'currency_id', 'company_id')
    def _compute_quotation_price(self):
        """Compute quotation price and global markup, converted to budget currency.
        
        The quotation_price is the full_service_cost (set price) which includes
        any global markup applied to the entire quotation.
        """
        for budget in self:
            order = budget._get_order()
            if order:
                order_date = order.date_order or fields.Date.today()
                full_service_cost = getattr(order, 'full_service_cost', 0.0) or 0.0
                
                if full_service_cost > 0:
                    budget.quotation_price = budget._convert_to_target_currency(
                        full_service_cost, order.currency_id, order_date
                    )
                    budget.quotation_margin = budget.quotation_price - budget.total_budgeted_cost
                    budget.quotation_margin_percentage = (
                        (budget.quotation_margin / budget.total_budgeted_cost * 100)
                        if budget.total_budgeted_cost > 0 else 0.0
                    )
                else:
                    budget.quotation_price = budget.total_charged_amount
                    budget.quotation_margin = 0.0
                    budget.quotation_margin_percentage = 0.0
            else:
                budget.quotation_price = budget.total_charged_amount
                budget.quotation_margin = 0.0
                budget.quotation_margin_percentage = 0.0

    @api.depends('fob_budget_lines', 'freight_budget_lines', 'lod_budget_lines',
                 'fob_budget_lines.currency_id', 'freight_budget_lines.currency_id', 
                 'lod_budget_lines.currency_id', 'currency_id', 'company_id')
    def _compute_budgeted_costs(self):
        """Compute budgeted costs from budget lines, converting to budget currency."""
        for budget in self:
            budget.fob_budgeted_cost = budget._convert_budget_lines(
                budget.fob_budget_lines, 'budgeted_amount', 'date_planned'
            )
            budget.freight_budgeted_cost = budget._convert_budget_lines(
                budget.freight_budget_lines, 'budgeted_amount', 'date_planned'
            )
            budget.lod_budgeted_cost = budget._convert_budget_lines(
                budget.lod_budget_lines, 'budgeted_amount', 'date_planned'
            )
            budget.total_budgeted_cost = (
                budget.fob_budgeted_cost + 
                budget.freight_budgeted_cost + 
                budget.lod_budgeted_cost
            )

    @api.depends('fob_budget_lines', 'freight_budget_lines', 'lod_budget_lines',
                 'fob_budget_lines.currency_id', 'freight_budget_lines.currency_id', 
                 'lod_budget_lines.currency_id', 'currency_id', 'company_id')
    def _compute_actual_costs(self):
        """Compute realised costs from budget lines, converting to budget currency.
        
        Sum all actual_amount from budget lines (both expense and charge lines),
        converting each to the budget currency before summing.
        """
        for budget in self:
            # Initialize all costs to 0
            fob_actual_cost = 0.0
            freight_actual_cost = 0.0
            lod_actual_cost = 0.0
            
            # Process FOB budget lines
            for line in budget.fob_budget_lines:
                line_actual = budget._convert_to_target_currency(
                    line.actual_amount, 
                    line.currency_id, 
                    line.date_actual or fields.Date.today()
                )
                if line.line_type != 'other':
                    fob_actual_cost += line_actual
                else:
                    # For 'other' type lines, subtract from actual cost (for reversals/credits)
                    fob_actual_cost -= line_actual
            
            # Process Freight budget lines
            for line in budget.freight_budget_lines:
                line_actual = budget._convert_to_target_currency(
                    line.actual_amount, 
                    line.currency_id, 
                    line.date_actual or fields.Date.today()
                )
                if line.line_type != 'other':
                    freight_actual_cost += line_actual
                else:
                    freight_actual_cost -= line_actual
            
            # Process LOD budget lines
            for line in budget.lod_budget_lines:
                line_actual = budget._convert_to_target_currency(
                    line.actual_amount, 
                    line.currency_id, 
                    line.date_actual or fields.Date.today()
                )
                if line.line_type != 'other':
                    lod_actual_cost += line_actual
                else:
                    lod_actual_cost -= line_actual
            
            # Assign the computed values
            budget.fob_actual_cost = fob_actual_cost
            budget.freight_actual_cost = freight_actual_cost
            budget.lod_actual_cost = lod_actual_cost
            budget.total_actual_cost = (
                budget.fob_actual_cost + 
                budget.freight_actual_cost + 
                budget.lod_actual_cost
            )

    @api.depends('quotation_price', 'production_id',
                 'fob_charged_amount', 'freight_charged_amount', 'lod_charged_amount', 'total_charged_amount')
    def _compute_projected_revenue(self):
        """Compute projected revenue by allocating quotation_price proportionally.
        
        Allocates based on each service's "Total Incl. Margin" (fob_total_cost_est, 
        total_cost_est, lod_total_cost_est) - same as sale order line allocation in 
        three-line quote mode.
        """
        for budget in self:
            if budget.quotation_price > 0 and budget.total_charged_amount > 0:
                # Allocate proportionally based on each service's "Total Incl. Margin"
                # (which is stored in charged_amount fields: fob_total_cost_est, total_cost_est, lod_total_cost_est)
                budget.fob_projected_revenue = (
                    budget.quotation_price * (budget.fob_charged_amount / budget.total_charged_amount)
                    if budget.has_fob_service else 0.0
                )
                budget.freight_projected_revenue = (
                    budget.quotation_price * (budget.freight_charged_amount / budget.total_charged_amount)
                    if budget.has_freight_service else 0.0
                )
                budget.lod_projected_revenue = (
                    budget.quotation_price * (budget.lod_charged_amount / budget.total_charged_amount)
                    if budget.has_lod_service else 0.0
                )
            else:
                budget.fob_projected_revenue = 0.0
                budget.freight_projected_revenue = 0.0
                budget.lod_projected_revenue = 0.0

    @api.depends('fob_projected_revenue', 'fob_actual_cost',
                 'freight_projected_revenue', 'freight_actual_cost',
                 'lod_projected_revenue', 'lod_actual_cost', 'currency_id')
    def _compute_margin_display(self):
        """Compute margin display as "€250 (+8%)" or "-€250 (-8%)" format with superscript."""
        for budget in self:
            currency_symbol = budget.currency_id.symbol if budget.currency_id else ''
            
            # FOB Margin
            fob_margin = budget.fob_projected_revenue - budget.fob_actual_cost
            fob_margin_pct = (
                (fob_margin / budget.fob_projected_revenue) * 100
                if budget.fob_projected_revenue > 0 else 0.0
            )
            budget.fob_margin_display = budget._format_margin_display(fob_margin, fob_margin_pct, currency_symbol)
            
            # Freight Margin
            freight_margin = budget.freight_projected_revenue - budget.freight_actual_cost
            freight_margin_pct = (
                (freight_margin / budget.freight_projected_revenue) * 100
                if budget.freight_projected_revenue > 0 else 0.0
            )
            budget.freight_margin_display = budget._format_margin_display(freight_margin, freight_margin_pct, currency_symbol)
            
            # LOD Margin
            lod_margin = budget.lod_projected_revenue - budget.lod_actual_cost
            lod_margin_pct = (
                (lod_margin / budget.lod_projected_revenue) * 100
                if budget.lod_projected_revenue > 0 else 0.0
            )
            budget.lod_margin_display = budget._format_margin_display(lod_margin, lod_margin_pct, currency_symbol)
            
            # Total Margin
            total_margin = budget.quotation_price - budget.total_actual_cost
            total_margin_pct = (
                (total_margin / budget.quotation_price) * 100
                if budget.quotation_price > 0 else 0.0
            )
            budget.total_margin_display = budget._format_margin_display(total_margin, total_margin_pct, currency_symbol)
    
    @api.depends('fob_projected_revenue', 'fob_budgeted_cost', 'freight_projected_revenue', 'freight_budgeted_cost', 'lod_projected_revenue', 'lod_budgeted_cost', 'total_budgeted_cost', 'quotation_price', 'currency_id')
    def _compute_expected_margin_display(self):
        """Compute margin display as "€250 (+8%)" or "-€250 (-8%)" format with superscript."""
        for budget in self:
            currency_symbol = budget.currency_id.symbol if budget.currency_id else ''
            
            # FOB Margin
            fob_expected_margin = budget.fob_projected_revenue - budget.fob_budgeted_cost
            fob_margin_pct = (
                (fob_expected_margin / budget.fob_budgeted_cost) * 100
                if budget.fob_projected_revenue > 0 else 0.0
            )
            budget.fob_expected_margin_display = budget._format_margin_display(fob_expected_margin, fob_margin_pct, currency_symbol)
            
            # Freight Margin
            freight_expected_margin = budget.freight_projected_revenue - budget.freight_budgeted_cost
            freight_margin_pct = (
                (freight_expected_margin / budget.freight_budgeted_cost) * 100
                if budget.freight_projected_revenue > 0 else 0.0
            )
            budget.freight_expected_margin_display = budget._format_margin_display(freight_expected_margin, freight_margin_pct, currency_symbol)
            
            # DAP Margin
            lod_expected_margin = budget.lod_projected_revenue - budget.lod_budgeted_cost
            lod_margin_pct = (
                (lod_expected_margin / budget.lod_budgeted_cost) * 100
                if budget.lod_projected_revenue > 0 else 0.0
            )
            budget.lod_expected_margin_display = budget._format_margin_display(lod_expected_margin, lod_margin_pct, currency_symbol)
            
            # Total Margin
            total_expected_margin = budget.quotation_price - budget.total_budgeted_cost
            total_margin_pct = budget.quotation_margin_percentage
            budget.total_expected_margin_display = budget._format_margin_display(total_expected_margin, total_margin_pct, currency_symbol)
            

    def _format_margin_display(self, margin_amount, margin_percentage, currency_symbol=None):
        """Format margin as "€381.93 (+14.8%)" or "-€250 (-8.0%)" with superscript percentage."""
        # Get currency symbol if not provided
        if currency_symbol is None:
            currency_symbol = self.currency_id.symbol if self.currency_id else ''
        
        # Format amount with currency symbol
        if abs(margin_amount) < 0.01:
            amount_str = f"{currency_symbol}0"
        else:
            # Format with 2 decimal places, remove trailing zeros but keep at least one decimal if needed
            formatted = f"{margin_amount:,.2f}"
            # Remove trailing zeros but keep .00 if it's exactly .00
            if formatted.endswith('.00'):
                amount_str = formatted[:-3] if margin_amount == int(margin_amount) else formatted.rstrip('0').rstrip('.')
            else:
                amount_str = formatted.rstrip('0').rstrip('.')
            amount_str = f"{currency_symbol}{amount_str}"
        
        # Format percentage with sign, as superscript
        if abs(margin_percentage) < 0.1:
            pct_str = "0%"
        else:
            sign = "+" if margin_percentage >= 0 else ""
            pct_str = f"{sign}{margin_percentage:.2f}%"
        
        # Return with HTML superscript for percentage
        return Markup(f'{amount_str} <sup style="font-weight: normal; font-size: 0.7em;">({pct_str})</sup>')


