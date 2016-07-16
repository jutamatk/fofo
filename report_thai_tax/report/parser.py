# -*- encoding: utf-8 -*-
##############################################################################
#
#
##############################################################################
import sys
sys.path.insert(0, '/home/kittiu/workspace/common/common')
sys.path.insert(0, '/opt/odoo/common')
import jasper_reports
from openerp.osv import fields, osv
import datetime

def report_thai_tax_parser( cr, uid, ids, data, context ):
    return {
        'parameters': {	
            'company_id': data['form']['company_id'],
            'period_id': data['form']['period_id'],
            'tax_id': data['form']['tax_id'],
            'base_code_id': data['form']['base_code_id'],
            'tax_code_id': data['form']['tax_code_id'],
            'type_tax_use': data['form']['type_tax_use'],
        },
   }

jasper_reports.report_jasper(
    'report.report_thai_tax',
    'account.move',
    parser=report_thai_tax_parser
)
