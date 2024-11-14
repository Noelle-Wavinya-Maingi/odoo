from odoo import fields, models
from datetime import timedelta

class EstateProperty(models.Model):
    _name = 'estate.property'
    _description = 'Real estate property'
    
    name = fields.Char(string='Property Name', required = True, translate =  True)
    description = fields.Text(string='Description')
    postcode = fields.Char(string='Postcode')
    date_availability = fields.Date(string='Availability Date', default=lambda self: fields.Date.to_string(fields.Date.today() + timedelta(days=90)), copy=False)
    expected_price = fields.Float(string='Expected Price', required = True)
    selling_price = fields.Float(string='Selling Price', readonly=True, copy=False)
    bedrooms = fields.Integer(string='Bedrooms', default=2)
    living_area = fields.Integer(string='Living Area (sqm)')
    facades = fields.Integer(string='Number of facades')
    garage = fields.Boolean(string='Garage')
    garden = fields.Boolean(string='Garden')
    garden_area = fields.Integer(string='Garden Area (sqm)')
    
    #Selection field for garden orientation
    garden_orientation = fields.Selection(
        selection=[
            ('north', 'North'),
            ('south', 'South'),
            ('east', 'East'),
            ('west', 'West'),
        ],
        string='Garden Orientation'
    )
    
    active = fields.Boolean(default = True)
    state = fields.Selection([
        ('new', 'New'),
        ('offer received', 'Offer Received'),
        ('sold', 'Sold'),
        ('cancelled', 'Cancelled'),
    ], default='new', string="Status", required=True, copy=False)