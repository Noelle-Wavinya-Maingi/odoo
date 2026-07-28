from odoo import models, fields

class ProductTemplate(models.Model):
    """Adds the flag that marks a product as tradeablem so purchases/sales confirmation knows whether to create or update a trade - instead of reacting to every confirmed order regardless of the product."""
    _inherit = 'product.template'
    
    is_tradeable = fields.Boolean(string='Tradeable', default=True,  help='If enabled, confirming a Purchase or Sale Order for this product will '
             'automatically create or update a Trading Trade. Leave disabled for '
             'ordinary products that should never generate a trade (e.g. services, '
             'office supplies, non-traded goods).')