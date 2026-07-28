from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from .mixins.service_state_mixin import ServiceStateMixin


class OmniFreightWorkOrder(models.Model, ServiceStateMixin):
    """Extend work orders to support freight operations."""
    _inherit = 'mrp.workorder'

    # === FIELDS ===
    # Workcenter is required for BOM operations, optional for custom operations
    # Override to make it optional while keeping original attributes
    workcenter_id = fields.Many2one(
        'mrp.workcenter', 'Work Center',
        required=False,  # Changed from required=True to allow optional workcenters
        group_expand='_read_group_workcenter_id',  # Keep original group_expand
        check_company=True,
        help="Work center for this operation"
    )
    
    # Freight-specific fields
    freight_service_type = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'Destination')
    ], string='Service Type', compute='_compute_freight_service_type', store=True)

    # Service costs
    service_cost = fields.Float(string='Service Cost', default=0.0, help="Cost for this service operation")
    
    service_state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Service State (deprecated)', help="Deprecated - use state instead")
    # Temporary stub fields for cleanup - will be removed after Odoo deletes old field records
    service_end_date = fields.Datetime(string='Service End Date (deprecated)', help="Deprecated - use date_finished instead")
    service_start_date = fields.Datetime(string='Service Start Date (deprecated)', help="Deprecated - use date_start instead")
    is_service_end_date_manual = fields.Boolean(string='Manual Service End Date (deprecated)', help="Deprecated")
    
    # Documents related to this operation
    document_ids = fields.One2many(
        'omnifreight.documents', 
        'operation_id', 
        string='Documents',
        domain="[('operation_id', '=', operation_id)]"
    )
    
    # Computed fields for formatted date/time display
    date_start_formatted = fields.Html(
        string='Start Date/Time',
        compute='_compute_date_formatted',
        store=False,
        sanitize=False
    )
    
    date_finished_formatted = fields.Html(
        string='End Date/Time',
        compute='_compute_date_formatted',
        store=False,
        sanitize=False
    )

    # === DOMAIN METHODS ===


    # === CONSTRAINTS ===
    @api.constrains('workcenter_id', 'operation_id')
    def _check_workcenter_required(self):
        """Work center is required for regular BOM operations, optional for service BOM operations and custom operations."""
        for wo in self:
            # For custom operations (no operation_id), workcenter is optional
            if not wo.operation_id:
                continue
            # For service BOM operations, workcenter is optional
            if wo.operation_id.bom_id and wo.operation_id.bom_id.type == 'service':
                continue
            # For regular BOM operations, workcenter is required
            if not wo.workcenter_id:
                raise ValidationError(_("Work center is required for regular BOM operations."))

    # === COMPUTE METHODS ===
    @api.depends('operation_id.service_type')
    def _compute_freight_service_type(self):
        """Compute service type from the operation."""
        for wo in self:
            if wo.operation_id and wo.operation_id.service_type:
                wo.freight_service_type = wo.operation_id.service_type
            else:
                wo.freight_service_type = False
    
    @api.depends('date_start', 'date_finished')
    def _compute_date_formatted(self):
        """Format date and time in two rows for display."""
        for wo in self:
            if wo.date_start:
                date_str = wo.date_start.strftime('%m/%d/%Y')
                time_str = wo.date_start.strftime('%H:%M:%S')
                wo.date_start_formatted = f'<div style="white-space: pre-line; line-height: 1.4;">{date_str}<br/>{time_str}</div>'
            else:
                wo.date_start_formatted = ''
            
            if wo.date_finished:
                date_str = wo.date_finished.strftime('%m/%d/%Y')
                time_str = wo.date_finished.strftime('%H:%M:%S')
                wo.date_finished_formatted = f'<div style="white-space: pre-line; line-height: 1.4;">{date_str}<br/>{time_str}</div>'
            else:
                wo.date_finished_formatted = ''

    # === ONCHANGE METHODS ===
    @api.onchange('freight_service_type')
    def _onchange_freight_service_type(self):
        """Set a default workcenter based on service type if none is set."""
        if self.freight_service_type and not self.workcenter_id:
            # Try to find a workcenter with a matching name or create a generic one
            workcenter = self.env['mrp.workcenter'].search([
                ('name', 'ilike', self.freight_service_type)
            ], limit=1)
            if not workcenter:
                # Create a generic workcenter for this service type if none exists
                workcenter = self.env['mrp.workcenter'].create({
                    'name': f'{self.freight_service_type.upper()} Operations',
                    'code': self.freight_service_type.upper(),
                })
            self.workcenter_id = workcenter

    # === CRUD METHODS ===
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to ensure workcenter is set for service operations."""
        for vals in vals_list:
            # If this is a service operation and no workcenter is provided, create one
            if not vals.get('workcenter_id'):
                # Check if this is a service BOM operation
                if vals.get('operation_id'):
                    operation = self.env['mrp.routing.workcenter'].browse(vals['operation_id'])
                    if operation.bom_id and operation.bom_id.type == 'service':
                        # Get the service type from the operation
                        service_type = operation.service_type
                        if service_type:
                            # Try to find or create a workcenter for this service type
                            workcenter = self.env['mrp.workcenter'].search([
                                ('name', 'ilike', service_type)
                            ], limit=1)
                            if not workcenter:
                                workcenter = self.env['mrp.workcenter'].create({
                                    'name': f'{service_type.upper()} Operations',
                                    'code': service_type.upper(),
                                })
                            vals['workcenter_id'] = workcenter.id
                # If this is a custom operation with freight_service_type, create workcenter
                elif vals.get('freight_service_type'):
                    service_type = vals['freight_service_type']
                    workcenter = self.env['mrp.workcenter'].search([
                        ('name', 'ilike', service_type)
                    ], limit=1)
                    if not workcenter:
                        workcenter = self.env['mrp.workcenter'].create({
                            'name': f'{service_type.upper()} Operations',
                            'code': service_type.upper(),
                        })
                    vals['workcenter_id'] = workcenter.id
        
        return super().create(vals_list)


    # === BUSINESS METHODS ===
    def action_start(self):
        """Override start action to log service operation start."""
        result = super().action_start()
        # Track who started the operation
        if not self.started_by_user_id:
            self.started_by_user_id = self.env.user.id
        if self.freight_service_type:
            self.message_post(
                body=_("Started %s service operation") % self.freight_service_type.upper()
            )
        return result

    def action_finish(self):
        """Override finish action to log service operation completion."""
        result = super().action_finish()
        if self.freight_service_type:
            self.message_post(
                body=_("Completed %s service operation") % self.freight_service_type.upper()
            )
        return result

    def button_finish(self):
        """Override button_finish to handle service operations with workcenters."""
        for wo in self:
            # Use standard finish for all operations with workcenters
            super(OmniFreightWorkOrder, wo).button_finish()
        return True

    def _set_dates(self):
        """Override _set_dates to handle all operations with workcenters."""
        for wo in self:
            # Use standard date calculations for all operations with work centers
            super(OmniFreightWorkOrder, wo)._set_dates()

    # === SERVICE STATE MANAGEMENT ===
    # Methods inherited from service.state.mixin
    # Override message target to post to production order
    def _get_message_target(self):
        """Override to post messages to production order instead of workorder."""
        return self.production_id if hasattr(self, 'production_id') and self.production_id else self


