# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime


class OmnifreightDocuments(models.Model):
    _name = 'omnifreight.documents'
    _description = 'Omnifreight Documents'
    _inherit = ['mail.thread']
    _rec_name = 'name'
    _order = 'create_date desc'

    # === FIELDS ===
    document_upload = fields.Binary(
        string="Document", 
        required=True,
        help="Upload your document file"
    )
    
    filename = fields.Char(
        string="Filename",
        help="Original filename of the uploaded file",
    )
    production_id = fields.Many2one(
        'mrp.production', 
        string="Manufacturing Order",
        help="Related manufacturing order"
    )
    operation_id = fields.Many2one(
        'mrp.routing.workcenter', 
        string="Operation ID",
        help="Related operation"
    )
    workcenter_id = fields.Many2one(
        'mrp.workcenter',
        string="Work Center",
        related='operation_id.workcenter_id',
        store=True,
        help="Work center for this document"
    )
    is_done = fields.Boolean(
        string="Mark as Done",
        default=False,
        help="Check this when the document processing is complete"
    )
    done_date = fields.Datetime(
        string="Done Date",
        help="Date when the document was marked as done"
    )
    done_by = fields.Many2one(
        'res.users',
        string="Done By",
        help="User who marked the document as done"
    )
    user_id = fields.Many2one(
        'res.users', 
        string="Uploaded By", 
        default=lambda self: self.env.user,
        required=True,
        help="User who uploaded the document"
    )
    upload_date = fields.Datetime(
        string="Upload Date",
        default=fields.Datetime.now,
        readonly=True,
        help="Date and time when the document was uploaded"
    )
    
    name = fields.Char(
        string="Document Name",
        compute='_compute_name',
        store=True,
        help="Computed name for the document"
    )


    # === COMPUTE METHODS ===
    @api.depends('filename', 'production_id', 'upload_date')
    def _compute_name(self):
        """Compute the name field based on filename, production order, and upload date."""
        for record in self:
            if record.filename:
                record.name = record.filename
            elif record.production_id:
                record.name = f"Document for {record.production_id.name} - {record.upload_date.strftime('%Y-%m-%d %H:%M') if record.upload_date else 'Unknown Date'}"
            else:
                record.name = f"Document - {record.upload_date.strftime('%Y-%m-%d %H:%M') if record.upload_date else 'Unknown Date'}"

    # === ONCHANGE METHODS ===
    @api.onchange('is_done')
    def _onchange_is_done(self):
        """Handle mark as done functionality."""
        if self.is_done and not self.done_date:
            self.done_date = fields.Datetime.now()
            self.done_by = self.env.user.id
        elif not self.is_done:
            self.done_date = False
            self.done_by = False

    # === BUSINESS METHODS ===
    def action_mark_done(self):
        """Mark document as done."""
        for record in self:
            record.write({
                'is_done': True,
                'done_date': fields.Datetime.now(),
                'done_by': self.env.user.id
            })
            record.message_post(
                body=_("Document marked as done by %s") % self.env.user.name
            )
        return True

    def action_mark_undone(self):
        """Mark document as not done."""
        for record in self:
            record.write({
                'is_done': False,
                'done_date': False,
                'done_by': False
            })
            record.message_post(
                body=_("Document marked as not done by %s") % self.env.user.name
            )
        return True

    # === CRUD METHODS ===
    @api.model_create_multi
    def create(self, vals_list):
        """Create documents."""
        for vals in vals_list:
            # Set default user if not provided
            if not vals.get('user_id'):
                vals['user_id'] = self.env.user.id
            
            # Set upload date
            if not vals.get('upload_date'):
                vals['upload_date'] = fields.Datetime.now()
        
        return super().create(vals_list)

    def unlink(self):
        """Override unlink to remove chatter attachments and post notifications."""
        
        # Store operation orders and filenames before deletion
        production_attachments = {}
        
        for document in self:
            if document.production_id:
                production_id = document.production_id.id
                
                if production_id not in production_attachments:
                    production_attachments[production_id] = {
                        'production': document.production_id,
                        'filenames': [],
                        'attachment_ids': [] 
                    }
                    
                production_attachments[production_id]['filenames'].append(document.filename)
                
        # Find and store the attachment IDs to delete
        for production_data in production_attachments.values():
            if production_data['filenames']:
                attachments = self.env['ir.attachment'].search([
                    ('res_model', '=', 'mrp.production'),
                    ('res_id', '=', production_data['production'].id),
                    ('name', 'in', production_data['filenames'])
                ])
            production_data['attachment_ids'] = attachments.ids
            
        # Delete the documents
        result = super().unlink()
        
        
        # Remove related attachments and post notifications
        for production_data in production_attachments.values():
            if production_data['attachment_ids']:
                self.env['ir.attachment'].browse(production_data['attachment_ids']).unlink()
                
            if production_data['filenames']:
                removed_files = "\n".join([f"- {fname}" for fname in production_data['filenames']])
                production_data['production'].message_post(
                    body=_("The following document(s) were removed:\n%s") % removed_files,
                    message_type='notification',
                )
        return result
    