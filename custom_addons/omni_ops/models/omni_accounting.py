from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html2plaintext


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Field for supplier workflow
    status = fields.Selection(
        selection=[
            ('draft', 'To be Sent for Validation'),
            ('awaiting_validation', 'Awaiting Validation'),
            ('validated', 'Validated'),
            ('posted', 'Posted'),
            ('cancel', 'Cancelled'),
            ('rejected', 'Rejected')
        ],
        string='Draft Status',
        default='draft',
        tracking=True,
        copy=False,
    )
    # Shipment details
    sale_order_ref = fields.Many2one('sale.order', compute="_compute_sale_order_ref", store=True)
    port_of_loading = fields.Many2one('port', string="Port of Loading", related="sale_order_ref.port_of_loading", store=True)
    port_of_dispatch = fields.Many2one('port', string="Port of Discharge", related="sale_order_ref.port_of_dispatch", store=True)
    container_size = fields.Selection(
        string="Container Size", related="sale_order_ref.container_type", store=True)
    no_of_containers = fields.Integer(string="No. of Containers", related="sale_order_ref.no_of_containers", store=True)
    marks = fields.Char(string="Marks/Numbers")
    goods_description = fields.Text(string="Goods Description")
    loading_date = fields.Date(string="Loading/Service Date")
    vessel = fields.Char(string="Vessel Name")
    file_number = fields.Char(string="File Number")
    
    @api.depends('invoice_origin')
    def _compute_sale_order_ref(self):
        for invoice in self:
            sale_order = False
            if invoice.invoice_origin:
                sale_order = self.env['sale.order'].search([
                    ('name', '=', invoice.invoice_origin)
                ], limit=1)
                
            invoice.sale_order_ref = sale_order.id if sale_order else False

    def button_draft(self):
        if any(move.state not in ('cancel', 'posted') for move in self):
            raise UserError(_("Only posted/cancelled journal entries can be reset to draft."))
        if any(move.need_cancel_request for move in self):
            raise UserError(_("You can't reset to draft those journal entries. You need to request a cancellation instead."))

        self._check_draftable()
        # We remove all the analytics entries for this journal
        self.mapped('line_ids.analytic_line_ids').unlink()
        self.mapped('line_ids').remove_move_reconcile()
        self.state = 'draft'
        self.status= 'validated'
    
    def action_send_for_validation_wizard(self):
        """Open wizard to choose validation type"""
        # Use sudo to bypass access rights
        wizard = self.env['account.move.validation.wizard'].sudo().create({
            'move_id': self.id,
        })
        return self._open_wizard(
            'Send for Validation',
            'account.move.validation.wizard',
            res_id=wizard.id,
            context={'default_move_id': self.id},
        )
    
    def _get_validation_request_subject(self):
        """Return the subject used for validation request messages."""
        validation_type = getattr(self, 'validation_type', 'management')
        label = 'Management' if validation_type == 'management' else 'Operations'
        return  f"Note added during {label} Validation Request"
        
    def action_open_validation_confirm_wizard(self):
        """Open wizard to confirm bill validation with the request notes."""
        self.ensure_one()
        
        wizard = self.env['account.move.validation.wizard'].sudo().create({
            'move_id': self.id,
            'validation_type': 'management',
            
            'previous_notes': self._get_validation_notes(),
        })
        
        return self._open_wizard(
            'Confirm Validaton',
            'account.move.validation.wizard',
            res_id=wizard.id,
            context={'default_move_id': self.id, 'validation_confirm_mode': True},
        )
    
    def action_reject_wizard(self):
        """Open wizard to reject bill with reason"""
        self.ensure_one()
        
        return self._open_wizard(
           "Reject Bill",
           'account.move.rejection.wizard',
           context={'default_move_id': self.id}
        )
        
    def action_reject(self, rejection_reason=False):
        """Actually reject the bill with the provided reason"""
        self.ensure_one()
        self.write({'status': 'rejected'})

        # Post message with rejection reason (if provided)
        message_body = f"❌ Bill has been Rejected\nReason: {rejection_reason}" if rejection_reason else "❌ Bill has been Rejected"
        
        self.message_post(
            body=message_body,
            subject="Bill Rejected"
        )

        # Mark any pending activities as done/cancelled
        self._complete_pending_activities()
        
        message = f'Bill has been rejected. Reason: {rejection_reason}' if rejection_reason else 'Bill has been rejected.'
        
        return self._notify('Rejected', message, notification_type='danger')
     
    def action_set_status_validated(self, note=None):
        """Set state to 'validated'"""
        self.ensure_one()
        self.write({'status': 'validated'})
        self._complete_pending_activities()
        
        if note:
            self.message_post(
                body=note,
                subject="Note added during Validation",
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
            )
            
        self.message_post(body="Bill has been validated by management.")
        return self._notify('Success', 'Bill has been validated.')
    # Update AccountMove model methods
    def action_send_for_management_validation(self, management_user_id=None, note=None, validation_type=''):
        """Send to management for validation"""
        self.write({'status': 'awaiting_validation'})
        
        user = self._get_management_user(management_user_id)
        
        # Create activity for the selected user
        self.activity_schedule(
            act_type_xmlid='mail.mail_activity_data_todo',
            summary='Vendor Bill Needs Management Validation',
            user_id=user.id
        )
        
        if note:
            try:
                self.message_post(
                    body=note,
                    subject=self._get_validation_request_subject(),
                    message_type='comment',
                    subtype_xmlid='mail.mt_comment',
                )
                
            except Exception as e:
                print(f"😣 Failed to send active notification: {e}")
        return self._notify('Success', f'Bill sent for management')
        
    def _notify(self, title, message, notification_type='success', close=True):
        """Return a display_notification client action"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': title,
                'message': message,
                'type': notification_type,
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'} if close else None
            },
        }
        
    def _open_wizard(self, name, res_model, res_id=None, context=None):
        """Return an act_window action to open a wizard"""
        action = {
            'name': name,
            'type': 'ir.actions.act_window',
            'res_model': res_model,
            'view_mode': 'form',
            'target': 'new',
            'context': context or {},
        }
        
        if res_id:
            action['res_id'] = res_id
        return action
    
    def _complete_pending_activities(self):
        """Complete any pending activities for the current user on this record"""
        self.activity_ids.filtered(lambda a: not a.date_done).action_done()
        
    def _get_management_user(self, management_user_id=None):
        """Return the user to notify for management validation"""
        if management_user_id:
            return management_user_id
        
        erp_users = self.env.ref('base.group_erp_manager').users.sorted(key=lambda u : u.id)
        
        return erp_users[-1] if erp_users else self.env.user
    
    def _get_validation_notes(self):
        """Return all request notes as a bulleted list"""
        messages = self.message_ids.filtered(lambda m: m.subject and 'Validation Request' in m.subject).sorted('id', reverse=True)
        
        notes = [html2plaintext(msg.body or '').strip() for msg in messages if html2plaintext(msg.body or '').strip()]
        
        return '\n'.join(f'• {note}' for note in notes)
    
    def _create_expense_from_bill(self):
        """Create an expense from the bill"""
        vendor_name = self.partner_id.name or 'Unknown Vendor'
        unique_name = f"Expense from {vendor_name} - Bill: {self.ref}"
        
        # Check if expense already exists
        existing_expense = self.env['hr.expense'].search([
            ('bill_reference', '=', self.ref),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if existing_expense:
            self.message_post(body=f"ℹ️ Expense already exists: {existing_expense.name}")
            return existing_expense, True
        
        # Get current user's employee
        employee = self.env.user.employee_id
        if not employee:
            raise UserError("Current user has no employee record")
        
        # Get product from bill
        if not self.invoice_line_ids:
            raise UserError("No invoice lines found on bill")
        
        bill_product = self.invoice_line_ids[0].product_id
        if not bill_product:
            raise UserError("No product found on invoice lines")
        
        # Calculate amount
        line_amounts_sum = sum(line.price_total for line in self.invoice_line_ids)
        bill_amount = abs(line_amounts_sum) if line_amounts_sum < 0 else line_amounts_sum
        
        # Create expense
        expense = self.env['hr.expense'].create({
            'name': unique_name,
            'price_unit': bill_amount,
            'total_amount_currency': bill_amount,
            'total_amount': bill_amount,
            'quantity': 1,
            'employee_id': employee.id,
            'product_id': bill_product.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'payment_mode': 'company_account',
            'vendor_id': self.partner_id.id,
            'date': self.invoice_date or fields.Date.today(),
            'description': f'Auto-created from Vendor Bill:Vendor: {vendor_name}\nBill Amount: {bill_amount}\nProduct: {bill_product.name}',
            'bill_reference': self.ref,
        })
        return expense, False

    def action_send_for_operations_validation(self):
        """Send to operations for validation - create expense"""
        self.write({'status': 'awaiting_validation'})
        
        expense, already_existed = self._create_expense_from_bill()
        
        if already_existed:
            return self._notify('Info', f"Expense already exists for this bill.", notification_type='info')
        
        # Copy attachments from bill to expense
        self._copy_attachments_to('hr.expense', expense.id)
        self.message_post(body=f"🔧 Sent for Operations Validation. Expense created: {expense.name}.")
        expense.message_post(body=f"📎 Created from Vendor Bill of reference: {self.ref}")
        
        return self._notify('Success', 'Expense created and sent for operations validation.')
    
    # Optional: Add a method to automatically validate bill when expense is approved
    def _validate_from_expense_approval(self):
        """Called when related expense is approved"""
        if self.status == 'awaiting_validation':
            self.write({'status': 'validated'})
            self.message_post(body="✅ Bill validated automatically from approved expense.")
    
    def action_duplicate_bill_line(self):
        """Duplicate only ONE line (the first line) each time the button is clicked"""
        self.ensure_one()
        if not self.invoice_line_ids:
            return self._notify('Info', "No lines found to duplicate.", notification_type='warning', close=False)
        
        # Duplicate the last line if the bill
        self.invoice_line_ids[-1].copy()
        
        return self._notify('Success', f'Duplicated 1 line. Total lines: {len(self.invoice_line_ids) + 1}.')
    
    def _copy_attachments_to(self, res_model, res_id):
        """Copy attachments from the bill to another record"""
        bill_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'account.move'),
            ('res_id', '=', self.id)
        ])
        
        for attachment in bill_attachments:
            # Create a copy of the attachment linked to the expense
            self.env['ir.attachment'].create({
                'name': attachment.name,
                'datas': attachment.datas,
                'type': attachment.type,
                'res_model': res_model,
                'res_id': res_id,
            })