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
        ('manufacturing', 'Manufacturing')
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
    install_shipping = fields.Boolean(string='Shipping Management',
                                     help='Install shipping module')
    install_trading = fields.Boolean(string='Trading Management',
                                    help='Install trading module')
    install_manufacturing = fields.Boolean(string='Manufacturing',
                                          help='Install manufacturing module')
    
    # Industry-specific Settings
    shipping_type = fields.Selection([
        ('container', 'Container Shipping'),
        ('bulk', 'Bulk Shipping'),
        ('breakbulk', 'Breakbulk'),
        ('roro', 'Ro-Ro'),
    ], string='Shipping Type')
    
    trading_type = fields.Selection([
        ('wholesale', 'Wholesale'),
        ('retail', 'Retail'),
        ('distribution', 'Distribution'),
        ('import_export', 'Import/Export'),
    ], string='Trading Type')
    
    # Dashboard Configuration
    dashboard_view = fields.Selection([
        ('kanban', 'Kanban'),
        ('list', 'List'),
        ('graph', 'Graph'),
        ('pivot', 'Pivot'),
    ], string='Default Dashboard',
       default='kanban',
       config_parameter='operations.dashboard_view')
    
    industry_locked = fields.Boolean(string="Industry Locked", compute='_compute_industry_locked')
    
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
    def _compute_industry_locked(self):
        locked = self.env['ir.config_parameter'].sudo().get_param('operations.industry_locked', False)
        
        for record in self:
            record.industry_locked = bool(locked)
            
    def action_unlock_industry(self):
        self.ensure_one()
    
        if not self.env.user.has_group('base.group_system'):
            raise UserError(_("Only system administrators can change the industry configuration."))
    
        # Unlock and reload
        self.env['ir.config_parameter'].sudo().set_param('operations.industry_locked', False)
        self.env['ir.config_parameter'].sudo().set_param('operations.active_industry', False)
    
        # Return a new action to reopen the settings popup fresh
        return {
            'type': 'ir.actions.act_window',
            'name': 'Operations Settings',
            'res_model': 'res.config.settings',
            'view_mode': 'form',
            'view_id': self.env.ref('operations.view_operations_config_settings').id,
            'target': 'new',
            'context': {'module': 'operations'},
        }
    
    @api.onchange('company_industry')
    def _onchange_company_industry(self):
        """Auto-configure based on industry selection"""
        if self.company_industry:
            # Auto-enable relevant modules
            params = self.env['ir.config_parameter'].sudo()
        
            if self.company_industry == 'shipping':
                self.install_shipping = True
                # Only default if nothing saved yet
                if not self.shipping_type and not params.get_param('operations.shipping_type'):
                    self.shipping_type = 'container'
            elif self.company_industry == 'trading':
                self.install_trading = True
                # Only default if nothing saved yet
                if not self.trading_type and not params.get_param('operations.trading_type'):
                    self.trading_type = 'wholesale'
            elif self.company_industry == 'manufacturing':
                self.install_manufacturing = True
                self.install_trading = True

    def execute(self):
        """Override execute to handle module installation"""
        # Get the current values before saving
        params = self.env['ir.config_parameter'].sudo()
        current_shipping = self.install_shipping
        current_trading = self.install_trading
        current_manufacturing = self.install_manufacturing

        # Read what was previously installed via these checkboxes
        was_shipping_installed = params.get_param('operations.shipping_module_installed', False)
        was_trading_installed = params.get_param('operations.trading_module_installed', False)
        was_manufacturing_installed = params.get_param('operations.manufacturing_module_installed', False)

        result = super().execute()
        
        # Now install modules if needed
        modules_to_install = []

        if current_shipping and not was_shipping_installed:
            modules_to_install.append('quotation')
            params.set_param('operations.shipping_module_installed', True)
        if current_trading and not was_trading_installed:
            modules_to_install.append('trading')
            params.set_param('operations.trading_module_installed', True)
        if current_manufacturing and not was_manufacturing_installed:
            modules_to_install.append('mrp')
            params.set_param('operations.manufacturing_module_installed', True)

        if modules_to_install:
            _logger.info(f"📦 New modules to install this save: {modules_to_install}")
            # NOTE: renamed from _install_modules -> _install_operations_modules.
            # Odoo's own core res.config.settings class defines a REAL internal
            # method literally called `_install_modules(self, modules)` -- but
            # its signature expects an ir.module.module RECORDSET, not a list of
            # plain strings. Because this class previously defined a method of
            # the exact same name, it silently overrode/shadowed that core
            # method for the ENTIRE res.config.settings model -- meaning every
            # module_<name> Boolean field anywhere in the system (not just this
            # module's own install_shipping/install_trading/install_manufacturing)
            # had its real installation hijacked by this incompatible override,
            # which then crashed trying to iterate a recordset as if it were a
            # list of strings ("sequence item 0: expected str instance,
            # ir.module.module found"), and silently swallowed the error.
            # Renaming this method removes the collision entirely, restoring
            # core's real _install_modules for every other module_ field.
            self._install_operations_modules(modules_to_install)
        else:
            _logger.info("ℹ️ No new modules to install — skipping")
        return result
    
    def set_values(self):
        """Save settings with validation"""
        super().set_values()
        
        if not self.company_industry:
            return
        
        params = self.env['ir.config_parameter'].sudo()
        previous_industry = params.get_param('operations.active_industry', False)
        # Validate industry-specific requirements
        if self.company_industry == 'shipping' and not self.shipping_type:
            raise UserError(_("Please select a shipping type for shipping industry"))
        
        # Set industry-specific parameters
        self.env['ir.config_parameter'].sudo().set_param('operations.trading_type', self.trading_type or '')
        self.env['ir.config_parameter'].sudo().set_param('operations.shipping_type', self.shipping_type or '')
        self.env['ir.config_parameter'].sudo().set_param('operations.active_industry', self.company_industry)
        self.env['ir.config_parameter'].sudo().set_param('operations.industry_locked', True)
        
        # Trigger industry setup
        if previous_industry != self.company_industry:
            self._setup_industry_environment()

    @api.model
    def get_values(self):
        res = super().get_values()
        params = self.env['ir.config_parameter'].sudo()
        
        trading_type = params.get_param('operations.trading_type', False)
        shipping_type = params.get_param('operations.shipping_type', False)
    
        res.update({
            'trading_type': trading_type if trading_type else False,
            'shipping_type': shipping_type if shipping_type else False,
        })
        return res
    
    def _install_operations_modules(self, module_names):
        """Install modules by name (list of plain string technical names).

        Renamed from `_install_modules` -- see the comment in execute() above
        for why the old name collided with a real Odoo core method and must
        never be reused for this custom, string-based helper.
        """
        try:
            # Define dependencies that must be installed before each module
            dependency_map = {
                'trading': ['purchase', 'sale_management', 'stock'],
                'operations_shipping': ['stock'],
                'mrp': ['stock', 'purchase'],
            }

            # Build ordered list: dependencies first, then the module itself
            ordered_modules = []
            for module_name in module_names:
                deps = dependency_map.get(module_name, [])
                for dep in deps:
                    if dep not in ordered_modules:
                        ordered_modules.append(dep)
                if module_name not in ordered_modules:
                    ordered_modules.append(module_name)

            _logger.info("📦 Install order: %s", ordered_modules)

            # Install in batches — dependencies first, then main modules
            for module_name in ordered_modules:
                module = self.env['ir.module.module'].search([
                    ('name', '=', module_name),
                    ('state', 'in', ['uninstalled', 'to install', 'to upgrade'])
                ], limit=1)

                if module:
                    _logger.info("⬇️ Installing: %s", module_name)
                    module.button_immediate_install()
                    _logger.info("✅ Installed: %s", module_name)
                else:
                    _logger.info("⏭️ Already installed or not found: %s", module_name)

            # Show success
            self.env['bus.bus']._sendone(self.env.user.partner_id, 'simple_notification', {
                'title': _('Modules Installed'),
                'message': _("Successfully installed: %s") % ', '.join(module_names),
                'sticky': True,
                'type': 'success',
            })

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