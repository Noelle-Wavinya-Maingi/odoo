from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    trade_id = fields.Many2one('trading.trade', string='Trade', help='Related trade for this move line')
    
    @api.onchange('product_id')
    def _onchange_product_id_trade_domain(self):
        if self.product_id:
            return {
                'domain': {
                    'trade_id': [('product_id', '=', self.product_id.id)]
                }
            }
    