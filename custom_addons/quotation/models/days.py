from odoo import models, fields

class RouteDays(models.Model):
    # model name
    _name = 'route.days'
    _description = 'Departure days for the shipping routes'
    
    # names of the days for the route
    name = fields.Char('Days', required=True)