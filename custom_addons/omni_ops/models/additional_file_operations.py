from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime


class AdditionalFileOperations(models.Model):
    _name = 'additional.file.operations'
    _description = 'Additional File Operations'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'service.state.mixin']
    _rec_name = 'operation_title'
    _order = 'sequence, id'

    # === FIELDS ===
    sequence = fields.Integer(string='Sequence', default=100, help="Sequence for ordering operations")
    production_id = fields.Many2one(
        'mrp.production', 
        string='Manufacturing Order',
        required=True,
        ondelete='cascade',
        index=True,
        check_company=True,
        help="Production order this operation belongs to")
    operation_title = fields.Char(string='Operation Title', required=True, tracking=True)
    operation_description = fields.Html(string='Operation Description', help="Detailed instructions for this operation", tracking=True)
    operation_duration = fields.Float(string='Expected Duration', help="Expected duration in minutes")
    actual_duration = fields.Float(
        string='Actual Duration', 
        compute='_compute_actual_duration',
        store=True,
        help="Actual duration in minutes (computed from start and end dates)")
    operation_center = fields.Many2one(
        'mrp.workcenter', 
        string='Work Center',
        check_company=True,
        tracking=True,
        help="Work center for this operation")
    service_type = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'Destination')
    ], string='Service Type', help="Type of service operation", tracking=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='State', default='pending', tracking=True)
    date_start = fields.Datetime(string='Start Date', tracking=True, help="When the operation was started")
    date_finished = fields.Datetime(string='End Date', tracking=True, help="When the operation was completed or cancelled")
    is_end_date_manual = fields.Boolean(string='Manual End Date', default=False)
    is_start_date_manual = fields.Boolean(string='Manual Start Date', default=False)
    is_duration_manual = fields.Boolean(string='Manual Duration', default=False)
    
    # Temporary stub fields for cleanup - will be removed after Odoo deletes old field records
    # These allow the mail module to access fields during unlink without errors
    service_end_date = fields.Datetime(string='Service End Date (deprecated)', help="Deprecated - use date_finished instead")
    service_start_date = fields.Datetime(string='Service Start Date (deprecated)', help="Deprecated - use date_start instead")
    
    service_state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Service State (deprecated)', help="Deprecated - use state instead")
    is_service_end_date_manual = fields.Boolean(string='Manual Service End Date (deprecated)', help="Deprecated - use is_end_date_manual instead")
    is_service_start_date_manual = fields.Boolean(string='Manual Service Start Date (deprecated)', help="Deprecated - use is_start_date_manual instead")
    is_service_duration_manual = fields.Boolean(string='Manual Service Duration (deprecated)', help="Deprecated - use is_duration_manual instead")
    
    # Company field for multi-company support
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='production_id.company_id',
        store=True,
        readonly=True)
    
    # === COMPUTE METHODS ===
    @api.depends('date_start', 'date_finished')
    def _compute_actual_duration(self):
        """Compute actual duration from start and end dates."""
        for record in self:
            if record.date_start and record.date_finished:
                delta = record.date_finished - record.date_start
                # Convert to minutes
                record.actual_duration = delta.total_seconds() / 60.0
            else:
                record.actual_duration = 0.0
    
    # === CRUD METHODS ===
    @api.model_create_multi
    def create(self, vals_list):
        """Override create to add logging."""
        records = super().create(vals_list)
        for record in records:
            record.message_post(
                body=_("Additional operation '%s' was created by %s") % (record.operation_title, self.env.user.name),
                subtype_xmlid='mail.mt_note'
            )
        return records
    
    def write(self, vals):
        """Override write to add logging for important field changes."""
        # Track important changes for logging - need to check before write
        start_date_changes = {}
        end_date_changes = {}
        
        if 'date_start' in vals and vals.get('date_start'):
            for record in self:
                if not record.date_start:  # Only log if it's being set for the first time
                    start_date_changes[record.id] = record
        if 'date_finished' in vals and vals.get('date_finished'):
            for record in self:
                if not record.date_finished:  # Only log if it's being set for the first time
                    end_date_changes[record.id] = record
        
        result = super().write(vals)
        
        # Post messages after write
        for record_id, record in start_date_changes.items():
            record.message_post(
                body=_("Start date was set by %s") % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )
        for record_id, record in end_date_changes.items():
            record.message_post(
                body=_("End date was set by %s") % self.env.user.name,
                subtype_xmlid='mail.mt_note'
            )
        
        return result
    
    # === SERVICE STATE MANAGEMENT ===
    # Methods inherited from service.state.mixin
    # Override to customize name shown in messages
    def _get_service_operation_name(self):
        """Override to use operation_title instead of name."""
        return self.operation_title or str(self.id)
    
    def _get_message_target(self):
        """Override to post messages to production order instead of operation."""
        # Post messages to the production order so they appear in the MO's chatter
        return self.production_id if self.production_id else self