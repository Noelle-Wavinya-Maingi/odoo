from odoo import models, fields, api

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'
    
    trade_id = fields.Many2one('trading.trade', string='Trade', help='Related trade for this move line')
    
    @api.model_create_multi
    def create(self, vals_list):
        """Ensure invoice lines from sale orders inherit trade information"""
        for vals in vals_list:
            if vals.get('move_id'):
                move = self.env['account.move'].browse(vals['move_id'])
                if move and move.is_from_sale_order and move.trade_id and not vals.get('trade_id'):
                    # If the invoice line doesn't have a trade but the parent invoice does, propagate the trade to the line
                    vals['trade_id'] = move.trade_id.id
                if move and move.is_from_purchase_order and move.trade_id and not vals.get('trade_id'):
                    vals['trade_id'] = move.trade_id.id
        
        return super().create(vals_list)
    
    @api.onchange('product_id')
    def _onchange_product_id_trade_domain(self):
        if self.product_id:
            return {
                'domain': {
                    'trade_id': [('product_id', '=', self.product_id.id)]
                }
            }
            
    @api.onchange('trade_id')
    def _onchange_trade_id(self):
        """On change of trade_id, check the header"""
        for line in self:
            if line.trade_id:
                line.move_id.trade_id = line.trade_id
                line.move_id._compute_is_from_order()
    