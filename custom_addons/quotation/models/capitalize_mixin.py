from odoo import models, fields, api
from odoo.exceptions import ValidationError

class CapitalizedNameMixin(models.AbstractModel):
    _name = 'capitalized.name.mixin'
    _description = 'Mixin to capitalize names before storing'

    name = fields.Char(string='Name', required=True)

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure names are capitalized on creation"""
        for vals in vals_list:
            if 'name' in vals:
                vals['name'] = vals['name'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        """Ensure names are capitalized on update"""
        if 'name' in vals:
            vals['name'] = vals['name'].strip().upper()
        return super().write(vals)
