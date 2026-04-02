from odoo import models, fields, api

class PackageDetailsMixin(models.AbstractModel):
    _name = 'package.details.mixin'
    _description = 'Package Details Mixin'

    def _compute_package_fields(self):
        for record in self:
            if record.package_details_id:
                record.container_type = record.package_details_id.container_type
                record.contents = record.package_details_id.contents
                record.content_classification = record.package_details_id.content_classification
            else:
                record.container_type = False
                record.contents = [(5, 0, 0)]  # Clear many2many fields properly
                record.content_classification = False

    def _inverse_container_type(self):
        for record in self:
            if record.package_details_id:
                record.package_details_id.container_type = record.container_type

    def _inverse_contents(self):
        for record in self:
            if record.package_details_id:
                record.package_details_id.contents = record.contents

    def _inverse_content_classification(self):
        for record in self:
            if record.package_details_id:
                record.package_details_id.content_classification = record.content_classification
