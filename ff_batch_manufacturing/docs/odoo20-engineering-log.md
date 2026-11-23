# Odoo 20 Engineering Log

## 2026-11-23 — Initial implementation

- Inspected the checked-out Odoo 20 source for `mrp.production`, stock moves,
  availability fields, native confirmation/completion and reset methods.
- Implemented a batch header and independent batch lines. Saved lines create one
  native draft `mrp.production` each; repeated products remain independent.
- Component customization is held on the production's stock moves and never
  writes the master BoM. Quantity changes scale the current moves.
- Added header location defaults with automatic line propagation, draft-time
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

## 2026-11-23 — Batch form cleanup

- Removed the unused Summary notebook page.
- Kept header locations as the only source for every line, while making
  location, availability, cost and linked-MO columns `optional="hide"` so users
  can choose them through the standard Odoo list-column selector. Removed the
  unused per-line custom source/destination flags.

## Boundaries

- The one-click action supports simple one-step MOs. Work Orders, serial/lot
  dialogs, multi-step pickings and other mandatory native workflows are left to
  their standard Odoo screens with an actionable error rather than being marked
  complete incorrectly.
- Native Odoo `mrp:TestProcurement` expectations may differ because this module
  intentionally manages a batch of independent MOs; full production validation
  still requires the target configuration.
### 2026-11-23 — Reset completed batch without Unbuild

- Decision: the batch reset action now uses Odoo's native manufacturing reset and clears the picked workflow flag so linked MOs and the batch return to Draft without creating `mrp.unbuild` records.
- Evidence: Odoo 20 `mrp.production.action_reset_to_draft` and `stock.move._action_reset_to_draft` inspected in the local source.
- Test: 19 addon tests passed, 0 failed, 0 errors.
- Boundary: this is a workflow-state reset only; it does not reverse the posted stock valuation/quant changes from the completed manufacturing. Users must not use it as an inventory correction.

### 2026-11-23 — Consume edited MO components without changing the BoM

- Decision: the batch completion flow now treats raw-material quantities edited from the native linked MO form as this MO's consumed quantities, skips the native BoM-vs-consumption warning for this controlled flow, and leaves the original BoM unchanged.
- Test: added an edited-component scenario; 20 addon tests passed, 0 failed, 0 errors.
- Boundary: stock availability still follows the normal Odoo stock moves; editing the MO can intentionally consume a quantity different from the source BoM.

### 2026-11-23 — Cleanup audit

- Removed unused custom availability and component-customization fields; the form now relies on Odoo's native quantity-at-date widget.
- Removed the unused `sale` dependency and corrected documentation that still described reset as blocked after completion.
- Gave hidden widget bridge fields distinct labels to eliminate duplicate-label registry warnings.
