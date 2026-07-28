# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class OmniMrpBudgetLine(models.Model):
    """Freight-specific extension of the shared operations.budget.line: adds the
    omni.mrp.budget header anchor and the FOB/Freight/LOD service-type split. All
    expense-management, tracking, and CRUD behavior comes from the base model in the
    operations module — this file only supplies freight's own anchor and hooks."""
    _inherit = 'operations.budget.line'
    _order = 'service_type, sequence, id'

    budget_id = fields.Many2one(
        'omni.mrp.budget',
        string='Budget',
        required=True,
        ondelete='cascade',
        index=True
    )

    # === SERVICE TYPE ===
    service_type = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'LOD (Destination)')
    ], string='Service Type', required=True, index=True, default='fob')

    @api.model
    def default_get(self, fields_list):
        """Set default service_type based on context."""
        res = super().default_get(fields_list)

        if 'default_service_type' in self.env.context:
            service_type = self.env.context.get('default_service_type')
            if service_type in ('fob', 'freight', 'lod'):
                res['service_type'] = service_type
        elif 'default_fob_operation' in self.env.context:
            res['service_type'] = 'fob'
        elif 'default_freight_operation' in self.env.context:
            res['service_type'] = 'freight'
        elif 'default_lod_operation' in self.env.context:
            res['service_type'] = 'lod'

        return res

    @api.constrains('service_type')
    def _check_service_type(self):
        """Ensure service_type is valid and preserved."""
        for line in self:
            if line.service_type not in ('fob', 'freight', 'lod'):
                raise ValidationError(_("Invalid service type '%s' for budget line '%s'.") % (line.service_type, line.name))

    # === ANCHOR HOOKS ===
    def _get_anchor_record(self):
        return self.budget_id

    def _get_anchor_expense_vals(self):
        production = self.budget_id.production_id if self.budget_id else False
        if not production:
            return {}
        return {'production_id': production.id}

    def _get_display_name_prefix(self):
        production = self.budget_id.production_id if self.budget_id else False
        return production.name if production else ''

    def _notify_anchor_of_amount_change(self):
        if self.budget_id:
            self.budget_id._compute_actual_costs()
            self.budget_id._compute_margin_display()

    def _get_conversion_company(self):
        if self.budget_id and self.budget_id.company_id:
            return self.budget_id.company_id
        return self.env.company

    def _get_target_currency(self):
        return self._get_conversion_company().currency_id
