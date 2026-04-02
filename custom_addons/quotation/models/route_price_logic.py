import logging

_logger = logging.getLogger(__name__)

class RoutePriceLogic:
    @staticmethod
    def compute_route_rate_for_distance(record, distance):
        """
        Calculates the route rates for a given distance based on the carrier's distance ranges.
        Args:
            record: The transport rate record
            distance (float): The distance for which to calculate the rate.
        Returns:
            float: The calculated route rate.
        """

        # Check if distance ranges are missing
        if not record.distance_range_ids:
            return 0.0

        # Sort the distance ranges by minimum distance
        sorted_ranges = sorted(record.distance_range_ids, key=lambda r: r.min_distance)

        applicable_range = None
        # Loop through the sorted ranges to find the applicable range for the given distance
        for r in sorted_ranges:
            if r.min_distance <= distance <= r.max_distance:
                applicable_range = r
                break

        # If an applicable range is found, return the fixed price for that range
        if applicable_range:
            return applicable_range.price

        # If no applicable range is found, calculate extra distance cost if distance exceeds all ranges
        max_range = sorted_ranges[-1] if sorted_ranges else None


        # If the distance exceeds the maximum range, calculate extra cost based on per km rate
        if max_range and distance > max_range.max_distance:
            extra_distance = distance - max_range.max_distance
            extra_cost = extra_distance * record.price_per_extra_km
            total_cost = max_range.price + extra_cost
            return total_cost

        return 0.0

    @staticmethod
    def compute_total_rate(records):
        """
        Compute the total rate dynamically using the compute_route_rate_for_distance method.
        The distance is fetched from the sale.order model.
        Args:
            records: The transport rate records
        Returns:
            float: The computed total rate
        """
        for record in records:

            if record.sales_id and record.sales_id.distance:
                # Fetch the distance from the sales order
                distance = record.sales_id.distance

                # Calculate the total rate using the compute_route_rate_for_distance method
                rate = RoutePriceLogic.compute_route_rate_for_distance(record, distance)
                record.total = rate
            else:
                record.total = 0.0
