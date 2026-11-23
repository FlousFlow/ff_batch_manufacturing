from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class FfBatchManufacturing(models.Model):
    _name = 'ff.batch.manufacturing'
    _description = 'Batch Manufacturing Sheet'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'manufacturing_date desc, id desc'

    name = fields.Char(string='Batch Reference', default='New', readonly=True, copy=False, tracking=True)
    company_id = fields.Many2one(
        'res.company', string='Company', required=True, default=lambda self: self.env.company,
        index=True, tracking=True,
    )
    manufacturing_date = fields.Date(
        string='Manufacturing Date', required=True, default=fields.Date.context_today, tracking=True,
    )
    picking_type_id = fields.Many2one(
        'stock.picking.type', string='Manufacturing Operation Type', required=True,
        domain="[('code', '=', 'mrp_operation'), ('company_id', '=', company_id)]",
        default=lambda self: self.env['stock.picking.type'].search([
            ('code', '=', 'mrp_operation'), ('company_id', '=', self.env.company.id)
        ], limit=1), check_company=True,
    )
    location_src_id = fields.Many2one(
        'stock.location', string='Component Source Location', required=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        check_company=True,
    )
    location_dest_id = fields.Many2one(
        'stock.location', string='Finished Product Destination Location', required=True,
        domain="[('usage', '=', 'internal'), ('company_id', 'in', [company_id, False])]",
        check_company=True,
    )
    line_ids = fields.One2many('ff.batch.manufacturing.line', 'batch_id', string='Manufacturing Lines')
    state = fields.Selection([('draft', 'Draft'), ('done', 'Done')], default='draft', tracking=True, index=True)
    user_id = fields.Many2one('res.users', string='Responsible', default=lambda self: self.env.user, tracking=True)
    note = fields.Html(string='Notes')
    production_ids = fields.Many2many(
        'mrp.production', compute='_compute_production_ids', string='Manufacturing Orders',
    )
    line_count = fields.Integer(string='Number of Lines', compute='_compute_totals', store=True)
    total_planned_qty = fields.Float(string='Total Planned Quantity', compute='_compute_totals', store=True)
    total_estimated_cost = fields.Monetary(string='Total Estimated Cost', compute='_compute_totals', store=True)
    total_actual_cost = fields.Monetary(string='Total Actual Cost', compute='_compute_totals', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', string='Currency', readonly=True)

    @api.depends('line_ids.production_id', 'line_ids.estimated_cost', 'line_ids.actual_cost', 'line_ids.product_qty', 'line_ids.uom_id')
    def _compute_totals(self):
        for batch in self:
            batch.line_count = len(batch.line_ids)
            batch.total_estimated_cost = sum(batch.line_ids.mapped('estimated_cost'))
            batch.total_actual_cost = sum(batch.line_ids.mapped('actual_cost'))
            batch.total_planned_qty = 0.0
            if batch.line_ids:
                first = batch.line_ids[0]
                def uom_root(uom):
                    while uom.relative_uom_id:
                        uom = uom.relative_uom_id
                    return uom

                if all(uom_root(line.uom_id) == uom_root(first.uom_id) for line in batch.line_ids):
                    batch.total_planned_qty = sum(
                        line.uom_id._compute_quantity(line.product_qty, first.uom_id)
                        for line in batch.line_ids
                    )

    @api.depends('line_ids.production_id')
    def _compute_production_ids(self):
        for batch in self:
            batch.production_ids = [Command.set(batch.line_ids.mapped('production_id').ids)]

    @api.constrains('company_id', 'picking_type_id', 'location_src_id', 'location_dest_id')
    def _check_company_locations(self):
        for batch in self:
            batch._check_company()
            if batch.picking_type_id and batch.picking_type_id.code != 'mrp_operation':
                raise ValidationError(_('The operation type must be a Manufacturing operation type.'))
            for location in batch.location_src_id | batch.location_dest_id:
                if location.usage != 'internal':
                    raise ValidationError(_('Manufacturing locations must be internal stock locations.'))
                if location.company_id and location.company_id != batch.company_id:
                    raise ValidationError(_('The selected location belongs to another company.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('ff.batch.manufacturing') or 'New'
        batches = super().create(vals_list)
        batches._propagate_default_locations()
        return batches

    def write(self, vals):
        result = super().write(vals)
        if {'location_src_id', 'location_dest_id'} & vals.keys():
            self._propagate_default_locations()
        return result

    @api.onchange('location_src_id', 'location_dest_id')
    def _onchange_locations(self):
        """Keep existing in-form lines aligned when header locations change."""
        for batch in self:
            if batch.state != 'draft':
                continue
            for line in batch.line_ids:
                line.location_src_id = batch.location_src_id
                line.location_dest_id = batch.location_dest_id

    def _propagate_default_locations(self):
        for batch in self:
            if batch.state != 'draft':
                continue
            for line in batch.line_ids:
                line.with_context(ff_batch_sync=True).write({
                    'location_src_id': batch.location_src_id.id,
                    'location_dest_id': batch.location_dest_id.id,
                })

    def _validate_for_execution(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only a draft batch can be confirmed and manufactured.'))
        if not self.line_ids:
            raise UserError(_('Add at least one manufacturing line before confirming the batch.'))
        for line in self.line_ids:
            line._validate_line()

    def action_confirm_manufacture(self):
        for batch in self:
            batch._validate_for_execution()
            batch.line_ids._sync_productions()
            productions = batch.line_ids.mapped('production_id')
            productions.action_confirm()
            for production in productions:
                if production.workorder_ids:
                    raise UserError(_(
                        'Manufacturing order %s cannot be completed automatically because its BoM '
                        'contains work center operations, which created work orders. Open the '
                        'manufacturing order, complete the work orders from the Work Orders tab, '
                        'then mark the manufacturing order as done. This is unrelated to lot/serial tracking.',
                        production.display_name,
                    ))
                production.action_assign()
                result = production.button_mark_done()
                if isinstance(result, dict):
                    raise UserError(_(
                        'Manufacturing order %s requires an additional native Odoo step before it can be completed.',
                        production.display_name,
                    ))
                if production.state != 'done':
                    raise UserError(_('Manufacturing order %s was not completed.', production.display_name))
            batch.write({'state': 'done'})
        return True

    def action_view_manufacturing_orders(self):
        self.ensure_one()
        action = self.env['ir.actions.actions']._for_xml_id('mrp.action_mrp_production_form')
        action.update({
            'name': _('Manufacturing Orders'),
            'domain': [('id', 'in', self.production_ids.ids)],
            'context': {'create': False},
        })
        if len(self.production_ids) == 1:
            action.update({'view_mode': 'form', 'res_id': self.production_ids.id})
        return action

    def action_reset_to_draft(self):
        if not self.env.user.has_group('mrp.group_mrp_manager'):
            raise UserError(_('Only Manufacturing Managers can reset a batch.'))
        for batch in self:
            if batch.state == 'draft':
                continue
            productions = batch.production_ids
            if any(production.state == 'done' for production in productions):
                raise UserError(_(
                    'Batch %s cannot be reset because a linked Manufacturing Order is completed. Reverse the native stock operation first.',
                    batch.display_name,
                ))
            if any(production.state == 'cancel' for production in productions):
                raise UserError(_('Batch %s contains a cancelled Manufacturing Order and cannot be reset automatically.', batch.display_name))
            productions.action_reset_to_draft()
            batch.write({'state': 'draft'})
        return True


class FfBatchManufacturingLine(models.Model):
    _name = 'ff.batch.manufacturing.line'
    _description = 'Batch Manufacturing Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    batch_id = fields.Many2one('ff.batch.manufacturing', required=True, ondelete='cascade', index=True)
    company_id = fields.Many2one(related='batch_id.company_id', store=True, readonly=True)
    product_id = fields.Many2one(
        'product.product', string='Product', required=True,
        domain="[('type', '=', 'consu'), ('bom_ids.type', '=', 'normal'), ('bom_ids.active', '=', True)]",
        check_company=True,
    )
    product_qty = fields.Float(string='Quantity to Manufacture', required=True, default=1.0, digits='Product Unit')
    uom_id = fields.Many2one('uom.uom', string='Unit of Measure', required=True)
    bom_id = fields.Many2one('mrp.bom', string='Standard BoM', readonly=True, check_company=True)
    location_src_id = fields.Many2one('stock.location', string='Component Source Location', required=True, check_company=True)
    location_dest_id = fields.Many2one('stock.location', string='Finished Product Destination', required=True, check_company=True)
    production_id = fields.Many2one('mrp.production', string='Manufacturing Order', readonly=True, copy=False, ondelete='restrict')
    components_availability_state = fields.Selection([
        ('available', 'Available'), ('expected', 'Expected'), ('late', 'Late'), ('unavailable', 'Not Available'),
    ], string='Component Availability', compute='_compute_availability')
    components_availability = fields.Char(string='Availability', compute='_compute_availability')
    display_qty_widget = fields.Boolean(compute='_compute_qty_at_date_widget')
    qty_available_today = fields.Float(compute='_compute_qty_at_date_widget')
    virtual_available_at_date = fields.Float(compute='_compute_qty_at_date_widget')
    scheduled_date = fields.Datetime(compute='_compute_qty_at_date_widget')
    product_uom_qty = fields.Float(related='product_qty', readonly=True)
    product_uom_id = fields.Many2one(related='uom_id', readonly=True)
    qty_delivered = fields.Float(compute='_compute_qty_at_date_widget')
    estimated_cost = fields.Monetary(string='Estimated Cost', compute='_compute_costs', store=True)
    actual_cost = fields.Monetary(string='Actual Cost', compute='_compute_costs', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', readonly=True)
    manufacturing_state = fields.Selection(related='production_id.state', string='Manufacturing Status', readonly=True)
    components_customized = fields.Boolean(string='Customized Components', copy=False)

    @api.depends('product_id', 'product_qty', 'uom_id', 'production_id.move_raw_ids.product_id', 'production_id.move_raw_ids.product_uom_qty', 'location_src_id')
    def _compute_costs(self):
        for line in self:
            line.estimated_cost = sum(
                move.product_id.standard_price * move.product_uom_qty
                for move in line.production_id.move_raw_ids
            ) if line.production_id else line.product_id.standard_price * line.product_qty
            line.actual_cost = 0.0
            if line.production_id and 'value' in self.env['stock.move']._fields:
                line.actual_cost = abs(sum(line.production_id.move_raw_ids.filtered(lambda move: move.state == 'done').mapped('value')))

    @api.depends('production_id.state', 'production_id.components_availability', 'production_id.components_availability_state', 'production_id.move_raw_ids', 'location_src_id')
    def _compute_availability(self):
        Quant = self.env['stock.quant']
        for line in self:
            production = line.production_id
            if production and production.state not in ('draft', 'cancel', 'done'):
                line.components_availability = production.components_availability
                line.components_availability_state = production.components_availability_state
                continue
            if not production:
                line.components_availability = False
                line.components_availability_state = False
                continue
            unavailable = False
            for move in production.move_raw_ids:
                available = Quant._get_available_quantity(move.product_id, line.location_src_id, strict=True)
                required = move.product_id.uom_id._compute_quantity(move.product_qty, move.product_id.uom_id)
                if float_compare(available, required, precision_rounding=0.00001) < 0:
                    unavailable = True
                    break
            line.components_availability_state = 'unavailable' if unavailable else 'available'
            line.components_availability = _('Not Available') if unavailable else _('Available')

    @api.depends('product_id', 'product_qty', 'location_src_id', 'batch_id.state', 'batch_id.manufacturing_date')
    def _compute_qty_at_date_widget(self):
        Quant = self.env['stock.quant']
        for line in self:
            line.display_qty_widget = bool(line.product_id and line.batch_id.state == 'draft')
            line.qty_available_today = 0.0
            line.virtual_available_at_date = 0.0
            line.qty_delivered = 0.0
            line.scheduled_date = fields.Datetime.to_datetime(line.batch_id.manufacturing_date) if line.batch_id.manufacturing_date else False
            if line.product_id and line.location_src_id:
                available = Quant._get_available_quantity(line.product_id, line.location_src_id, strict=True)
                line.qty_available_today = available
                line.virtual_available_at_date = available

    @api.onchange('batch_id')
    def _onchange_batch_id(self):
        for line in self:
            if line.batch_id:
                line.location_src_id = line.batch_id.location_src_id
                line.location_dest_id = line.batch_id.location_dest_id
                line.uom_id = line.product_id.uom_id

    @api.onchange('product_id')
    def _onchange_product_id(self):
        for line in self:
            if line.product_id:
                line.uom_id = line.product_id.uom_id

    @api.constrains('product_qty')
    def _check_product_qty(self):
        for line in self:
            if float_is_zero(line.product_qty, precision_rounding=0.00001) or line.product_qty < 0:
                raise ValidationError(_('Manufacturing quantity must be greater than zero.'))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            batch = self.env['ff.batch.manufacturing'].browse(vals.get('batch_id'))
            if batch:
                vals.setdefault('location_src_id', batch.location_src_id.id)
                vals.setdefault('location_dest_id', batch.location_dest_id.id)
        lines = super().create(vals_list)
        for line in lines:
            line._ensure_standard_bom()
        lines._sync_productions()
        return lines

    def write(self, vals):
        vals = dict(vals)
        quantity_changed = 'product_qty' in vals
        product_changed = 'product_id' in vals or 'uom_id' in vals
        result = super().write(vals)
        if self.env.context.get('ff_batch_sync'):
            return result
        if product_changed:
            self._ensure_standard_bom()
            self._sync_productions(regenerate=True)
        elif quantity_changed:
            self._sync_productions(scale_quantity=True)
        if {'location_src_id', 'location_dest_id'} & vals.keys():
            self._sync_productions(regenerate=False)
        return result

    def _prepare_production_vals(self):
        self.ensure_one()
        return {
            'product_id': self.product_id.id,
            'product_qty': self.product_qty,
            'uom_id': self.uom_id.id,
            'company_id': self.company_id.id,
            'picking_type_id': self.batch_id.picking_type_id.id,
            'location_src_id': self.location_src_id.id,
            'location_dest_id': self.location_dest_id.id,
            'date_start': fields.Datetime.now(),
            'origin': self.batch_id.name,
        }

    def _sync_productions(self, regenerate=False, scale_quantity=False):
        for line in self:
            if line.batch_id.state != 'draft' or not line.product_id:
                continue
            if not line.production_id:
                production = self.env['mrp.production'].create(line._prepare_production_vals())
                line.with_context(ff_batch_sync=True).write({'production_id': production.id, 'bom_id': production.bom_id.id})
                continue
            production = line.production_id
            if production.state != 'draft':
                continue
            old_qty = production.product_qty
            if regenerate:
                production.with_context(skip_compute_move_raw_ids=False).write(line._prepare_production_vals())
            elif scale_quantity and not float_is_zero(old_qty, precision_rounding=0.00001):
                ratio = line.uom_id._compute_quantity(line.product_qty, production.uom_id) / old_qty
                production.with_context(skip_compute_move_raw_ids=True).write({
                    'product_qty': line.uom_id._compute_quantity(line.product_qty, production.uom_id),
                })
                for move in production.move_raw_ids:
                    move.product_uom_qty = move.product_uom_qty * ratio
            else:
                production.with_context(skip_compute_move_raw_ids=True).write({
                    'location_src_id': line.location_src_id.id,
                    'location_dest_id': line.location_dest_id.id,
                })
            line.with_context(ff_batch_sync=True).write({'bom_id': production.bom_id.id})

    def _validate_line(self):
        self.ensure_one()
        if not self.product_id or self.product_qty <= 0:
            raise UserError(_('Every manufacturing line needs a positive quantity and a product.'))
        if self.company_id != self.batch_id.company_id:
            raise UserError(_('The line company must match the batch company.'))
        if not self.production_id:
            raise UserError(_('Save the batch line before manufacturing.'))
        if not self.bom_id:
            raise UserError(_('Product %s has no standard manufacturing BoM.', self.product_id.display_name))

    def _ensure_standard_bom(self):
        for line in self:
            if not line.product_id:
                continue
            bom = self.env['mrp.bom']._bom_find(
                line.product_id,
                picking_type=line.batch_id.picking_type_id,
                company_id=line.company_id.id,
                bom_type='normal',
            ).get(line.product_id)
            if not bom:
                raise ValidationError(_(
                    'Only products with a standard manufacturing BoM can be added to a batch.'
                ))

    def action_view_components(self):
        self.ensure_one()
        if not self.production_id:
            self._sync_productions()
        if not self.production_id:
            raise UserError(_('Save the line before opening its components.'))
        action = self.env['ir.actions.actions']._for_xml_id(
            'mrp.action_mrp_production_form'
        )
        action.update({
            'name': self.production_id.display_name,
            'view_mode': 'form',
            'res_id': self.production_id.id,
            'target': 'new',
            'context': {'create': False},
        })
        return action
