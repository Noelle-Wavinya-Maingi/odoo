# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ServiceScopeMixin(models.AbstractModel):
    """Mixin for service scope functionality in BOMs."""
    _name = 'omni.service.scope.mixin'
    _description = 'Service Scope Mixin'

    # Service scope configuration - determines which service types are included
    service_scope = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'Destination'),
        ('fob_freight', 'FOB + Freight'),
        ('freight_lod', 'Freight + Destination'),
        ('fob_lod', 'FOB + Destination'),
        ('fob_freight_lod', 'FOB + Freight + Destination'),
    ], string='Service Scope', help="Defines which services this BOM covers")

    fob_operation_ids = fields.One2many(
        "mrp.routing.workcenter", "bom_id",
        domain=[("service_type", "=", "fob")],
        string="FOB Operations"
    )

    freight_operation_ids = fields.One2many(
        "mrp.routing.workcenter", "bom_id",
        domain=[("service_type", "=", "freight")],
        string="Freight Operations"
    )

    lod_operation_ids = fields.One2many(
        "mrp.routing.workcenter", "bom_id",
        domain=[("service_type", "=", "lod")],
        string="Destination Operations"
    )

    @api.onchange('service_scope')
    def _onchange_service_scope(self):
        """Update manufacturing operations based on service scope."""
        if not self.service_scope or self.type != 'service':
            return

        # Clear existing operations
        self.operation_ids = [(5, 0, 0)]

        # For service BOMs, don't create operations that require work centers
        # Service operations are handled differently and don't need work orders
        # Load operations from template with appropriate workcenters
        operations_data = self._get_operations_from_template()
        for operation_data in operations_data:
            # Get or create a workcenter for this service type
            workcenter_id = False
            if operation_data.get('service_type'):
                workcenter = self.env['mrp.workcenter'].search([
                    ('name', 'ilike', operation_data['service_type'])
                ], limit=1)
                if not workcenter:
                    workcenter = self.env['mrp.workcenter'].create({
                        'name': f"{operation_data['service_type'].upper()} Operations",
                        'code': operation_data['service_type'].upper(),
                    })
                workcenter_id = workcenter.id
            
            operation_data['workcenter_id'] = workcenter_id
            self.operation_ids = [(0, 0, operation_data)]

    def _get_operations_from_template(self):
        """Fetch operations from service template instead of hardcoding."""
        template = self.env['omni.service.template'].search([
            ('service_scope', '=', self.service_scope),
            ('active', '=', True),
        ], limit=1)

        if not template:
            # Return empty list if no template found
            return []

        return template._get_operations_for_template()

    def action_create_service_operations(self):
        """Create service operations based on current service scope."""
        self.ensure_one()
        if self.type != 'service':
            raise UserError(_("This action is only available for service BOMs."))

        if not self.service_scope:
            raise UserError(_("Please select a service scope first."))

        # Clear existing operations
        self.operation_ids.unlink()

        # Create new operations from template
        operations_data = self._get_operations_from_template()
        for operation_data in operations_data:
            operation_data['bom_id'] = self.id
            
            # Get or create a workcenter for this service type
            workcenter_id = False
            if operation_data.get('service_type'):
                workcenter = self.env['mrp.workcenter'].search([
                    ('name', 'ilike', operation_data['service_type'])
                ], limit=1)
                if not workcenter:
                    workcenter = self.env['mrp.workcenter'].create({
                        'name': f"{operation_data['service_type'].upper()} Operations",
                        'code': operation_data['service_type'].upper(),
                    })
                workcenter_id = workcenter.id
            
            operation_data['workcenter_id'] = workcenter_id
            self.env['mrp.routing.workcenter'].create(operation_data)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Service Operations Created'),
                'message': _('Service operations have been created based on the selected template.'),
                'type': 'success',
            }
        }
