from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class OmniMrpRoutingWorkcenter(models.Model):
    """Extend manufacturing operations to support service operations without work centers."""
    _inherit = 'mrp.routing.workcenter'

    # === FIELDS ===
    # Service type for freight forwarding operations
    service_type = fields.Selection([
        ('fob', 'FOB'),
        ('freight', 'Freight'),
        ('lod', 'Destination')
    ], string='Service Type', help="Type of service operation (FOB, Freight, or Destination)")
    
    # Service operation specific fields
    cost_per_hour = fields.Float('Cost per Hour', default=0.0, help="Cost per hour for this service operation")
    state = fields.Selection([
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='State', default='pending', tracking=True)
    
    # Date fields for operation tracking
    start_date = fields.Datetime('Start Date', tracking=True, help="When the operation was started")
    end_date = fields.Datetime('End Date', tracking=True, help="When the operation was completed or cancelled")
    is_end_date_manual = fields.Boolean('Manual End Date', default=False, help="Whether end date was set manually")

    # Workcenter is required
    workcenter_id = fields.Many2one(
        'mrp.workcenter', 'Work Center',
        check_company=True, index=True, required=True,
        help="Work center for this operation"
    )

    # Documents tied to the operation
    document_ids = fields.One2many(
        'omnifreight.documents',
        'operation_id',
        string="Documents"
    )
    # === COMPUTE METHODS ===
    @api.depends('state', 'is_end_date_manual')
    def _compute_end_date(self):
        """Compute end date based on state and manual setting."""
        for operation in self:
            if operation.state in ['done', 'cancel'] and not operation.is_end_date_manual:
                operation.end_date = fields.Datetime.now()

    # === ONCHANGE METHODS ===
    @api.onchange('end_date')
    def _onchange_end_date(self):
        """Mark end date as manual when user changes it."""
        if self.end_date:
            self.is_end_date_manual = True

    # === CONSTRAINTS ===
    @api.constrains('state', 'start_date', 'end_date')
    def _check_operation_dates(self):
        """Validate operation dates and state consistency."""
        for operation in self:
            if operation.state == 'in_progress' and not operation.start_date:
                raise ValidationError(_("Start date is required when operation is in progress."))
            
            if operation.state in ['done', 'cancel'] and not operation.end_date:
                raise ValidationError(_("End date is required when operation is completed or cancelled."))
            
            if operation.start_date and operation.end_date and operation.start_date > operation.end_date:
                raise ValidationError(_("Start date cannot be after end date."))

    # === BUSINESS METHODS ===
    # --- individual actions (used internally by the cycle method) ---

    def _do_start(self):
        for op in self:
            if op.state != 'pending':
                raise ValidationError(_("Only pending operations can be started."))
            vals = {'state': 'in_progress'}
            if not op.start_date:
                vals['start_date'] = fields.Datetime.now()
            op.write(vals)
            op.message_post(body=_("Operation started by %s") % self.env.user.name)

    def _do_done(self):
        for op in self:
            if op.state not in ('pending', 'in_progress'):
                raise ValidationError(_("Only pending or in-progress operations can be marked as done."))
            vals = {'state': 'done'}
            # respect manual end_date
            if not op.is_end_date_manual and not op.end_date:
                vals['end_date'] = fields.Datetime.now()
            op.write(vals)
            op.message_post(body=_("Operation completed by %s") % self.env.user.name)

    def _do_cancel(self):
        for op in self:
            # per your requirement: Cancel only allowed when state is done
            if op.state != 'done':
                raise ValidationError(_("Only completed operations can be cancelled."))
            vals = {'state': 'cancel'}
            if not op.is_end_date_manual and not op.end_date:
                vals['end_date'] = fields.Datetime.now()
            op.write(vals)
            op.message_post(body=_("Operation cancelled by %s") % self.env.user.name)

    # --- public single action button called from the list/tree ---
    def action_cycle_state(self):
        """
        Single button that acts depending on current state:
          pending -> start (in_progress)
          in_progress -> done (done)
          done -> cancel (cancel)
        """
        for op in self:
            if op.state == 'pending':
                op._do_start()
            elif op.state == 'in_progress':
                op._do_done()
            elif op.state == 'done':
                op._do_cancel()
            else:
                # either cancel or unknown state: raise or ignore
                op.state = 'pending'
        return True

    # --- keep write override to support dropdown changes from the badge widget ----
    def write(self, vals):
        if 'state' not in vals:
            return super().write(vals)

        # handle per-record to respect existing dates and manual flags
        for rec in self:
            local_vals = dict(vals)
            new_state = local_vals.get('state')

            if new_state == 'in_progress' and not rec.start_date:
                local_vals.setdefault('start_date', fields.Datetime.now())

            if new_state in ('done', 'cancel'):
                if not local_vals.get('end_date') and not rec.end_date and not rec.is_end_date_manual:
                    local_vals.setdefault('end_date', fields.Datetime.now())

            if new_state == 'pending':
                local_vals.update({
                    'start_date': False,
                    'end_date': False,
                    'is_end_date_manual': False,
                })

            # call write for that record only
            super(OmniMrpRoutingWorkcenter, rec).write(local_vals)

        return True
            