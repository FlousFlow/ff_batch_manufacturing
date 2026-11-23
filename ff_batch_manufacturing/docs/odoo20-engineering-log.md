# Odoo 20 Engineering Log

## 2026-11-23 — Initial implementation

- Inspected the checked-out Odoo 20 source for `mrp.production`, stock moves,
  availability fields, native confirmation/completion and reset methods.
- Implemented a batch header and independent batch lines. Saved lines create one
  native draft `mrp.production` each; repeated products remain independent.
- Component customization is held on the production's stock moves and never
  writes the master BoM. Quantity changes scale the current moves.
- Added header location defaults with independent line overrides, draft-time
  availability preview, native manufacturing action, manager-only reset guard,
  access rules using Odoo 20's `ir.access`, Arabic translations, views, sequence
  and focused tests.
- Focused local test suite: 6 tests, 0 failures, 0 errors.

## 2026-11-23 — Arabic translation coverage

- Audited Python labels, validation messages, selection values and XML view
  labels against `i18n/ar.po`; added the missing Arabic entries for the full
  batch form, line columns, summary, statuses and error messages.
- Reloaded the module with the Arabic locale on the local Odoo 20 database;
  `msgfmt --check` passed (header metadata warnings only) and the focused suite
  completed with 7 tests, 0 failures and 0 errors.

## Boundaries

- The one-click action supports simple one-step MOs. Work Orders, serial/lot
  dialogs, multi-step pickings and other mandatory native workflows are left to
  their standard Odoo screens with an actionable error rather than being marked
  complete incorrectly.
- Native Odoo `mrp:TestProcurement` expectations may differ because this module
  intentionally manages a batch of independent MOs; full production validation
  still requires the target configuration.
