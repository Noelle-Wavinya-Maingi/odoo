from odoo import models, fields, api

class AccountMoveValidationWizard(models.TransientModel):
    _name = 'account.move.validation.wizard'
    _description = 'Bill Validation Wizard'
    
    move_id = fields.Many2one('account.move', string='Bill', required=True)
    validation_type = fields.Selection([
        ('management', 'Management Validation'),
        ('operations', 'Operations Validation')
    ], string='Validation Type', required=True, default='management')
    
    # Field to select management user
    management_user_id = fields.Many2one(
        'res.users', 
        string='Notify User',
        domain="[('share', '=', False)]",  # Only internal users, not portal users
        help="Select the user to notify for management validation"
    )
    
    note = fields.Text(string="Notes", help="Field to log a note when sending for validation and when validated.")
    # Field to display previous notes in validation confirm mode
    previous_notes = fields.Text(string="Previous Notes", readonly=True)
    is_validation_confirm_mode = fields.Boolean(compute='_compute_is_validation_confirm_mode')
    
    @api.model
    def default_get(self, fields_list):
        """Set default management user to last ERP Manager"""
        result = super().default_get(fields_list)
        
        if 'management_user_id' in fields_list:
            erp_manager_group = self.env.ref('base.group_erp_manager')
            erp_users = erp_manager_group.users.sorted(key=lambda u: u.id)
            if erp_users:
                result['management_user_id'] = erp_users[-1].id

        return result

    @api.depends_context('validation_confirm_mode')
    def _compute_is_validation_confirm_mode(self):
        for wizard in self:
            wizard.is_validation_confirm_mode = bool(self.env.context.get('validation_confirm_mode'))

    def action_confirm(self):
        """Process the selected validation type"""
        self.ensure_one()

        if self.is_validation_confirm_mode:
            return self.move_id.action_set_status_validated(note=self.note)
        
        if self.validation_type == 'management':
            # Pass the management_user_id to the method
            return self.move_id.action_send_for_management_validation(self.management_user_id, self.note, validation_type=self.validation_type,)
        else:  # operations
            return self.move_id.action_send_for_operations_validation()


class AccountMoveRejectionWizard(models.TransientModel):
    _name = 'account.move.rejection.wizard'
    _description = 'Bill Rejection Wizard'
    
    move_id = fields.Many2one('account.move', string='Bill', required=True)
    rejection_reason = fields.Text(
        string='Rejection Reason',
        help='Please provide a detailed reason for the rejection'
    )
    
    def action_confirm(self):
        """Confirm rejection with the provided reason"""
        self.ensure_one()
        
        return self.move_id.action_reject(self.rejection_reason)
