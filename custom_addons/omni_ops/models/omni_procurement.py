# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.tools import float_is_zero


class OmniProcurementGroup(models.Model):
    """Extend procurement group to allow omni_service products to be procured."""
    _inherit = 'stock.reference'

    @api.model
    def _skip_procurement(self, procurement):
        """Override to allow omni_service products to be procured."""
        # Allow omni_service products to be procured (don't skip them)
        if procurement.product_id.type == 'omni_service':
            return float_is_zero(
                procurement.product_qty, precision_rounding=procurement.product_uom.rounding
            )
        
        # Original logic for other product types
        return procurement.product_id.type != "consu" or float_is_zero(
            procurement.product_qty, precision_rounding=procurement.product_uom.rounding
        )
