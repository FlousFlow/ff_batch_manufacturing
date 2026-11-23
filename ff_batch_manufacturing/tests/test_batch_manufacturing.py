from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import TransactionCase


class TestBatchManufacturing(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.picking_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'mrp_operation'), ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.source = cls.picking_type.default_location_src_id
        cls.destination = cls.picking_type.default_location_dest_id
        cls.finished, cls.component = cls.env['product.product'].create([
            {'name': 'FF Batch Finished', 'type': 'consu', 'is_storable': True},
            {'name': 'FF Batch Component', 'type': 'consu', 'is_storable': True},
        ])
        cls.component_bom = cls.env['mrp.bom'].create({
            'product_id': cls.component.id,
            'product_tmpl_id': cls.component.product_tmpl_id.id,
            'product_qty': 1.0,
            'uom_id': cls.component.uom_id.id,
        })
        cls.finished_bom = cls.env['mrp.bom'].create({
            'product_id': cls.finished.id,
            'product_tmpl_id': cls.finished.product_tmpl_id.id,
            'product_qty': 1.0,
            'uom_id': cls.finished.uom_id.id,
            'bom_line_ids': [Command.create({
                'product_id': cls.component.id,
                'product_qty': 2.0,
            })],
        })

    def _batch(self, lines=1):
        batch = self.env['ff.batch.manufacturing'].create({
            'picking_type_id': self.picking_type.id,
            'location_src_id': self.source.id,
            'location_dest_id': self.destination.id,
            'line_ids': [Command.create({
                'product_id': self.finished.id,
                'product_qty': 1.0,
                'uom_id': self.finished.uom_id.id,
            }) for _index in range(lines)],
        })
        return batch

    def test_saved_line_creates_one_draft_mo(self):
        batch = self._batch()
        self.assertEqual(len(batch.line_ids), 1)
        self.assertEqual(len(batch.production_ids), 1)
        self.assertEqual(batch.production_ids.state, 'draft')
        self.assertEqual(batch.production_ids.product_id, self.finished)

    def test_repeated_products_remain_independent(self):
        batch = self._batch(lines=2)
        self.assertEqual(len(batch.production_ids), 2)
        self.assertEqual(len(set(batch.production_ids.ids)), 2)

    def test_view_components_returns_native_production_form_action(self):
        batch = self._batch()
        action = batch.line_ids.action_view_components()
        self.assertEqual(action['res_id'], batch.line_ids.production_id.id)
        self.assertEqual(action['view_mode'], 'form')
        self.assertEqual(action['target'], 'new')
        self.assertFalse(action['context']['create'])

    def test_quantity_scales_current_component_moves(self):
        batch = self._batch()
        line = batch.line_ids
        move = line.production_id.move_raw_ids.filtered(lambda item: item.product_id == self.component)
        self.assertEqual(move.product_qty, 2.0)
        line.product_qty = 3.0
        self.assertEqual(move.product_qty, 6.0)

    def test_master_bom_is_not_modified(self):
        original_qty = self.finished_bom.bom_line_ids.product_qty
        batch = self._batch()
        line = batch.line_ids
        line.production_id.move_raw_ids.filtered(lambda item: item.product_id == self.component).product_uom_qty = 9.0
        self.assertEqual(self.finished_bom.bom_line_ids.product_qty, original_qty)

    def test_header_locations_propagate_to_lines(self):
        batch = self._batch()
        line = batch.line_ids
        batch.write({
            'location_src_id': self.destination.id,
            'location_dest_id': self.source.id,
        })
        self.assertEqual(line.location_src_id, self.destination)
        self.assertEqual(line.location_dest_id, self.source)

    def test_line_locations_default_from_batch_header(self):
        batch = self._batch()
        line = batch.line_ids
        self.assertEqual(line.location_src_id, self.source)
        self.assertEqual(line.location_dest_id, self.destination)

    def test_empty_batch_is_rejected(self):
        batch = self.env['ff.batch.manufacturing'].create({
            'picking_type_id': self.picking_type.id,
            'location_src_id': self.source.id,
            'location_dest_id': self.destination.id,
        })
        with self.assertRaises(UserError):
            batch.action_confirm_manufacture()

    def test_product_without_standard_bom_is_rejected(self):
        product = self.env['product.product'].create({
            'name': 'FF Batch Product Without BoM', 'type': 'consu', 'is_storable': True,
        })
        batch = self.env['ff.batch.manufacturing'].create({
            'picking_type_id': self.picking_type.id,
            'location_src_id': self.source.id,
            'location_dest_id': self.destination.id,
        })
        with self.assertRaises(ValidationError):
            self.env['ff.batch.manufacturing.line'].create({
                'batch_id': batch.id,
                'product_id': product.id,
                'product_qty': 1.0,
                'uom_id': product.uom_id.id,
            })

    def test_confirm_manufacture_completes_native_mo(self):
        self.env['stock.quant']._update_available_quantity(self.component, self.source, 2.0)
        batch = self._batch()
        batch.action_confirm_manufacture()
        self.assertEqual(batch.state, 'done')
        self.assertEqual(batch.production_ids.state, 'done')
        self.assertEqual(batch.production_ids.product_qty, 1.0)
