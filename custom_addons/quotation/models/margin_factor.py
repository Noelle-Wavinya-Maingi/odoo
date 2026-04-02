from odoo import api, fields, models

class MarginFactor(models.Model):
    _name = 'omnifreight.margin.factor'
    _description = "Margin Factor"

    sales_order_id = fields.Many2one('sale.order', string="Sale Order", ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string="Customer", related="sales_order_id.partner_id", store=True, readonly=True)
    
    profile = fields.Char(string="Profile", compute="_compute_partner_data", store=True)
    country = fields.Char(string="Country", compute="_compute_partner_data", store=True)

    profile_margin = fields.Float(string="Profile Margin Factor", help="Margin factor based on customer profile")
    country_margin = fields.Float(string="Country Margin Factor", help="Margin factor based on customer location")

    margin_type = fields.Selection([
        ('profile', 'Profile Margin'),
        ('country', 'Country Margin')
    ], string="Selected Margin", help="Choose either Profile Margin or Country Margin")

    @api.depends('partner_id')
    def _compute_partner_data(self):
        """Fetch partner profile (ratings_tag) and country"""
        for record in self:
            record.profile = record.partner_id.ratings_tag if record.partner_id else ""
            record.country = record.partner_id.country_id.name if record.partner_id and record.partner_id.country_id else ""

