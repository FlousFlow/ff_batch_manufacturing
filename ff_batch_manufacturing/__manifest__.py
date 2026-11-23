{
    'name': 'Batch Manufacturing',
    'summary': 'Create and manufacture multiple products from one batch sheet',
    'description': """
Flous Flow Batch Manufacturing
==============================

Create one batch sheet containing multiple manufacturing products. Every line
uses its own native Odoo Manufacturing Order, so components can be reviewed and
customized independently without changing the master BoM. Confirm & Manufacture
executes eligible simple manufacturing orders through native MRP workflows.
    """,
    'version': '20.0.1.0.1',
    'category': 'Manufacturing/Manufacturing',
    'author': 'Flous Flow',
    'website': 'https://flousflow.com',
    'support': 'support@flousflow.com',
    'license': 'LGPL-3',
    'images': ['static/description/banner.jpg'],
    # The standard quantity-at-date widget is registered by Sales and reused
    # here for the native availability indicator.
    'depends': ['mrp', 'sale'],
    'data': [
        'security/ir.access.csv',
        'data/ff_batch_manufacturing_data.xml',
        'views/ff_batch_manufacturing_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': False,
    'auto_install': False,
}
