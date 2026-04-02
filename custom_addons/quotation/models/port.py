from odoo import fields, models, api, _
from odoo.exceptions import UserError

from .route_logic import compute_write_date_only

class Port(models.Model):
    # Model name
    _name = 'port'
    _description = 'Port'

    # Name of the port
    name = fields.Char()
    # Port code
    city = fields.Char(string="City")
    port_city = fields.Many2one('unloc.city', string="Port City")
    port_code = fields.Char()
    # Country where the port is located
    country_id = fields.Many2one('unloc.country')
    # Terminal linked to the port
    terminal = fields.Char()
    # Loading duration for operations at the port
    loading_duration = fields.Float(help='Loading duration in hours')
    # Latest possible loading time at the port
    latest_loading_time = fields.Float(help='Latest loading time in hours')
    # Additional info 
    info = fields.Json()
    # Reference to an employee
    expert_id = fields.Many2one('hr.employee', string="Expert")
    # Reference to the label tags associated with the port
    label_id = fields.Many2many('port.labels', string='Label')
    # Reference to a haulier region associated with the port
    haulier_region_id = fields.Many2one('haulier.region', string='Haulier Region')
    # Additional information on ICDs and congestion field
    port_info = fields.Text(string='Additional info', help="Any additional information on ICDs and port congestion")
    
    last_updated = fields.Date(compute='_compute_write_date_only')

    # COSTS ASSOCIATED WITH A PORT
    special_costs = fields.One2many(
        'omnifreight.special.costs',  # related model
        'port_id',                    # inverse field on special costs
        string='Special Costs'
    )
    special_costs_preset = fields.One2many(
        'omnifreight.special.cost.preset',
        'port_id',
        string='Special Cost Presets'
    )
                
    def action_redirect_to_route(self):
        """
        This method is triggered by the button to open existing routes
        """
        try:
            action_ref = self.env.ref('omni_quotation.action_omnifreight_route')
            if not action_ref.exists():
                raise UserError(_('The route action is not properly configured. Please contact your administrator.'))
            action = action_ref.read()[0] if action_ref.exists() else {}
            # A check to only display routes with either POL or POD matches the current port
            action['domain'] = ['|', ('departure_port_id', '=', self.id), ('arrival_port_id', '=', self.id)]
            return action
        except ValueError:
            raise UserError(_('The route action is not properly configured. Please contact your administrator.'))
       
    def _compute_write_date_only(self):
           compute_write_date_only(self)
           
    def _compute_name(self):
        for record in self:
            if record.port_city and record.port_code:
                record.name = f"{record.port_code}: {record.port_city}"
            else:
                record.name = "Unnamed Port"


    def _generate_routes_for_ports(self, ports):
        """
        Generate routes for the provided list of ports, avoiding duplicates.
        This method now handles route generation in bulk to improve performance.
        """
        routes_model = self.env['omnifreight.route']
        all_ports = self.search([])  # Fetch all ports

        routes = []
        for departure_port in ports:
            for arrival_port in all_ports:
                if departure_port != arrival_port:
                    # Check if the route already exists in the database
                    existing_route = routes_model.search([
                        ('departure_port_id', '=', departure_port.id),
                        ('arrival_port_id', '=', arrival_port.id)
                    ], limit=1)
                    if not existing_route:
                        routes.append({
                            'departure_port_id': departure_port.id,
                            'arrival_port_id': arrival_port.id,
                        })

        # Bulk create routes
        if routes:
            try:
                created_routes = routes_model.create(routes)
                return created_routes
            except Exception as e:
                # Try creating routes one by one to identify the problematic one
                for route_data in routes:
                    try:
                        routes_model.create(route_data)
                    except Exception as e2:
                        pass
                return False
        return False

    @api.onchange('country_id')
    def _onchange_country_id(self):
        """ 
        Clear the city when country changes and update haulier region.
        """
        for record in self:
            # Clear the city when country changes
            record.port_city = False
            
            # Update haulier region based on country
            if record.country_id and record.country_id.subregion_id:
                haulier_region = self.env['haulier.region'].search([('region_name', '=', record.country_id.subregion_id.id)], limit=1)
                if haulier_region:
                    record.haulier_region_id = haulier_region.id
                else:
                    record.haulier_region_id = False
            else:
                record.haulier_region_id = False

    @api.onchange('port_city')
    def _onchange_port_city(self):
        """ 
        Update country when city is selected and update haulier region.
        Clear country when city is deleted.
        """
        for record in self:
            if record.port_city:
                # Set country based on selected city
                record.country_id = record.port_city.country_id
                
                # Get the subregion from the city
                subregion = record.port_city.country_id.subregion_id if record.port_city.country_id else False
            else:
                # Clear country when city is deleted
                record.country_id = False
                subregion = False

            # Update haulier region
            if subregion:
                haulier_region = self.env['haulier.region'].search([('region_name', '=', subregion.id)], limit=1)
                if haulier_region:
                    record.haulier_region_id = haulier_region.id
                else:
                    record.haulier_region_id = False
            else:
                record.haulier_region_id = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Override create method to generate routes when a new port is added.
        This handles batch creation of ports and bulk generation of routes.
        """
        # If vals_list is not a list, handle as single record creation
        if not isinstance(vals_list, list):
            vals_list = [vals_list]
        
        # Call super to create all the ports in batch
        ports = super(Port, self).create(vals_list)

        # Generate routes for the newly created ports in bulk
        self._generate_routes_for_ports(ports)
        
        return ports
