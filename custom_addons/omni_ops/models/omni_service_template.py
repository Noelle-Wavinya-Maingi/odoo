# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class OmniServiceTemplate(models.Model):
    """Service operation templates for quick BOM creation."""
    _name = 'omni.service.template'
    _description = 'Service Operation Template'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'sequence, id'
    _check_company_auto = True

    # === FIELDS ===
    name = fields.Char('Template Name', required=True, index=True)
    active = fields.Boolean('Active', default=True)
    sequence = fields.Integer('Sequence', default=100)
    company_id = fields.Many2one( 
        'res.company', 'Company',
        default=lambda self: self.env.company,
        index=True
    )
    
    # Service scope
    service_scope = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'Destination'),
        ('fob_freight', 'FOB + Freight'),
        ('freight_lod', 'Freight + Destination'),
        ('fob_lod', 'FOB + Destination'),
        ('fob_freight_lod', 'FOB + Freight + Destination'),
    ], string='Service Scope', required=True)
    
    # Template operations
    template_operation_ids = fields.One2many(
        'omni.service.template.operation', 'template_id', 'Template Operations',
        copy=True
    )
    
    # Description
    description = fields.Text('Description', help="Description of this service template")

    # === BUSINESS METHODS ===
    def action_create_bom_from_template(self):
        """Create a BOM from this template."""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create BOM from Template'),
            'res_model': 'mrp.bom',
            'view_mode': 'form',
            'context': {
                'default_type': 'service',
                'default_service_scope': self.service_scope,
                'default_name': f"BOM - {self.name}",
                'template_id': self.id,
            },
            'target': 'new',
        }

    def _get_operations_for_template(self):
        """Get operations data for this template."""
        operations_data = []
        for operation in self.template_operation_ids:
            operations_data.append({
                'name': operation.name,
                'service_type': operation.service_type,
                'time_cycle_manual': operation.duration * 60,  # Convert hours to minutes
                'note': operation.description or '',
                'is_mandatory': operation.is_mandatory,
                'requires_documentation': operation.requires_documentation,
                'cost_per_hour': operation.cost_per_hour,
            })
        return operations_data


class OmniServiceTemplateOperation(models.Model):
    """Individual operations within a service template."""
    _name = 'omni.service.template.operation'
    _description = 'Service Template Operation'
    _order = 'sequence, id'

    # === FIELDS ===
    name = fields.Char('Operation Name', required=True)
    sequence = fields.Integer('Sequence', default=100)
    template_id = fields.Many2one(
        'omni.service.template', 'Template',
        ondelete='cascade', required=True
    )
    
    # Service type
    service_type = fields.Selection([
        ('fob', 'FOB Operations'),
        ('freight', 'Freight Operations'),
        ('lod', 'Destination Operations'),
    ], string='Service Type', required=True)
    
    # Operation details
    duration = fields.Float('Duration (hours)', default=1.0)
    cost_per_hour = fields.Float('Cost per Hour', default=0.0)
    description = fields.Text('Description')
    is_mandatory = fields.Boolean('Mandatory', default=True)
    requires_documentation = fields.Boolean('Requires Documentation', default=False)

    # === CONSTRAINTS ===
    @api.constrains('duration', 'cost_per_hour')
    def _check_positive_values(self):
        """Validate positive values."""
        for record in self:
            if record.duration < 0:
                raise ValidationError(_("Duration must be positive."))
            if record.cost_per_hour < 0:
                raise ValidationError(_("Cost per hour must be positive."))
