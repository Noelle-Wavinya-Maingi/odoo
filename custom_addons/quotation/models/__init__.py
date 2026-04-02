# Independent models with no dependencies
from . import carrier
from . import port
from . import haulier_region
from . import roles
from . import subcategory
from . import target
from . import omnifreight_segments
from . import capitalize_mixin
from . import segment_two
from . import omnifreight_cargo_type

# Models with minimal dependencies
from . import carrier_regions_join
from . import distance_range

# Models with Many2one dependencies on earlier models
from . import route_price
from . import route_price_logic
from . import package_details
from . import omnifreight_route
from . import supplier
from . import transport_rates
from . import known_prices
from . import container_type
from . import containter_size
from . import contact_roles
from . import res_partner_subregion

# Models with Many2Many dependencies on earlier models
from . import days
from . import port_labels
from . import specialty
from . import un_subregions
from . import compute_package_logic

# Models with complex dependencies
from . import customer_routes
from . import omnifreight_quotation
from . import special_costs
from . import special_cost_preset
from . import freight_costs_sheet
from . import margin_factor
from . import omnifreight_lod
from . import omnifreight_fob_service
from . import known_price_sale_order
from . import sale_order_transport_rate
from . import sale_order_lod_transport_rate
