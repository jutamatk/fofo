# -*- coding: utf-8 -*-
##############################################################################
#
#    OpenERP, Open Source Management Solution
#    Copyright (C) 2015-Today Ecosoft Co., Ltd. (http://Ecosoft.co.th).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp

class sale_order_line(models.Model):
    _inherit = 'sale.order.line'

    date_order = fields.Datetime(related='order_id.date_order', store=True, string='Order Date')
    product_tmpl_id_store = fields.Many2one(related='product_id.product_tmpl_id', store=True, string='Product Template', relation='product.template')
    sale_history_line_ids = fields.Many2many('sale.order.line', 'sale_line_history_rel', 'line_id1', 'line_id2', string='Sale History')
    route_id = fields.Many2one(compute='_compute_route_id')


    @api.multi
    def product_id_change(self, pricelist, product, qty=0,
            uom=False, qty_uos=0, uos=False, name='', partner_id=False,
            lang=False, update_tax=True, date_order=False, packaging=False, fiscal_position=False, flag=False):
        res = super(sale_order_line, self).product_id_change(pricelist, product, qty,
            uom, qty_uos, uos, name, partner_id,
            lang, update_tax, date_order, packaging, fiscal_position, flag)
        if product and partner_id:
            sale_lines = self.search([('product_id', '=', product), ('order_id.partner_id', '=', partner_id)], order='id desc', limit=8)
            lines = []
            if sale_lines:
                for line in sale_lines:
                    lines.append(line.id)
                res['value'].update({'sale_history_line_ids': [(6, 0, lines)]})
        return res

    @api.multi
    @api.depends('product_id', 'order_id.partner_id')
    def _compute_route_id(self):
        for l in self:
            l.route_id = l.order_id.partner_id.route_id


class sale_order(models.Model):
    _inherit = 'sale.order'
    
    @api.constrains('order_policy', 'order_line')
    def check_order_policy(self):
        if self.order_line:
            for line in self.order_line:
                product_tmpl_id = line.product_id.product_tmpl_id.id
                bom_product = self.env['mrp.bom'].search([('product_tmpl_id', '=', product_tmpl_id)])
                if bom_product and self.order_policy != 'manual':
                    raise Warning('Product : %s is bundled product. Please set the order policy : On Demand.' %(line.product_id.name))
        return True
    

