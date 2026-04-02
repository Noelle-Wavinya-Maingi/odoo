# -*- coding: utf-8 -*-
# from odoo import http


# class OmnifreightQuotation(http.Controller):
#     @http.route('/omnifreight_quotation/omnifreight_quotation', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/omnifreight_quotation/omnifreight_quotation/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('omnifreight_quotation.listing', {
#             'root': '/omnifreight_quotation/omnifreight_quotation',
#             'objects': http.request.env['omnifreight_quotation.omnifreight_quotation'].search([]),
#         })

#     @http.route('/omnifreight_quotation/omnifreight_quotation/objects/<model("omnifreight_quotation.omnifreight_quotation"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('omnifreight_quotation.object', {
#             'object': obj
#         })

