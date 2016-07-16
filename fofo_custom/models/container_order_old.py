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

from datetime import datetime 
import datetime as DT
import openerp
import openerp.tools as tools
from openerp.tools.translate import _
from openerp.tools import float_repr, float_round, frozendict, html_sanitize
import simplejson
from openerp import SUPERUSER_ID, registry
import time

import base64
import datetime as DT
import functools
import logging
import pytz
import re
import xmlrpclib
from operator import itemgetter
from psycopg2 import Binary
from openerp import models, fields, api, _
import openerp.addons.decimal_precision as dp
from openerp.exceptions import except_orm, Warning, RedirectWarning

from openerp.tools.float_utils import float_compare

class container_size(models.Model):
    _name = "container.size"
    
    name = fields.Char('Container Size', required=True)
    max_weight = fields.Float('Max Weight', help="Max Weight of Container.")
    max_volume = fields.Float('Max Volume', help="Max Volume of Container.")
    

class container_order_line(models.Model):
    _name = 'container.order.line'

    @api.one
    @api.depends('po_line_id','product_qty','product_id', 'state')
    def _compute_volume(self):
        self.volume = 0.0
        self.weight = 0.0
        for line in self:
            self.volume = line.product_id.volume * line.product_qty
            self.weight = line.product_id.weight * line.product_qty

    @api.one
    @api.depends('product_packaging','product_id', 'product_qty', 'state')
    def _number_packages(self):
        self.number_packages = 0
        for line in self:
            try:
                self.number_packages = int((line.product_qty+line.product_packaging.qty-0.0001) / line.product_packaging.qty)
            except:
                self.number_packages = 0

    @api.one
    @api.depends('product_id', 'product_qty', 'state', 'taxes_id', 'price_unit')
    def _amount_line(self):
        res = {}
        cur_obj=self.env['res.currency']
        tax_obj = self.env['account.tax']
        for line in self:
            taxes = line.taxes_id.compute_all(line.price_unit, line.product_qty, line.product_id, line.order_id.partner_id)
            cur = line.order_id.pricelist_id.currency_id
            self.price_subtotal = cur.round(taxes['total'])

    po_line_id = fields.Many2one('purchase.order.line', string='Purchase Order Line')
    container_order_id = fields.Many2one('container.order', string='Container Order')
    product_id = fields.Many2one('product.product', string='Product', related='po_line_id.product_id', readonly=True)
    product_qty = fields.Float('Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
    product_uom = fields.Many2one('product.uom', 'Product Unit of Measure', required=True)
#    co_product_qty = fields.Float('Contained Quantity', digits=dp.get_precision('Product Unit of Measure'), required=True)
#    co_product_uom = fields.Many2one('product.uom', 'Product Unit of Measure', required=True)

    price_unit = fields.Float('Unit Price', required=True, digits= dp.get_precision('Product Price'))
    state =  fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'),('done', 'Done')],
                                  'Status', readonly=False, copy=False)
    taxes_id = fields.Many2many('account.tax', 'container_order_line_tax', 'ord_id', 'tax_id', 'Taxes')
    date_planned = fields.Date('Scheduled Date', required=True, select=True)
    account_analytic_id = fields.Many2one('account.analytic.account', 'Analytic Account')
    name = fields.Text('Description', required=True)
    company_id = fields.Many2one('res.company', string='Company')
    move_ids =  fields.One2many('stock.move', 'purchase_line_id', 'Reservation', readonly=True, ondelete='set null')
    invoice_lines =  fields.Many2many('account.invoice.line', 'container_order_line_invoice_rel',
                                          'order_line_id', 'invoice_id', 'Invoice Lines',
                                          readonly=True, copy=False)
    weight = fields.Float(string="Weight", digits=dp.get_precision('Account'), store=True, compute='_compute_volume')
    volume = fields.Float(string="Volume", digits=dp.get_precision('Account'), store=True, compute='_compute_volume')
    reference = fields.Char(related = 'po_line_id.order_id.name', string='PO number')
    purchase_by_container = fields.Boolean(related = 'po_line_id.order_id.purchase_by_container', string='Purchase by Container', store=True)
    purchase_by_container_flag = fields.Boolean('Selected in Container Order')
    supplier_id = fields.Many2one('res.partner', related='po_line_id.order_id.partner_id', string="Supplier")
    product_packaging =  fields.Many2one('product.packaging', string='Packaging')
    product_tmpl_id = fields.Many2one(related='product_id.product_tmpl_id', type='many2one', relation='product.template', string='Product Template')
    number_packages =  fields.Integer(compute=_number_packages, string='Total Number of Packages', store=True)
    qty_package = fields.Float(string='Quantity / Package')
    price_subtotal = fields.Float(compute=_amount_line, string='Subtotal', digits= dp.get_precision('Account'))
    order_id = fields.Many2one(relation='purchase.order',related='po_line_id.order_id', string='Purchase Order')
    
    @api.onchange('po_line_id')
    def on_change_po_line(self):
        if self.po_line_id:
            line_data = self.env['purchase.order.line'].browse(self.po_line_id.id)
            
            self.product_id = line_data.product_id.id
            self.product_qty = line_data.product_qty
            self.product_uom= line_data.product_uom
#            self.co_product_qty = line_data.product_qty
#            self.co_product_uom= line_data.product_uom
            self.price_unit = line_data.price_unit
            self.date_planned = line_data.date_planned
            self.name = line_data.name
            self.product_packaging = line_data.product_packaging.id
            self.qty_package = line_data.qty_package
            self.number_packages = line_data.number_packages
            if line_data.taxes_id:
                taxes = []
                for tax in line_data.taxes_id:
                    taxes.append(tax.id)
                self.taxes_id = taxes

class container_order(models.Model):
    _inherit = ['mail.thread']
    _name = "container.order"
    _rec_name = "number"
    _order = 'date desc, id desc'
    
    @api.one
    @api.depends('co_line_ids','state')
    def _compute_amount(self):
        self.amount_untaxed = 0.0
        self.amount_tax = 0.0
        for line_id in self.co_line_ids:
            self.amount_untaxed += line_id.price_subtotal
        for line in self.co_line_ids:
                if line.taxes_id:
                    for c in line.taxes_id.compute_all(line.price_unit, line.product_qty, line.product_id, line.supplier_id)['taxes']:
                        self.amount_tax += c.get('amount', 0.0)
        self.amount_total = self.amount_untaxed + self.amount_tax

    @api.multi
    def _get_picking_in(self):
        obj_data = self.env['ir.model.data']
        type_obj = self.env['stock.picking.type']
        user_obj = self.env['res.users']
        company_id = self.env.user.company_id.id
        types = type_obj.search([('code', '=', 'incoming'), ('warehouse_id.company_id', '=', company_id)])
        if not types:
            types = type_obj.search([('code', '=', 'incoming'), ('warehouse_id', '=', False)])
            if not types:
                raise Warning(_('Make sure you have at least an incoming picking type defined.'))
        return types[0]
        
    @api.one
    @api.depends('co_line_ids','state')
    def _get_picking_ids(self):
        if self.ids:
            res = {}
            list_picks = []
            for po_id in self.ids:
                res[po_id] = []
            query = """
            SELECT picking_id, po.id FROM stock_picking p, stock_move m, purchase_order_line pol, container_order po
                WHERE po.id in %s and po.id = pol.container_id and pol.id = m.purchase_line_id and m.picking_id = p.id
                GROUP BY picking_id, po.id
                 
            """
            self._cr.execute(query, (tuple(self.ids), ))
            picks = self._cr.fetchall()
            for pick_id, po_id in picks:
                list_picks.append(pick_id)
            self.picking_ids = list_picks

    @api.multi
    def onchange_picking_type_id(self, picking_type_id):
        value = {}
        if picking_type_id:
            picktype = self.env["stock.picking.type"].browse(picking_type_id)
            if picktype.default_location_dest_id:
                value.update({'location_id': picktype.default_location_dest_id.id, 'related_usage': picktype.default_location_dest_id.usage})
            value.update({'related_location_id': picktype.default_location_dest_id.id})
        return {'value': value}
        
    @api.multi
    @api.depends('picking_ids', 'invoice_ids')
    def _count_all(self):
        self.shipment_count = len(self.picking_ids)
        self.invoice_count = len(self.invoice_ids)

    @api.multi
    def view_invoice(self):
        invoice_ids = []
        for po in self:
            invoice_ids += [invoice.id for invoice in po.invoice_ids]
        result = self.env.ref('account.action_invoice_tree2')
        result = result.read()[0]
        result['context'] = {}
        if len(invoice_ids) > 1:
            result['domain'] = "[('id','in', [" + ','.join(map(str, invoice_ids)) + "])]"
        else:
            result['domain'] = "[('id','in', [" + ','.join(map(str, invoice_ids)) + "])]" #Ecosoft TODO: open single form view instead of list.
        return result

    @api.multi
    def view_picking(self):
        pick_ids = []
        for po in self:
            pick_ids += [picking.id for picking in po.picking_ids]

        result = self.env.ref('stock.action_picking_tree')
        result = result.read()[0]
        
        result['context'] = {}
        if len(pick_ids) > 1:
            result['domain'] = "[('id','in', [" + ','.join(map(str, pick_ids)) + "])]"
        else:
            result['domain'] = "[('id','in', [" + ','.join(map(str, pick_ids)) + "])]" #Ecosoft todo: open single form view instead of list.
        return result

    @api.multi
    def onchange_container_size(self, container_size=False):
        res = {}
        res['value'] = {}
        size_obj = self.env['container.size']
        if not container_size:
            return {}
        if container_size:
            size = size_obj.browse(container_size)
            res['value'].update({'max_weight': size.max_weight or 0.0, 'max_volume': size.max_volume or 0.0})
        return res

    @api.multi
    def onchange_shipper_cost(self, outbound_shipper_expense_id=False, inbound_shipper_expense_id=False):
        res = {}
        res['value'] = {}
        product_obj = self.env['product.product']
        if not outbound_shipper_expense_id and not inbound_shipper_expense_id:
            return {}
        if outbound_shipper_expense_id:
            product = product_obj.browse(outbound_shipper_expense_id)
            res['value'].update({'outbound_shipper_cost': product.standard_price or 0.0})
        if inbound_shipper_expense_id:
            product = product_obj.browse(inbound_shipper_expense_id)
            res['value'].update({'inbound_shipper_cost': product.standard_price or 0.0})
        return res

    @api.multi
    @api.depends('picking_ids', 'picking_ids.state', 'state')#TODO:
    def _check_received(self):
        for order in self:
            if order.state == 'confirm' and order.picking_ids:
                for picking in order.picking_ids:
                    is_received = True
                    if picking.state != 'done':
                        is_received = False
                order.is_received = is_received

    @api.one
    @api.depends('co_line_ids','co_line_ids.weight', 'co_line_ids.volume', 'state')
    def _total_weight_volume(self):
        self.total_weight = 0.0
        self.total_volume = 0.0
        for line in self:
            for l in line.co_line_ids:
                self.total_weight += l.weight
                self.total_volume += l.volume

    _track = {
        'state': {
            'fofo_custom.mt_co_confirmed': lambda self, cr, uid, obj, ctx=None: obj.state == 'sent_to_shipper',
            'fofo_custom.mt_co_approved': lambda self, cr, uid, obj, ctx=None: obj.state == 'confirm',
            'fofo_custom.mt_co_done': lambda self, cr, uid, obj, ctx=None: obj.state == 'done',
        },
    }

    number = fields.Char('Number', readonly=True, copy=False)
    container_shipper_number = fields.Char('Shipper Container Number', readonly=False, copy=False, help='Container number is provided by shipper after the loading process is complete.')
    max_weight = fields.Float('Max Weight Container', help="Max Weight of Container.")
    max_volume = fields.Float('Max Volume Container', help="Max Volume of Container.")
    container_size = fields.Many2one('container.size', string="Container Size", required=True)
    date = fields.Date('Date', default=fields.Date.today(), required=True, copy=False)
    outbound_shipper_id = fields.Many2one('res.partner', string="Outbound Shipper Name")
    inbound_shipper_id = fields.Many2one('res.partner', string="Inbound Shipper Name")
    load_date = fields.Date("Loading Date")
    ship_date = fields.Date('Shipping Date')
    #etd = fields.Float('ETD', help="Estimated Time of Departure.")
    arrive_date = fields.Date('Arrival Date')
    order_line_ids = fields.Many2many('purchase.order.line', 'container_po_rel', 'container_id', 'po_line_id', 'Purchase Lines'
                                      )
    state = fields.Selection([
        ('draft','Draft'),
        ('sent_to_shipper','Sent to Shipper'),
        ('confirm','Confirmed'),
        ('done','Done'),('cancel','Cancelled'),], string='Status', default='draft',
        track_visibility='onchange', copy=False)
    resp_user_id = fields.Many2one('res.users', string="Responsible User", default = lambda self:self.env.uid)
    confirm_date = fields.Date('Date Confirmed', copy=False)
    company_id = fields.Many2one('res.company', string="Company", required=True, default=lambda self: self.env['res.company']._company_default_get('container.order'))
    reference = fields.Char('Reference')
    notes = fields.Text('Notes')
    confirm_by_id = fields.Many2one('res.users', 'Confirmed by', copy=False)
    is_received = fields.Boolean('Received', readonly=True, copy=False, compute=_check_received)
    amount_untaxed = fields.Float(string='Subtotal', digits=dp.get_precision('Product Price'),
        store=True, readonly=True, compute='_compute_amount', track_visibility='always')
    amount_tax = fields.Float(string='Tax', digits=dp.get_precision('Product Price'),
        store=True, readonly=True, compute='_compute_amount')
    amount_total = fields.Float(string='Total', digits=dp.get_precision('Product Price'),
        store=True, readonly=True, compute='_compute_amount')
    incoterm_id = fields.Many2one('stock.incoterms', string="Incoterm")
    inbound_shipper_expense_id = fields.Many2one('product.product', string="Inbound Shipper Expense")
    outbound_shipper_expense_id = fields.Many2one('product.product', string="Outbound Shipper Expense")
    inbound_shipper_cost = fields.Float(string="Inbound Shipper Cost", digits=dp.get_precision('Product Price'))
    outbound_shipper_cost = fields.Float(string="Outbound Shipper Cost", digits=dp.get_precision('Product Price'))

    picking_type_id = fields.Many2one('stock.picking.type', string='Deliver To', help="This will determine picking type of incoming shipment", required=True,
                                           default=_get_picking_in)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.user.company_id.currency_id.id)
    location_id = fields.Many2one('stock.location', string='Destination', required=True, domain=[('usage','<>','view')])

    picking_ids =  fields.One2many('stock.picking', 'container_id', compute=_get_picking_ids, string='Picking List', store=True, copy=False, readonly=True)
    invoice_ids =  fields.One2many('account.invoice', 'container_id', string='Shipper Invoices', readonly=True, copy=False)

    shipment_count = fields.Integer(compute=_count_all, string='Incoming Shipments', copy=False)
    invoice_count = fields.Integer(compute=_count_all, string='Shipper Invoices', copy=False)
    total_weight =  fields.Float(compute=_total_weight_volume, string='Total Weight', store=True)
    total_volume =  fields.Float(compute=_total_weight_volume, string='Total Volume', store=True)
    co_line_ids = fields.One2many('container.order.line','container_order_id', string='Container Order Lines' )


    @api.one
    @api.model
    def unlink(self):
        unlink_ids = []
        s = self
        if s.state in ['draft','cancel']:
            unlink_ids.append(s.id)
        else:
            raise Warning(_('In order to delete a container order, you must cancel it first.'))
        return super(container_order, self).unlink()

    @api.model
    def create(self, vals):
        purchase_line_obj = self.env['purchase.order.line']
        if not vals.get('number'):
            vals['number'] = self.env['ir.sequence'].get('container.order')
        res = super(container_order, self).create(vals)
        if vals.get('co_line_ids', False):
            for line in vals['co_line_ids']:
                if line and line[2]:
                    line_record = purchase_line_obj.browse(line[2]['po_line_id'])
                    if line_record.product_id:
                        product_record = line_record.product_id.browse()# This will allow to call function field on product object. (_count_qty_contained).
                    line_record.write({'purchase_by_container_flag': True})# This will allow to call function field on product object. (_count_qty_contained).
        return res

    @api.multi
    def write(self, vals):
        purchase_line_obj = self.env['purchase.order.line']
        res = super(container_order, self).write(vals)
        if vals.get('co_line_ids', False):
            for line in vals['co_line_ids']:
                if line and line[2] and 'po_line_id' in line[2]:
                    line_record = purchase_line_obj.browse(line[2]['po_line_id'])
                    if line_record.product_id:
                        product_record = line_record.product_id.browse()# This will allow to call function field on product object. (_count_qty_contained).
                    line_record.write({'purchase_by_container_flag': True})# This will allow to call function field on product object. (_count_qty_contained).
        return res

    @api.multi
    def _choose_account_from_po_line(self, product_id):
        property_obj = self.env['ir.property']
        if product_id:
            acc_id = product_id.property_account_expense.id
            if not acc_id:
                acc_id = product_id.categ_id.property_account_expense_categ.id
            if not acc_id:
                raise Warning( _('Define an expense account for this product: "%s" (id:%d).') % (product_id.name, product_id.id,))
        else:
            acc_id = property_obj.get('property_account_expense_categ', 'product.category').id
        return acc_id
    
    @api.multi
    def _prepare_inv_line(self, container_id, product_id, account_id, cost_type='inbound'):
        price_unit = False
        if cost_type == 'inbound':
            price_unit = container_id.inbound_shipper_cost
        if cost_type == 'outbound':
            price_unit = container_id.outbound_shipper_cost
        return {
            'name': product_id.name,
            'account_id': account_id,
            'price_unit': price_unit or product_id.standard_price or 0.0,
            'quantity': 1.0,
            'product_id': product_id.id or False,
            'uos_id': product_id.uom_id.id or False,
#            'invoice_line_tax_id': [],
#            'account_analytic_id': order_line.account_analytic_id.id or False,
        }

    @api.multi
    def _prepare_invoice(self, order, partner_id, line_ids, type='Inbound Supplier Invoice'):
        journal_ids = self.env['account.journal'].search(
                            [('type', '=', 'purchase'),
                                      ('company_id', '=', order.company_id.id)],
                            limit=1)
        if not journal_ids:
            raise Warning( _('Define purchase journal for this company: "%s" (id:%d).') % \
                    (order.company_id.name, order.company_id.id))
        return {
            'name': order.number,
            'reference': type + ' - ' + order.number,
            'account_id': partner_id.property_account_payable.id,
            'type': 'in_invoice',
            'partner_id': partner_id.id,
            'currency_id': order.currency_id.id,
            'journal_id': len(journal_ids) and journal_ids.id or False,
            'invoice_line': [(6, 0, line_ids)],
            'origin': order.number,
            'fiscal_position': False,
            'payment_term': partner_id.property_supplier_payment_term.id or False,
            'company_id': order.company_id.id,
        }

    @api.multi
    def action_invoice_create(self):
        inv_obj = self.env['account.invoice']
        inv_line_obj = self.env['account.invoice.line']
        res = False
        uid_company_id = self.env.user.company_id.id

        for order in self:
            if not order.inbound_shipper_id or not order.outbound_shipper_id:
                    raise Warning( _('Please define Inbound Shipper and Outbound Shipper.'))
            if not order.inbound_shipper_expense_id or not order.outbound_shipper_expense_id:
                    raise Warning( _('Please define Inbound Shipper Expense and Outbound Shipper Expense.'))
            res = []

            # For inbound shipper invoice.
            inv_lines = []
            acc_id = self._choose_account_from_po_line(order.inbound_shipper_expense_id)
            inv_line_data = self._prepare_inv_line(order, order.inbound_shipper_expense_id, acc_id, cost_type='inbound')
            inv_line_id = inv_line_obj.create(inv_line_data)
            inv_lines.append(inv_line_id.id)
            # get invoice data and create invoice
            inv_data = self._prepare_invoice(order, order.inbound_shipper_id, inv_lines)
            inv_id = inv_obj.create(inv_data)
            # compute the invoice
            inv_id.button_compute(set_total=True)
            order.write({'invoice_ids': [(4, inv_id.id)]})
            res.append(inv_id.id)

            # For outbound shipper invoice.
            inv_lines = []
            acc_id = self._choose_account_from_po_line(order.outbound_shipper_expense_id)
            inv_line_data = self._prepare_inv_line(order, order.outbound_shipper_expense_id, acc_id, cost_type='outbound')
            inv_line_id = inv_line_obj.create(inv_line_data)
            inv_lines.append(inv_line_id.id)
            # get invoice data and create invoice
            inv_data = self._prepare_invoice(order, order.outbound_shipper_id, inv_lines,type='Outbound Supplier Invoice')
            inv_id = inv_obj.create(inv_data)
            # compute the invoice
            inv_id.button_compute(set_total=True)
            order.write({'invoice_ids': [(4, inv_id.id)]})
            res.append(inv_id.id)
        return res

    
    @api.multi
    def send_to_shipper(self):
        ir_model_data = self.env['ir.model.data']
        try:
            if self._context.get('send_to_inbound', False):
                template_id = ir_model_data.get_object_reference('fofo_custom', 'email_template_container_inbound_shipper')[1]
            else:
                template_id = ir_model_data.get_object_reference('fofo_custom', 'email_template_container_outbound_shipper')[1]
        except ValueError:
            template_id = False
        try:
            compose_form_id = ir_model_data.get_object_reference('mail', 'email_compose_message_wizard_form')[1]
        except ValueError:
            compose_form_id = False 
        ctx = dict(self._context)
        ctx.update({
            'default_model': 'container.order',
            'default_res_id': self._ids[0],
            'default_use_template': bool(template_id),
            'default_template_id': template_id,
            'default_composition_mode': 'comment',
        })
        if not self.state == 'confirm':# If state is already confirm no need to go back to change state.
            self.write({'state': 'sent_to_shipper'})
        return {
            'name': _('Compose Email'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'mail.compose.message',
            'views': [(compose_form_id, 'form')],
            'view_id': compose_form_id,
            'target': 'new',
            'context': ctx,
        }
        
    @staticmethod
    @api.multi
    def date_to_datetime(self, userdate):
        """ Convert date values expressed in user's timezone to
        server-side UTC timestamp, assuming a default arbitrary
        time of 12:00 AM - because a time is needed.
        :param str userdate: date string in in user time zone
        :return: UTC datetime string for server-side use
        """
        user_date = DT.datetime.strptime(userdate, tools.DEFAULT_SERVER_DATE_FORMAT)
        if self._context and self._context.get('tz'):
            tz_name = self._context['tz']
        else:
            tz_name = self.pool.get('res.users').read(self._cr, SUPERUSER_ID, self.env.uid, ['tz'])['tz']
        if tz_name:
            utc = pytz.timezone('UTC')
            context_tz = pytz.timezone(tz_name)
            user_datetime = user_date + DT.timedelta(hours=12.0)
            local_timestamp = context_tz.localize(user_datetime, is_dst=False)
            user_datetime = local_timestamp.astimezone(utc)
            return user_datetime.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)
        return user_date.strftime(tools.DEFAULT_SERVER_DATETIME_FORMAT)

    @api.multi
    def _prepare_order_line_move(self, order, order_line, picking_id, group_id):
        product_uom = self.env['product.uom']
        price_unit = order_line.price_unit
        if order_line.product_uom.id != order_line.product_id.uom_id.id:
            price_unit *= order_line.product_uom.factor / order_line.product_id.uom_id.factor
        if order.currency_id.id != order.company_id.currency_id.id:
            #we don't round the price_unit, as we may want to store the standard price with more digits than allowed by the currency
            price_unit = self.env['res.currency'].compute(order.currency_id.id, order.company_id.currency_id.id, price_unit, round=False)
        res = []
        move_template = {
            'name': order_line.name or '',
            'product_id': order_line.product_id.id,
            'product_uom': order_line.product_uom.id,
            'product_uos': order_line.product_uom.id,
            'date': order.date,
            'date_expected': self.date_to_datetime(self, order_line.date_planned),
            'location_id': order_line.supplier_id.property_stock_supplier.id,
            'location_dest_id': order.location_id.id,
            'picking_id': picking_id.id,
            'partner_id': order_line.supplier_id.id,
            'move_dest_id': False,
            'state': 'draft',
            'purchase_line_id': order_line.id,
            'company_id': order.company_id.id,
            'price_unit': price_unit,
            'picking_type_id': order.picking_type_id.id,
            'group_id': group_id.id,
            'procurement_id': False,
            'origin': order.number,
            'route_ids': order.picking_type_id.warehouse_id and [(6, 0, [x.id for x in order.picking_type_id.warehouse_id.route_ids])] or [],
            'warehouse_id':order.picking_type_id.warehouse_id.id,
            'invoice_state': '2binvoiced',#For moment use static. Todo Ecosoft Check.
        }

        diff_quantity = order_line.product_qty
        for procurement in order_line.procurement_ids:
            procurement_qty = product_uom._compute_qty(procurement.product_uom.id, procurement.product_qty, to_uom_id=order_line.product_uom.id)
            tmp = move_template.copy()
            tmp.update({
                'product_uom_qty': min(procurement_qty, diff_quantity),
                'product_uos_qty': min(procurement_qty, diff_quantity),
                'move_dest_id': procurement.move_dest_id.id,  #move destination is same as procurement destination
                'group_id': procurement.group_id and procurement.group_id.id or group_id and group_id.id or False,  #move group is same as group of procurements if it exists, otherwise take another group
                'procurement_id': procurement.id,
                #'invoice_state': procurement.rule_id.invoice_state or (procurement.location_id and procurement.location_id.usage == 'customer' and procurement.invoice_state=='2binvoiced' and '2binvoiced') or (order.invoice_method == 'picking' and '2binvoiced') or 'none', #dropship case takes from sale
                'invoice_state': '2binvoiced',
                'propagate': procurement.rule_id.propagate,
            })
            diff_quantity -= min(procurement_qty, diff_quantity)
            res.append(tmp)
        #if the order line has a bigger quantity than the procurement it was for (manually changed or minimal quantity), then
        #split the future stock move in two because the route followed may be different.
        if float_compare(diff_quantity, 0.0, precision_rounding=order_line.product_uom.rounding) > 0:
            move_template['product_uom_qty'] = diff_quantity
            move_template['product_uos_qty'] = diff_quantity
            res.append(move_template)
        return res
    
    @api.multi
    def _create_stock_moves(self, order, order_lines, picking_id=False):
        stock_move = self.env['stock.move']
        todo_moves = []
        new_group = self.env["procurement.group"].create({'name': order.number, })#'partner_id': order.partner_id.id

        for order_line in order_lines:
            if not order_line.product_id:
                continue

            if order_line.product_id.type in ('product', 'consu'):
                for vals in self._prepare_order_line_move(order, order_line, picking_id, new_group):
                    move = stock_move.create(vals)
                    todo_moves.append(move.id)
        stock_move_ids = self.env['stock.move'].browse(todo_moves)
        todo_moves = stock_move_ids.action_confirm()
        stock_move_ids.force_assign()

    @api.multi
    def action_picking_create(self):
        for order in self:
            picking_vals = {
                'picking_type_id': order.picking_type_id.id,
                #'partner_id': order.partner_id.id,
                'date': order.date,
                'origin': order.number,
                'container_id': order.id,
            }
            picking_id = self.env['stock.picking'].create(picking_vals)
            self._create_stock_moves(order, order.order_line_ids, picking_id)

    @api.multi
    def confirm_order(self):
        purchase_line_obj = self.env['purchase.order.line']
        self.action_picking_create()
        for line in self.order_line_ids:
            line_purchase = purchase_line_obj.browse(line.id)
            line_purchase.write({'container_id': self.ids[0], 'state': 'contained'})
            line.order_id.signal_workflow('purchase_contained')
            line.order_id.write({'state': 'contained'})#todo fix: check if all order lines are contained then change state.
        self.write({'state': 'confirm', 'confirm_by_id': self.env.uid, 'confirm_date': time.strftime('%Y-%m-%d')})

    @api.multi
    def action_done(self):
        purchase_obj = self.env['purchase.order']
        order_dict = {}
        for container in self:
            container.write({'state': 'done'})
            for purchase_line in container.order_line_ids:
                order_dict[purchase_line.order_id.id] = False
                for line in purchase_line.order_id.order_line:
                    if line.state != 'contained' and line.state != 'done' and line.state != 'cancel':
                        order_dict[purchase_line.order_id.id] = False
                    elif line.state == 'contained' and line.container_id.state == 'done':
                        order_dict[purchase_line.order_id.id] = True
        for order in order_dict:
            # Make related all purchase orders to done.
            purchase = purchase_obj.browse(order)
            purchase.wkf_po_done()
            purchase.write({'shipped': True}) #Received field on PO now ticked.
        
    @api.multi
    def cancel_order(self):
        for order in self:
            if order.state == 'confirm':
                raise Warning(_('You can not cancel container order which already confirmed. Please first cancle all related pickings and invoices.'))
        self.write({'state': 'cancel'})

# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
