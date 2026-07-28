# -*- coding: utf-8 -*-
# from odoo import http


# class OmniOps(http.Controller):
#     @http.route('/omni_ops/omni_ops', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/omni_ops/omni_ops/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('omni_ops.listing', {
#             'root': '/omni_ops/omni_ops',
#             'objects': http.request.env['omni_ops.omni_ops'].search([]),
#         })

#     @http.route('/omni_ops/omni_ops/objects/<model("omni_ops.omni_ops"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('omni_ops.object', {
#             'object': obj
#         })

