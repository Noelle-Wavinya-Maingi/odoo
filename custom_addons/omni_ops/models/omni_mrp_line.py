from odoo import models, fields, api


class OmniMrpLine(models.Model):
    """
    Extend BOM line to allow 'omni_service' products as components
    """
    _inherit = 'mrp.bom.line'

    # Allow omni_service at template level
    product_tmpl_id = fields.Many2one(
        'product.template', 'Product',
        check_company=True, index=True,
        domain="[('type', 'in', ('consu','product','omni_service'))]",  # extended
        required=True
    )

    # Allow omni_service at variant level
    product_id = fields.Many2one(
        'product.product', 'Product Variant',
        check_company=True, index=True,
        domain="['&', ('product_tmpl_id', '=', product_tmpl_id), ('type', 'in', ('consu','product','omni_service'))]",
        help="If a product variant is defined the BOM is available only for this product."
    )
