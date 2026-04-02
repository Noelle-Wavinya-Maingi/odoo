from odoo.exceptions import ValidationError
from odoo.fields import Date

# Compute method for the name of the routes
def compute_name(records):
        for record in records:
            if record.departure_port_id and record.arrival_port_id:
                record.name = f"{record.departure_port_id.name} - {record.arrival_port_id.name}"
            else:
                record.name = "Unnamed Route"
                
# Compute method to validate that POD and POL do not match
def check_ports(records):
    for record in records:
        if record.departure_port_id == record.arrival_port_id:
            raise ValidationError("Port of Loading and Port of Destination cannot be the same!")
        
def compute_write_date_only(records):
        for record in records:
            record.last_updated = record.write_date.date() if record.write_date else None

def compute_create_date_only(records):
        for record in records:
            record.last_updated = record.create_date.date() if record.create_date else None