from odoo import api, models
from odoo.exceptions import ValidationError
from odoo.tools.mail import email_normalize

class CarrierConstrains(models.AbstractModel):
    _name = 'carrier.constrains'
    _description = 'Carrier Constrains Methods class'

    @api.constrains('email')
    def _check_email_format(self):
        for record in self:
            if record.email:
                try:
                    email_normalize(record.email)  # this WILL raise if invalid
                except Exception:
                    raise ValidationError(
                        f"The email address '{record.email}' is not valid. Please provide a valid email"
                    )