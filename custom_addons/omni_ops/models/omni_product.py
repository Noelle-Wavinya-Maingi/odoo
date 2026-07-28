from odoo import models, fields, api


class OmniProductTemplate(models.Model):
    """
    This is a custom product template that is used to create an Omnifreight service product.
    The product can be used as a component in the manufacturing module but it does not cause stock movements
    """

    _inherit = 'product.template'

    ## Safely add a new product type to the product template
    type = fields.Selection(
        selection_add=[
            ('omni_service', 'Omnifreight Service'),
        ],
        ondelete={'omni_service': 'set default'},
    )
    
    ## Ensure omni_service products are treated as consumable and phantom for BOM usage
    @api.onchange('type')
    def _onchange_type_set_properties(self):
        """
        Automatically sets properties for omni_service products:
        - Sets as phantom product (no stock moves)
        - Sets category to 'Omnifreight Services'
        - Enables MTO with manufacturing route for smart button
        """
        if self.type == 'omni_service':
            # Set category to 'Omnifreight Services'
            category = self.env['product.category'].search(
                [('name', '=', 'Omnifreight Services')], limit=1
            )
            if category:
                self.categ_id = category.id
            
            # Ensure it's not tracked for inventory
            self.tracking = 'none'
            
            # Set as a service product (no stock moves)
            self.service_type = 'manual'
            
 

