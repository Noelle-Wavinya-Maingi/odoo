# from odoo import api, fields, models, _
# from odoo.exceptions import ValidationError
# import json


# class GenericOperation(models.Model):
#     """Generic Operation Model that adapts to different industries"""
#     _name = 'generic.operation'
#     _description = 'Generic Operation'
#     _inherit = ['mail.thread']
#     _order = 'date_created desc, id desc'

#     # Core Fields
#     name = fields.Char(string='Operation Reference', required=True, 
#                        default=lambda self: _('New'), copy=False)
    
#     industry_type = fields.Selection([
#         ('shipping', 'Shipping'),
#         ('trading', 'Trading'),
#         ('manufacturing', 'Manufacturing'),
#     ], string='Industry Type', required=True, 
#        default=lambda self: self._get_default_industry())
    
#     operation_type = fields.Selection([
#         ('project', 'Project Based'),
#         ('continuous', 'Continuous'),
#         ('batch', 'Batch'),
#         ('job', 'Job Based'),
#     ], string='Operation Type', required=True,
#        default=lambda self: self._get_default_operation_type())
    
#     state = fields.Selection(string='Status', tracking=True,
#                              selection='_get_state_selection',
#                              default='draft')
    
#     # Partner Information
#     partner_id = fields.Many2one('res.partner', string='Customer/Supplier',
#                                   tracking=True)
#     partner_ref = fields.Char(string='Partner Reference', tracking=True)
    
#     # Dates
#     date_created = fields.Datetime(string='Created On', default=fields.Datetime.now,
#                                     readonly=True)
#     date_start = fields.Datetime(string='Start Date', tracking=True)
#     date_end = fields.Datetime(string='End Date', tracking=True)
#     date_deadline = fields.Date(string='Deadline', tracking=True)
    
#     # Financial
#     company_id = fields.Many2one('res.company', string='Company',
#                                   default=lambda self: self.env.company)
#     currency_id = fields.Many2one('res.currency',
#                                    related='company_id.currency_id')
    
#     estimated_cost = fields.Monetary(string='Estimated Cost',
#                                       currency_field='currency_id',
#                                       tracking=True)
#     actual_cost = fields.Monetary(string='Actual Cost',
#                                    currency_field='currency_id',
#                                    compute='_compute_actual_cost',
#                                    store=True)
#     margin = fields.Monetary(string='Margin',
#                               currency_field='currency_id',
#                               compute='_compute_margin')
    
#     # === BUDGET INTEGRATION - Odoo Community Models ===
#     # Link to analytic account (for budget tracking)
#     analytic_account_id = fields.Many2one(
#         'account.analytic.account', 
#         string='Analytic Account',
#         help="Analytic account to track operation costs and revenues",
#         domain="[('company_id', '=', company_id)]"
#     )
    
#     # Link to crossovered budget (Community version)
#     crossovered_budget_id = fields.Many2one(
#         'crossovered.budget', 
#         string='Budget',
#         help="Budget for this operation",
#         domain="[('company_id', '=', company_id)]"
#     )
    
#     # Link to budget lines
#     crossovered_budget_line_ids = fields.One2many(
#         'crossovered.budget.lines', 
#         'operation_id',  # We'll add this field via inheritance
#         string='Budget Lines'
#     )
    
#     # Budgetary positions
#     general_budget_id = fields.Many2one(
#         'account.budget.post',
#         string='Budgetary Position',
#         help="Default budgetary position for this operation"
#     )
    
#     # Documents
#     document_ids = fields.One2many('operations.document', 'operation_id',
#                                     string='Documents')
    
#     # Industry-specific fields (stored in JSON)
#     industry_data = fields.Text(string='Industry Data',
#                                  default='{}',
#                                  help='JSON data for industry-specific fields')
    
#     # Dynamic fields based on industry
#     voyage_id = fields.Many2one('operations.voyage', string='Voyage',
#                                  compute='_compute_industry_fields',
#                                  inverse='_inverse_voyage_id',
#                                  search='_search_voyage_id')
    
#     production_id = fields.Many2one('mrp.production', string='Production Order',
#                                      compute='_compute_industry_fields',
#                                      inverse='_inverse_production_id')
    
#     lot_id = fields.Many2one('stock.lot', string='Lot/Serial Number',
#                               compute='_compute_industry_fields',
#                               inverse='_inverse_lot_id')
    
#     # Tracking
#     user_id = fields.Many2one('res.users', string='Responsible',
#                                default=lambda self: self.env.user,
#                                tracking=True)
#     team_id = fields.Many2one('crm.team', string='Team')
    
#     # Workflow
#     stage_id = fields.Many2one('workflow.stage', string='Stage',
#                                 group_expand='_read_group_stage_ids',
#                                 tracking=True)
    
#     # Inventory
#     product_ids = fields.One2many('operation.product', 'operation_id',
#                                     string='Products')
    
#     # UI Helpers
#     color = fields.Integer(string='Color Index')
#     priority = fields.Selection([
#         ('0', 'Low'),
#         ('1', 'Normal'),
#         ('2', 'High'),
#         ('3', 'Urgent'),
#     ], string='Priority', default='1')
    
#     # ===========================================================
#     # Budget-related Methods
#     # ===========================================================
    
#     def action_create_budget(self):
#         """Create a budget for this operation using Odoo Community budget model"""
#         self.ensure_one()
        
#         if self.crossovered_budget_id:
#             return {
#                 'type': 'ir.actions.act_window',
#                 'name': 'Budget',
#                 'res_model': 'crossovered.budget',
#                 'res_id': self.crossovered_budget_id.id,
#                 'view_mode': 'form',
#                 'target': 'current',
#             }
        
#         # Create budget name
#         budget_name = f"{self.name} - {dict(self._fields['industry_type'].selection).get(self.industry_type, 'Operation')}"
        
#         # Set date range
#         date_from = self.date_start or fields.Date.today()
#         date_to = self.date_end or (fields.Date.today() + relativedelta(months=+12))
        
#         # Create the budget
#         budget_vals = {
#             'name': budget_name,
#             'company_id': self.company_id.id,
#             'date_from': date_from,
#             'date_to': date_to,
#         }
        
#         budget = self.env['crossovered.budget'].create(budget_vals)
#         self.crossovered_budget_id = budget.id
        
#         return {
#             'type': 'ir.actions.act_window',
#             'name': 'Budget',
#             'res_model': 'crossovered.budget',
#             'res_id': budget.id,
#             'view_mode': 'form',
#             'target': 'current',
#         }
    
#     def action_add_budget_line(self):
#         """Open wizard to add budget line"""
#         self.ensure_one()
        
#         return {
#             'type': 'ir.actions.act_window',
#             'name': 'Add Budget Line',
#             'res_model': 'add.budget.line.wizard',
#             'view_mode': 'form',
#             'target': 'new',
#             'context': {
#                 'default_operation_id': self.id,
#                 'default_company_id': self.company_id.id,
#             }
#         }
    
#     def _get_actual_costs_from_budget(self):
#         """Calculate actual costs from budget lines"""
#         self.ensure_one()
        
#         total = 0.0
#         if self.crossovered_budget_line_ids:
#             for line in self.crossovered_budget_line_ids:
#                 # Sum actual amounts from budget lines
#                 total += line.actual_amount or 0.0
#         return total
    
#     @api.depends('crossovered_budget_line_ids.actual_amount')
#     def _compute_actual_cost(self):
#         """Compute actual cost from budget lines"""
#         for record in self:
#             record.actual_cost = record._get_actual_costs_from_budget()
    
#     @api.depends('estimated_cost', 'actual_cost')
#     def _compute_margin(self):
#         """Compute margin"""
#         for record in self:
#             record.margin = record.estimated_cost - record.actual_cost
    
#     # ===========================================================
#     # Dynamic Methods
#     # ===========================================================
    
#     @api.model
#     def _get_default_industry(self):
#         """Get default industry from settings"""
#         return self.env['ir.config_parameter'].sudo().get_param(
#             'operations.company_industry', 'trading'
#         )
    
#     @api.model
#     def _get_default_operation_type(self):
#         """Get default operation type from industry config"""
#         industry = self._get_default_industry()
#         config = self.env['industry.type'].search([
#             ('code', '=', industry)
#         ], limit=1)
#         return config.default_operation_type if config else 'project'
    
#     @api.model
#     def _get_state_selection(self):
#         """Dynamic state selection based on industry"""
#         base_states = [
#             ('draft', 'Draft'),
#             ('confirmed', 'Confirmed'),
#             ('in_progress', 'In Progress'),
#             ('done', 'Done'),
#             ('cancelled', 'Cancelled'),
#         ]
        
#         industry = self._get_default_industry()
#         if industry == 'shipping':
#             return [
#                 ('draft', 'Draft'),
#                 ('voyage_planning', 'Voyage Planning'),
#                 ('cargo_booking', 'Cargo Booking'),
#                 ('in_transit', 'In Transit'),
#                 ('arrived', 'Arrived'),
#                 ('customs_clearance', 'Customs Clearance'),
#                 ('delivered', 'Delivered'),
#                 ('cancelled', 'Cancelled'),
#             ]
#         elif industry == 'manufacturing':
#             return [
#                 ('draft', 'Draft'),
#                 ('planned', 'Planned'),
#                 ('production', 'In Production'),
#                 ('quality_check', 'Quality Check'),
#                 ('completed', 'Completed'),
#                 ('cancelled', 'Cancelled'),
#             ]
#         return base_states
    
#     @api.model
#     def _read_group_stage_ids(self, stages, domain, order):
#         """Read group for stages"""
#         industry = self._get_default_industry()
#         stage_ids = self.env['workflow.stage'].search([
#             ('industry_id.code', '=', industry)
#         ])
#         return stage_ids
    
#     @api.model
#     def create(self, vals):
#         """Create operation with industry-specific handling"""
#         if vals.get('name', _('New')) == _('New'):
#             vals['name'] = self._get_next_sequence()
        
#         # Set industry type from settings if not provided
#         if 'industry_type' not in vals:
#             vals['industry_type'] = self._get_default_industry()
        
#         # Initialize industry data
#         if 'industry_data' not in vals:
#             vals['industry_data'] = json.dumps({})
        
#         operation = super().create(vals)
        
#         return operation
    
#     def _get_next_sequence(self):
#         """Get next sequence based on industry"""
#         industry = self._get_default_industry()
#         sequences = {
#             'shipping': 'shipping.operation',
#             'trading': 'trading.operation',
#             'manufacturing': 'manufacturing.operation',
#         }
        
#         if industry in sequences:
#             return self.env['ir.sequence'].next_by_code(sequences[industry]) or _('New')
#         return self.env['ir.sequence'].next_by_code('generic.operation') or _('New')
    
#     # ===========================================================
#     # Dynamic Field Computation
#     # ===========================================================
    
#     def _compute_industry_fields(self):
#         """Compute industry-specific fields from JSON data"""
#         for record in self:
#             data = json.loads(record.industry_data or '{}')
            
#             # Set computed values based on industry
#             if record.industry_type == 'shipping':
#                 record.voyage_id = data.get('voyage_id', False)
#             elif record.industry_type == 'manufacturing':
#                 record.production_id = data.get('production_id', False)
    
#     def _inverse_voyage_id(self):
#         """Inverse method for voyage_id field"""
#         for record in self:
#             if record.industry_type == 'shipping':
#                 data = json.loads(record.industry_data or '{}')
#                 data['voyage_id'] = record.voyage_id.id if record.voyage_id else False
#                 record.industry_data = json.dumps(data)
    
#     def _inverse_production_id(self):
#         """Inverse method for production_id field"""
#         for record in self:
#             if record.industry_type == 'manufacturing':
#                 data = json.loads(record.industry_data or '{}')
#                 data['production_id'] = record.production_id.id if record.production_id else False
#                 record.industry_data = json.dumps(data)
    
#     def _search_voyage_id(self, operator, value):
#         """Search method for voyage_id"""
#         operations = self.search([])
#         result_ids = []
#         for op in operations:
#             data = json.loads(op.industry_data or '{}')
#             voyage_id = data.get('voyage_id')
#             if voyage_id and self._eval_domain([('voyage_id', operator, value)], {'voyage_id': voyage_id}):
#                 result_ids.append(op.id)
#         return [('id', 'in', result_ids)]
    
#     # ===========================================================
#     # Business Methods
#     # ===========================================================
    
#     def action_confirm(self):
#         """Confirm the operation"""
#         self.state = 'confirmed'
#         self.message_post(body=_("Operation confirmed"))
    
#     def action_start(self):
#         """Start the operation"""
#         self.state = 'in_progress'
#         self.date_start = fields.Datetime.now()
#         self.message_post(body=_("Operation started"))
    
#     def action_done(self):
#         """Complete the operation"""
#         self.state = 'done'
#         self.date_end = fields.Datetime.now()
#         self.message_post(body=_("Operation completed"))
        
#         # Auto-create invoice if configured
#         if self.env['ir.config_parameter'].sudo().get_param('operations.auto_create_invoice'):
#             self._create_invoice()
    
#     def action_cancel(self):
#         """Cancel the operation"""
#         self.state = 'cancelled'
#         self.message_post(body=_("Operation cancelled"))
    
#     def _create_invoice(self):
#         """Create invoice for operation"""
#         # This would create invoices based on operation type
#         pass
    
#     def get_dashboard_data(self):
#         """Get dashboard data for this operation"""
#         return {
#             'id': self.id,
#             'name': self.name,
#             'state': self.state,
#             'partner': self.partner_id.name,
#             'estimated_cost': self.estimated_cost,
#             'actual_cost': self.actual_cost,
#             'progress': self._calculate_progress(),
#         }
    
#     def _calculate_progress(self):
#         """Calculate operation progress"""
#         if self.state == 'done':
#             return 100
#         elif self.state == 'cancelled':
#             return 0
#         elif self.state == 'in_progress':
#             # Calculate based on completed tasks
#             return 50
#         return 0


# class OperationProduct(models.Model):
#     """Products in an operation"""
#     _name = 'operation.product'
#     _description = 'Operation Product'

#     operation_id = fields.Many2one('generic.operation', string='Operation',
#                                     required=True, ondelete='cascade')
#     product_id = fields.Many2one('product.product', string='Product',
#                                   required=True)
#     quantity = fields.Float(string='Quantity', required=True, default=1.0)
#     uom_id = fields.Many2one('uom.uom', string='Unit of Measure',
#                               related='product_id.uom_id')
#     price_unit = fields.Float(string='Unit Price')
#     subtotal = fields.Float(string='Subtotal', compute='_compute_subtotal')
    
#     @api.depends('quantity', 'price_unit')
#     def _compute_subtotal(self):
#         for record in self:
#             record.subtotal = record.quantity * record.price_unit