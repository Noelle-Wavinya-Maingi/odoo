from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # Industry Selection
    company_industry = fields.Selection([
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
    ], string='Company Industry', 
       default='trading',
       config_parameter='operations.company_industry',
       help='Select your primary industry to enable relevant features')
    
    industry_config_id = fields.Many2one('industry.type', 
                                        string='Industry Configuration',
                                        compute='_compute_industry_config',
                                        store=False, readonly=False)
    
    # Add these computed fields to access industry config data
    industry_income_account = fields.Many2one(
        'account.account', 
        string='Default Income Account',
        compute='_compute_industry_accounts',
        inverse='_inverse_industry_accounts',
        domain="[('account_type', 'in', ('income', 'other_income'))]"
    )
    
    industry_expense_account = fields.Many2one(
        'account.account', 
        string='Default Expense Account',
        compute='_compute_industry_accounts',
        inverse='_inverse_industry_accounts',
        domain="[ ('account_type', 'in', ('expense', 'other_expense'))]"
    )
    
    industry_journal_id = fields.Many2one(
        'account.journal', 
        string='Default Journal',
        compute='_compute_industry_accounts',
        inverse='_inverse_industry_accounts',
        domain="[('type', 'in', ['sale', 'purchase', 'general'])]"
    )
    
    # Operation Settings
    operation_prefix = fields.Char(string='Operation Prefix',
                                   config_parameter='operations.operation_prefix',
                                   default='OP')
    
    auto_operation_numbering = fields.Boolean(string='Auto Numbering',
                                              config_parameter='operations.auto_operation_numbering',
                                              default=True)
    
    # Module Features (Dynamic based on industry)
    module_shipping = fields.Boolean(string='Shipping Management',
                                     help='Install shipping module')
    module_trading = fields.Boolean(string='Trading Management',
                                    help='Install trading module')
    module_manufacturing = fields.Boolean(string='Manufacturing',
                                          help='Install manufacturing module')
    
    # Industry-specific Settings
    shipping_type = fields.Selection([
        ('container', 'Container Shipping'),
        ('bulk', 'Bulk Shipping'),
        ('breakbulk', 'Breakbulk'),
        ('roro', 'Ro-Ro'),
    ], string='Shipping Type',
       config_parameter='operations.shipping_type')
    
    trading_type = fields.Selection([
        ('wholesale', 'Wholesale'),
        ('retail', 'Retail'),
        ('distribution', 'Distribution'),
        ('import_export', 'Import/Export'),
    ], string='Trading Type',
       config_parameter='operations.trading_type')
    
    # Document Settings
    use_digital_signature = fields.Boolean(string='Use Digital Signature',
                                           config_parameter='operations.use_digital_signature')
    document_archive = fields.Boolean(string='Archive Documents',
                                      config_parameter='operations.document_archive')
    
    # Workflow Settings
    approval_required = fields.Boolean(string='Require Approval',
                                       config_parameter='operations.approval_required')
    multi_level_approval = fields.Boolean(string='Multi-level Approval',
                                          config_parameter='operations.multi_level_approval')
    
    # Notification Settings
    notify_on_creation = fields.Boolean(string='Notify on Creation',
                                        config_parameter='operations.notify_on_creation')
    notify_on_completion = fields.Boolean(string='Notify on Completion',
                                          config_parameter='operations.notify_on_completion')
    
    # Accounting Integration
    auto_create_invoice = fields.Boolean(string='Auto-create Invoice',
                                          config_parameter='operations.auto_create_invoice')
    auto_create_picking = fields.Boolean(string='Auto-create Picking',
                                          config_parameter='operations.auto_create_picking')
    
    # Dashboard Configuration
    dashboard_view = fields.Selection([
        ('kanban', 'Kanban'),
        ('list', 'List'),
        ('graph', 'Graph'),
        ('pivot', 'Pivot'),
    ], string='Default Dashboard',
       default='kanban',
       config_parameter='operations.dashboard_view')
    
    # Industry-specific UI
    show_budget_tab = fields.Boolean(string='Show Budget Tab',
                                      compute='_compute_industry_features')
    show_voyage_tab = fields.Boolean(string='Show Voyage Tab',
                                      compute='_compute_industry_features')
    show_quality_tab = fields.Boolean(string='Show Quality Tab',
                                       compute='_compute_industry_features')
    
    @api.depends('company_industry')
    def _compute_industry_config(self):
        """Get the full industry configuration"""
        for record in self:
            if record.company_industry:
                config = self.env['industry.type'].search([
                    ('code', '=', record.company_industry)
                ], limit=1)
                record.industry_config_id = config.id
            else:
                record.industry_config_id = False
    
    @api.depends('industry_config_id')
    def _compute_industry_accounts(self):
        """Compute account fields from industry config"""
        for record in self:
            if record.industry_config_id:
                record.industry_income_account = record.industry_config_id.industry_income_account
                record.industry_expense_account = record.industry_config_id.industry_expense_account
                record.industry_journal_id = record.industry_config_id.industry_journal_id
            else:
                record.industry_income_account = False
                record.industry_expense_account = False
                record.industry_journal_id = False
    
    def _inverse_industry_accounts(self):
        """Inverse method to save account fields to industry config"""
        for record in self:
            if record.industry_config_id:
                record.industry_config_id.write({
                    'industry_income_account': record.industry_income_account.id,
                    'industry_expense_account': record.industry_expense_account.id,
                    'industry_journal_id': record.industry_journal_id.id,
                })
    
    @api.depends('company_industry')
    def _compute_industry_features(self):
        """Enable/disable features based on industry"""
        for record in self:
            # Default values
            record.show_budget_tab = True
            record.show_voyage_tab = False
            record.show_quality_tab = False
            
            if record.company_industry == 'shipping':
                record.show_voyage_tab = True
            elif record.company_industry == 'manufacturing':
                record.show_quality_tab = True
                record.show_budget_tab = True
            elif record.company_industry == 'trading':
                record.show_budget_tab = True
    
    @api.onchange('company_industry')
    def _onchange_company_industry(self):
        """Auto-configure based on industry selection"""
        if self.company_industry:
            # Auto-enable relevant modules
            if self.company_industry == 'shipping':
                self.module_shipping = True
                self.shipping_type = 'container'
            elif self.company_industry == 'trading':
                self.module_trading = True
                self.trading_type = 'wholesale'
            elif self.company_industry == 'manufacturing':
                self.module_manufacturing = True
                self.module_trading = True
    
    def execute(self):
        """Override execute to handle module installation"""
        # Get the current values before saving
        current_shipping = self.module_shipping
        current_trading = self.module_trading
        current_manufacturing = self.module_manufacturing
        
        # Call super to save settings
        result = super().execute()
        
        # Now install modules if needed
        modules_to_install = []
        
        if current_shipping:
            modules_to_install.append('operations_shipping')
        if current_trading:
            modules_to_install.append('trading')
        if current_manufacturing:
            modules_to_install.append('mrp')
        
        if modules_to_install:
            self._install_modules(modules_to_install)
        
        return result
    
    def set_values(self):
        """Save settings with validation"""
        super().set_values()
        
        # Validate industry-specific requirements
        if self.company_industry == 'shipping' and not self.shipping_type:
            raise UserError(_("Please select a shipping type for shipping industry"))
        
        # Set industry-specific parameters
        self.env['ir.config_parameter'].sudo().set_param(
            'operations.active_industry', self.company_industry
        )
        
        # Trigger industry setup
        self._setup_industry_environment()
    
    def _install_modules(self, module_names):
        """Install modules by name - matches base method signature"""
        try:
            # Get module IDs
            module_ids = self.env['ir.module.module'].search([
                ('name', 'in', module_names),
                ('state', 'in', ['uninstalled', 'to install', 'to upgrade'])
            ])
            
            if module_ids:
                # Mark modules for installation
                module_ids.button_immediate_install()
                
                # Get display names for notification
                display_names = []
                for module_name in module_names:
                    if module_name == 'operations_shipping':
                        display_names.append('Shipping Management')
                    elif module_name == 'operations_trading':
                        display_names.append('Trading Management')
                    elif module_name == 'operations_manufacturing':
                        display_names.append('Manufacturing')
                
                # Show success message
                message = _("Modules installed successfully: %s") % ', '.join(display_names)
                _logger.info(message)
                
                # Use the proper notification method
                self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                    'title': _('Module Installation'),
                    'message': message,
                    'sticky': True,
                    'type': 'success',
                })
                
            else:
                # Modules might already be installed
                installed = self.env['ir.module.module'].search([
                    ('name', 'in', module_names),
                    ('state', '=', 'installed')
                ])
                if installed:
                    _logger.info("Modules already installed: %s", module_names)
                else:
                    _logger.warning("Modules not found: %s", module_names)
                    
        except Exception as e:
            _logger.error("Failed to install modules %s: %s", module_names, e)
            # Send error notification
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'title': _('Module Installation Failed'),
                'message': str(e),
                'sticky': True,
                'type': 'danger',
            })
    
    def _setup_industry_environment(self):
        """Setup industry-specific environment"""
        # Create default sequences
        self._create_industry_sequences()
        
        # Create workflow stages
        self._create_workflow_stages()
        
        # Show success message
        self._show_success_message()
    
    def _create_industry_sequences(self):
        """Create industry-specific sequences"""
        sequence_data = {
            'shipping': {
                'code': 'shipping.operation',
                'name': 'Shipping Operation',
                'prefix': 'SHIP',
            },
            'trading': {
                'code': 'trading.operation',
                'name': 'Trading Operation',
                'prefix': 'TRADE',
            },
            'manufacturing': {
                'code': 'manufacturing.operation',
                'name': 'Manufacturing Operation',
                'prefix': 'MFG',
            }
        }
        
        if self.company_industry in sequence_data:
            data = sequence_data[self.company_industry]
            if not self.env['ir.sequence'].search([
                ('code', '=', data['code'])
            ]):
                self.env['ir.sequence'].create({
                    'name': data['name'],
                    'code': data['code'],
                    'prefix': data['prefix'] + '/%(year)s/',
                    'padding': 5,
                    'company_id': self.company_id.id,
                })
    
    def _create_workflow_stages(self):
        """Create default workflow stages for the selected industry"""
        industry_config = self.industry_config_id
        if not industry_config:
            return
        
        stages_data = {
            'shipping': [
                {'name': 'Draft', 'code': 'draft', 'sequence': 10, 'fold': True},
                {'name': 'Voyage Planning', 'code': 'planning', 'sequence': 20},
                {'name': 'Cargo Booking', 'code': 'booking', 'sequence': 30},
                {'name': 'In Transit', 'code': 'transit', 'sequence': 40},
                {'name': 'Delivered', 'code': 'delivered', 'sequence': 50, 'fold': True},
            ],
            'trading': [
                {'name': 'Draft', 'code': 'draft', 'sequence': 10, 'fold': True},
                {'name': 'Confirmed', 'code': 'confirmed', 'sequence': 20},
                {'name': 'Processing', 'code': 'processing', 'sequence': 30},
                {'name': 'Shipped', 'code': 'shipped', 'sequence': 40},
                {'name': 'Done', 'code': 'done', 'sequence': 50, 'fold': True},
            ],
            'manufacturing': [
                {'name': 'Draft', 'code': 'draft', 'sequence': 10, 'fold': True},
                {'name': 'Planned', 'code': 'planned', 'sequence': 20},
                {'name': 'In Production', 'code': 'production', 'sequence': 30},
                {'name': 'Quality Check', 'code': 'quality', 'sequence': 40},
                {'name': 'Completed', 'code': 'completed', 'sequence': 50, 'fold': True},
            ]
        }
        
        if self.company_industry in stages_data:
            # Remove existing stages
            existing = self.env['workflow.stage'].search([
                ('industry_id', '=', industry_config.id)
            ])
            if existing:
                existing.unlink()
            
            # Create new stages
            for stage_vals in stages_data[self.company_industry]:
                self.env['workflow.stage'].create({
                    'name': stage_vals['name'],
                    'code': stage_vals['code'],
                    'sequence': stage_vals['sequence'],
                    'industry_id': industry_config.id,
                    'fold': stage_vals.get('fold', False),
                })
    
    def _show_success_message(self):
        """Show success message to user using proper notification system"""
        industry_name = dict(self._fields['company_industry'].selection).get(self.company_industry)
        message = _(
            "Industry configuration applied successfully!\n\n"
            "The following changes were made:\n"
            "✓ Created workflow stages for %s\n"
            "✓ Configured sequences\n"
            "✓ Updated settings"
        ) % industry_name
        
        # Use bus notification system
        self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
            'title': _('Operations Configuration'),
            'message': message,
            'sticky': False,
            'type': 'success',
        })
        
        _logger.info("Industry setup completed successfully for: %s", self.company_industry)