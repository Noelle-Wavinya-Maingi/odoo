# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class OmniStockMoveLine(models.Model):
    """Extend stock move lines to support Omnifreight service products."""
    _inherit = 'stock.move.line'

    # === FIELDS ===
    # Override product_id domain to include omni_service products
    product_id = fields.Many2one(
        'product.product', 'Product', 
        ondelete="cascade", 
        check_company=True, 
        domain="[('type', 'in', ('consu', 'product', 'omni_service'))]", 
        index=True
    )
