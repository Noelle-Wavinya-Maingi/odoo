from odoo import fields, models, api
from odoo.exceptions import ValidationError
# from odoo.orm import Constraint
import json
import logging

_logger = logging.getLogger(__name__)


class IndustryType(models.Model):
    """Master data for industry types"""
    _name = 'industry.type'
    _description = 'Industry Type'
    _order = 'sequence, name'
    
    name = fields.Char(string='Industry Name', required=True, translate=True)
    code = fields.Selection([
        ('shipping', 'Shipping & Logistics'),
        ('trading', 'Trading & Distribution'),
        ('manufacturing', 'Manufacturing'),
        ('construction', 'Construction'),
        ('services', 'Services'),
        ('retail', 'Retail'),
        ('healthcare', 'Healthcare'),
        ('agriculture', 'Agriculture'),
        ('mining', 'Mining'),
        ('energy', 'Energy'),  
    ], string='Industry Code', required=True)
    
    sequence = fields.Integer(string='Sequence', default=10)
    active = fields.Boolean(string='Active', default=True)
    
    # Operation Configuration
    default_operation_type = fields.Selection([
        ('project', 'Project Based'),
        ('continuous', 'Continuous Operations'),
        ('batch', 'Batch Processing'),
        ('job', 'Job Based'),
    ], string='Default Operation Type', required=True)
    
    # Feature Flags
    requires_voyage = fields.Boolean(string='Requires Voyage Management', default=False)
    requires_lot = fields.Boolean(string='Requires Lot/Batch Tracking', default=False)
    requires_production = fields.Boolean(string='Requires Production Management', default=False)
    requires_quality = fields.Boolean(string='Requires Quality Control', default=False)
    requires_inspection = fields.Boolean(string='Requires Inspection Management', default=False)
    requires_budgeting = fields.Boolean(string='Requires Budgeting', default=True)
    
    # Document and Sequence Settings
    document_template = fields.Text(
        string='Document Template', 
        help='JSON structure for industry-specific documents'
    )
    sequence_prefix = fields.Char(string='Sequence Prefix', default='OP')
    sequence_padding = fields.Integer(string='Sequence Padding', default=5)
    
    # Accounting Fields - These need proper dependency checking
    industry_income_account = fields.Many2one(
        'account.account', 
        string='Industry Income Account',
        domain="[('deprecated', '=', False), ('account_type', 'in', ('income', 'other_income'))]",
        help="Default income account for this industry"
    )
    industry_expense_account = fields.Many2one(
        'account.account', 
        string='Industry Expense Account',
        domain="[('deprecated', '=', False), ('account_type', 'in', ('expense', 'other_expense'))]",
        help="Default expense account for this industry"
    )
    industry_journal_id = fields.Many2one(
        'account.journal', 
        string='Industry Journal',
        domain="[('type', 'in', ['sale', 'purchase', 'general'])]",
        help="Default journal for this industry"
    )
    
    # Workflow Configuration
    workflow_stages = fields.One2many(
        'workflow.stage', 
        'industry_id', 
        string='Workflow Stages',
        help="Default workflow stages for this industry"
    )
    
    # UI Configuration
    dashboard_config = fields.Text(
        string='Dashboard Configuration', 
        default='{}', 
        help='JSON configuration for industry dashboard'
    )
    field_visibility = fields.Text(
        string='Field Visibility', 
        default='{}', 
        help='JSON defining which fields are visible'
    )
    
    # Additional Info
    description = fields.Text(string='Description')
    color = fields.Integer(string='Color Index', default=0)
    icon = fields.Char(string='Icon', default='fa-industry')
    
    # # Constraints
    # _constraints = [
    #     Constraint(name='name_uniq', sql_constraint='unique(name)', message="Industry name must be unique!"),
    #     Constraint(name='code_uniq', sql_constraint='unique(code)', message="Industry code must be unique!"),
    # ]
    
    _uniq_name = models.Constraint('unique(name)', 'Industry name must be unique!')
    _uniq_code = models.Constraint('unique(code)', 'Industry code must be unique!')

    @api.constrains('dashboard_config', 'field_visibility')
    def _check_json_fields(self):
        """Validate JSON fields"""
        for record in self:
            for field_name in ['dashboard_config', 'field_visibility']:
                value = getattr(record, field_name)
                if value and value != '{}':
                    try:
                        json.loads(value)
                    except json.JSONDecodeError:
                        raise ValidationError(f"Invalid JSON in {field_name} field")

    @api.model
    def _get_account_account_model(self):
        """Safely get account.account model if available"""
        try:
            return self.env['account.account']
        except KeyError:
            _logger.warning("Account module not installed. Accounting fields will be limited.")
            return None

    def get_default_accounts(self):
        """Get default accounts with fallback"""
        self.ensure_one()
        
        accounts = {
            'income': self.industry_income_account,
            'expense': self.industry_expense_account,
            'journal': self.industry_journal_id,
        }
        
        # If accounting not available, return empty values
        if not self._get_account_account_model():
            return {}
        
        return accounts

    def get_dashboard_config(self):
        """Parse and return dashboard configuration"""
        self.ensure_one()
        try:
            return json.loads(self.dashboard_config or '{}')
        except json.JSONDecodeError:
            return {}

    def get_field_visibility(self):
        """Parse and return field visibility configuration"""
        self.ensure_one()
        try:
            return json.loads(self.field_visibility or '{}')
        except json.JSONDecodeError:
            return {}