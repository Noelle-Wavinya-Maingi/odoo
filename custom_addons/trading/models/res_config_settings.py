from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    
    module_trading_budget = fields.Boolean(string="Budgets")