def compute_supplier_specialty_ids(records):
        """
        Computes the specialties associated with the supplier. If a supplier is set, the specialties
        will be taken from the supplier's specialty_id otherwise the dropdown will be empty
        """
        for record in records:
            if record.supplier_id:
                record.supplier_specialty_ids = record.supplier_id.specialty_id
            else:
                record.supplier_specialty_ids = False
                

# def default_cost_type(record):
#     """
#     Set default cost type based on the context
#     """
#     if record.env.context.get('default_cost_type') == 'import':
#         return 'import'
#     elif record.env.context.get('default_cost_type') == 'export':
#         return 'export'
#     else:
#         return False
                