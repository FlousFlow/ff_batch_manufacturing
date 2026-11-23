# Flous Flow Batch Manufacturing

## Overview

This Odoo 20 Community addon provides one standard batch sheet for planning
multiple different manufacturing products. Each line remains a separate native
`mrp.production` record, so components, quantities, locations, reservations,
traceability, valuation and accounting continue to use Odoo's Manufacturing and
Inventory engines.

The package includes the supplied Flous Flow/Odoo 20 cover artwork in
`static/description/banner.jpg` for the Apps description page.

## Workflow

1. Open **Manufacturing → Operations → Batch Manufacturing**.
2. Create a batch and choose the operation type, component source location and
   finished-product destination location.
3. Add one line per finished product and enter its manufacturing quantity.
4. Save the line. The module creates one draft Manufacturing Order for that
   line, using the product's normal BoM.
5. Use **View Components** on a line to review or customize only that line's
   draft Manufacturing Order. The master BoM is never edited.
6. Use **Confirm & Manufacture** for simple eligible one-step MOs. The module
   delegates confirmation, reservations, stock moves, valuation and completion
   to native Odoo methods.

## Important behavior

- Repeated products on two lines create two independent Manufacturing Orders.
- Components edited from **View Components** are consumed for that MO only; the
  source BoM remains unchanged.
- Changing a line quantity scales its current component moves, including manual
  additions, removals and replacements, without reloading the master BoM.
- Header source and destination locations populate every line automatically.
- Availability uses Odoo's native quantity-at-date indicator.
- Work Orders, serial/lot wizards, multi-step pickings and other mandatory
  native workflows are not bypassed; unsupported one-click cases return an
  actionable Odoo error and remain incomplete rather than being falsely marked
  Done.
- Reset is restricted to Manufacturing Managers and returns linked MOs to Draft
  without creating an Unbuild. It does not reverse posted stock valuation.

## Requirements

- Odoo 20 Community.
- Odoo Manufacturing (`mrp`).
- Normal manufacturing BoMs for products intended for internal production.

No cron, external service, custom accounting ledger or custom stock engine is
added. Standard Odoo Manufacturing permissions and company rules apply.

## Testing

The test suite covers line persistence and draft-MO creation, repeated products,
component scaling, master-BoM protection, header-location propagation,
empty-batch validation and native one-step completion. Run it on a disposable Odoo 20
database with:

```bash
odoo-bin -d test_db -u ff_batch_manufacturing \
  --test-enable --test-tags ff_batch_manufacturing --stop-after-init
```

Production load, advanced work orders, serial/lot completion, backorders,
multi-company access and accounting valuation should be validated in the target
deployment before release.
