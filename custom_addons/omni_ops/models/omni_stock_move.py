from odoo import api, fields, models, _


class OmniStockMove(models.Model):
    """Extend stock moves to support Omnifreight service products in manufacturing."""
    _inherit = 'stock.move'

    # === FIELDS ===
    # Override product_id domain to include omni_service products
    product_id = fields.Many2one(
        'product.product', 'Product',
        check_company=True, index=True,
        domain="[('type', 'in', ('consu', 'product', 'omni_service'))]",
        help="Product to be manufactured"
    )