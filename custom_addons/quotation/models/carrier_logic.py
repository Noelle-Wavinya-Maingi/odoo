from odoo import fields


# def compute_flags(carriers):
#         print('🤠Compute flags started!')

#         # Get all carriers
#         all_carriers = carriers.search([])

#         for carrier in carriers:
#             print(f"😀Processing carrier ID: {carrier.id}, Name: {carrier.name}")
#             # Check for the oldest deadline
#             valid_deadlines = [c.last_updated for c in all_carriers if c.last_updated]

#             if valid_deadlines:
#                 min_deadline = min(valid_deadlines)
#                 carrier.is_oldest = carrier.last_updated == min_deadline
#                 print(f"😅Deadline comparison: Carrier deadline {carrier.last_updated}, Min deadline {min_deadline}")
#             else:
#                 carrier.is_oldest = False

#             # Check for the cheapest rate
#             valid_rates = [c.rate for c in all_carriers if c.rate and c.rate > 0]

#             if valid_rates:
#                 min_rate = min(valid_rates)
#                 carrier.is_cheapest = carrier.rate == min_rate
#                 print(f"😙Rate comparison: Carrier rate {carrier.rate}, Min rate {min_rate}")
#             else:
#                 carrier.is_cheapest = False

def compute_flags(self):
        """Compute is_cheapest and is_oldest flags."""

        # Get all prices
        all_prices = self.search([])

        # Compute cheapest price
        min_price = min(all_prices.mapped('price'), default=0)

        # Compute oldest date
        valid_dates = [p.write_date_as_date for p in all_prices if p.write_date_as_date]
        oldest_date = min(valid_dates) if valid_dates else None

        for record in self:
            record.is_cheapest = record.price == min_price
            record.is_oldest = record.write_date_as_date == oldest_date
                
# def show_price_per_km(records):
#     for record in records:
#         record.show_price_per_km = record.carrier_type == 'land'
#         print(f"Carrier ID {record.id}: carrier_type={record.carrier_type}, show_price_per_km={record.show_price_per_km}")
