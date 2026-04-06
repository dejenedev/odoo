# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request


class MetabaseController(http.Controller):

    @http.route('/budget_segment/metabase_url', type='json', auth='user')
    def get_metabase_url(self):
        ICP = request.env['ir.config_parameter'].sudo()
        base_url = ICP.get_param('budget_segment.metabase_url', 'http://localhost:3000')
        dashboard_id = ICP.get_param('budget_segment.metabase_dashboard_id', '')
        if dashboard_id:
            return '%s/public/dashboard/%s#bordered=false&titled=false' % (
                base_url.rstrip('/'), dashboard_id)
        return ''
