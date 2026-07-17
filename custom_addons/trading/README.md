# Trading Module - Official Documentation

| | |
|--- | --- |
| **Module** | Trading (Odoo Custom Addon) |
| **Version** | 1.0.0 |
| **Depends on** | base, stock, sale, purchase |
| **Audience** | Business Stakeholders and technical/engineering staff |
| **Status** | Functional, in active use |

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Business Problem & Solution](#2-business-problem--solution)
3. [System Architecture](#3-system-architecture)
4. [Functional Overview](#4-functional-overview)
5. [Data Model Reference](#5-data-model-reference)
6. [P&L Calculation Methodology](#6-pl-calculation-methodology)
7. [Multi-currency Handling](#7-multi-currency-handling)
8. [Futures Contract](#8-futures-contract)
9. [Stock & Inventory Integration](#9-stock-inventory-integration)
10. [User Interface Reference](#10-user-interface-reference)
11. [Installation & Configuration](#11-installation-configuration)

## 1. Executive Summary

The trading module extends Odoo to support commodity trading operations - buying, holding, and selling a position over time, tracking profit and loss as that position moves, and doing so across multiple currencies.

Odoo, out of the box, treats a purchase and a sale as two separate, unrelated documents. For a trading business, that's not sufficient: a single purchase is often sold off in pieces, at different currencies, and the business needs to see all of that as **one trade** with one running profit and loss figure - not as disconnected purchase and sales records that have to be manually reconciled.

This module solves that by introducing a central **Trade** record that Purchase Orders and Sale orders feed into automatically. When a Purchase Order is confirmed, a trade is either created or updated. When a Sale Order is confirmed against that same product, it links to the trade and the trade's position and P&L update immediately - no manual data entry, no separate spreadsheet.

**In plain terms:** a trader or operations user works entirely within Odoo's normal purchase and sale screens; the Trading module observes those actions and keeps a live trading ledger in the background.

## 2. Business Problem & Solution 

| Problem | How this module addresses it |
| --- | --- |
|Purchase and sales aren't linked, so position and P&L must be tracked manually (spreadsheets, outside Odoo).|A trade record is created/updated automatically from confirmed Purchase Orders and Sale Orders.|
| A single purchase is often sold in multiple pieces over time. | The trade tracks cumulative sold quantity against the original purchase quantity, computing an **open position** at all times. |
| Purchases and sales may happen in different currencies. | All monetary figures are converted to a single reporting currency, using the exchange rate **on the actual transaction date** - not today's rate applied retroactively. |
| Knowing paper profit on a position that hasn't fully sold yet. | A market price can be entered on the trade at any time, producing a live **unrealized P&L** on the open portion. |
|Additional invoices/bills (freight, storage, etc.) affect true profitability but aren't part of the original PO/SO value. | Invoices and bills linked to a trade (directly or via their originating order) are automatically folded in to **additional cost/revenue**. |

## 3. System Architecture

```
 Purchase Order            Sale Order
 (button_confirm)          (action_confirm)
        │                        │
        ▼                        ▼
        └──────────► trading.trade ◄──────────┐
                          │                    │
                          ▼                    │
                  trading.futures    (optional contract tracking)
                          │
                          ▼
                  account.move (invoices / bills)
              linked via trade_id, contributing to
              additional_costs / additional_revenue
                          │
                          ▼
                  stock.picking (goods receipt)
           links received lots → trade.lot_ids,
           driving on_hand_quantity independently
              of the commercial open position
```

**Design Principle:** the trade is never data-entered directly by a user in normal operation. It is derived from, and kept in sync with, the standard Odoo documents (POs, SOs, invoices, stock moves) that staff use already.

## 4. Functional Overview

### 4.1 Opening a position (Long Trade)

1. A purchase Order is confirmed for a tracked product.
2. A trade record is created automatically; trade type **Long**, quantity/price/currency taken from the PO.
3. If the PO's goods receipt includes lots, those lots are linked to the trade, enabling physical on-hand tracking.

### 4.2 Selling down a position
 
1. A Sale Order is confirmed against the same product.
2. If a matching open trade exists, the SO links to it; otherwise a new **Short** trade is created.
3. The trade's sold quantity, open position, and realized P&L update immediately.
4. Once purchase and sale quantities fully match, the trade **closes itself** — no manual status change required.
### 4.3 Marking a position to market
 
At any point, a user can enter a **Current/Market Price** on an open trade. This produces an **unrealized P&L** on the still-open quantity, so the business can see paper profit/loss on inventory that hasn't sold yet.
 
### 4.4 Additional costs and revenue
 
Invoices/bills that reference the same PO/SO (or are linked to the trade directly) contribute to the trade's `additional_costs` or `additional_revenue`. If such an invoice is later reset to draft or unlinked from the trade, that contribution is automatically reversed so figures don't remain artificially inflated.
 
## 5. Data Model Reference
 
| Model | Responsibility |
|---|---|
| `trading.trade` | Central trade record — identity, workflow status (Draft → Confirmed → Closed), and the fields described below. |
| `trading.futures` | A contract nested under a trade — contract price/quantity, delivery balance, its own realized/unrealized P&L. |
| `trading.future.delivery.line` | Individual delivery entries against a futures contract. |
| `sale.order` *(extended)* | Adds `trade_id`; auto-creates/links a trade on confirmation. |
| `purchase.order` *(extended)* | Adds `trade_id`; auto-creates/links a trade on confirmation, including lot linking. |
| `account.move` *(extended)* | Adds `trade_id`; links invoices/bills to trades and manages the additional cost/revenue lifecycle, including reversal on draft-reset or unlink. |
| `account.move.line` *(extended)* | Adds line-level `trade_id` for invoices with no PO/SO origin. |
| `stock.picking` *(extended)* | Links received lots to a trade on validated incoming receipts. |
 
### 5.1 Key fields on `trading.trade`
 
| Field | Meaning |
|---|---|
| `trade_type` | Long or Short. |
| `status` | Draft, Confirmed, or Closed. Closed is set automatically once fully matched. |
| `quantity` / `price` | Purchase-side quantity and price, in `purchase_currency_id`. |
| `sales_price` | Derived average sale price. In the sale orders' original currency if they share one currency; converted to the reporting currency if they don't (see [§7](#7-multi-currency-handling)). |
| `current_price` | Manually entered market price, used for unrealized P&L. |
| `open_position_quantity` | `quantity − total_sold_quantity`. Positive = long exposure, negative = short exposure. |
| `open_position_cost_basis` | Cost basis of just the **open** quantity — distinct from `total_purchase_cost`, which is the full original position's cost. |
| `on_hand_quantity` | Physical stock on hand, from linked lots — tracked independently of the commercial position (see [§9](#9-stock--inventory-integration)). |
| `realized_pnl` / `unrealized_pnl` / `total_pnl` | See [§6](#6-pl-calculation-methodology). |
| `additional_costs` / `additional_revenue` | Manually or invoice-driven adjustments not captured by the original PO/SO value. |
| `is_fully_matched` | True once both a purchase and a sale exist with equal quantities — triggers auto-close. |
 
## 6. P&L Calculation Methodology
 
**Average cost per unit** (reporting currency):
```
avg_cost_per_unit = (quantity × price_in_base_currency + additional_costs) / quantity
```
 
**Realized P&L** — profit/loss on the matched portion only:
```
matched_qty   = min(quantity, total_sold_quantity)
realized_pnl  = total_sales_value − (matched_qty × avg_cost_per_unit)
```
 
**Unrealized P&L** — profit/loss on the still-open portion, only once a market price is set:
 
| Position | Formula |
|---|---|
| Long, market price set | `open_qty × (current_price − avg_cost_per_unit)` |
| Short, market price set | `open_qty × (sale_price − current_price)` |
| Long, no market price set yet | Full cost exposure shown as unrealized loss — a deliberate conservative placeholder meaning "not yet priced," not an error. See [§12](#12-known-limitations--risks). |
| Short, no market price set yet | Shown as zero (cost to cover is unknown). |
 
**Total P&L**:
```
total_pnl = realized_pnl + unrealized_pnl + additional_revenue
```
 
**Auto-close**: once `is_fully_matched` is true, the trade's status is set to Closed automatically, without user action.
 
## 7. Multi-Currency Handling
 
All conversions use the exchange rate **as of the transaction's own date**, not the date the record happens to be viewed — this keeps historical trades accurate regardless of when someone looks at them later.
 
- If a trade's confirmed sale orders **all share one currency**, `sales_price` is the quantity-weighted average in that original currency.
- If confirmed sale orders **span multiple currencies**, no single "original currency" figure would be meaningful, so `sales_price` instead shows the quantity-weighted average **converted to the reporting currency**, each order converted at its own transaction date.
- `average_sale_price` (shown in the trade summary) is always expressed in the reporting currency and is the figure to trust for a blended view across multiple sales.
## 8. Futures Contracts
 
A `trading.futures` record tracks a forward/futures contract nested under a parent trade, independent of the trade's own purchase/sale bookkeeping:
 
- **Contract terms**: `contract_price`, `contract_quantity`.
- **Delivery tracking**: `closed_balance` (delivered, via confirmed sale orders) vs. `open_balance` (still undelivered).
- **P&L**: realized P&L compares actual sales value against contract value on the delivered portion; unrealized P&L applies the parent trade's long/short direction to the undelivered portion against the current market price.
- Contracts under the same trade are auto-named uniquely (e.g. `TRD/LONG/00008 - Cocoa Future - 2026-07-14 - #2`) to stay distinguishable.
## 9. Stock & Inventory Integration
 
Two quantities are tracked **independently** and can legitimately disagree:
 
- **`open_position_quantity`** — the *commercial* position, derived from purchase and sale order quantities.
- **`on_hand_quantity`** — the *physical* inventory, derived from stock lots linked to the trade.
A trade can show an open commercial position with zero on-hand quantity if, for example, a sale was confirmed but the corresponding goods receipt hasn't been validated (and lots linked) yet. **This is intentional design, not a synchronization bug** — but it should be explained to anyone comparing the two figures side by side, as the difference is not self-evident from the UI alone.
 
## 10. User Interface Reference
 
**Trade form view** is organized into:
- **Trade Details** — type, linked lots.
- **Trade Metrics & Financials** — product, quantity, on-hand quantity.
- **Pricing Details** — purchase price, sales price, market price.
- **Invoicing & Cost Details** — additional costs/revenue (manually editable inputs, kept separate from computed output).
- **Trade Summary tab**, with three cards:
  - *Open Positions* — open quantity, cost basis of the open portion, unrealized P&L, market price.
  - *Closed Positions* — sold quantity, sales value, realized P&L, cost basis of the sold portion.
  - *Summary* — total P&L, P&L %, average sale price, fully-matched indicator.
**Reporting views**: List, Kanban, Pivot, and Graph, with filters for trade type, status, profitability, and fully-matched state, accessible under the Trading Reporting menu.
 
## 11. Installation & Configuration
 
1. Place the module in the addons path (e.g. `custom_addons/trading`).
2. Update the Apps list in Odoo, then install (or upgrade, if already present) **Trading**.
3. Review `security/ir.model.access.csv` before granting access beyond administrators — this defines which user groups can read/write trades.
4. No additional configuration is required; the module activates automatically for any product used on a Purchase or Sale Order once installed.
## 12. Known Limitations & Risks
 
| Item | Detail |
|---|---|
| **Win rate is per-trade, not aggregate** | `win_rate` currently shows 100 or 0 for a single trade based on whether its own realized P&L is positive — it is not yet an aggregate win rate across all trades. |
| **No automated test coverage** | The P&L engine has no automated tests yet. This is the highest-priority gap before relying on this module at higher trade volume. |
| **Not load-tested** | Saving a trade recomputes roughly nine dependent fields on any relevant change. Behavior at high trade volume or write frequency has not been benchmarked. |
| **Partial reversal gap on direct vendor bills** | A vendor bill not linked to a Purchase Order, if it includes a line matching the trade's own product, is treated as an additional purchase (adjusting quantity and the weighted-average cost). If that bill is later reset to draft, only the non-product-line cost portion is reversed — the quantity/price adjustment currently is not. This is a narrow scenario but not yet fully handled. |
| **Verbose debug logging** | Several files log at warning level for ordinary, expected flow rather than actual problems — this should be reduced before treating log output as a signal of real issues. |
 
## 13. Recommended Next Steps
 
1. Add automated tests around the P&L engine (highest priority — see §12).
2. Build a true aggregate win-rate / performance report across trades, replacing the current per-trade binary field.
3. Close the direct-bill reversal gap described in §12.
4. Load-test trade creation/update at realistic volume before scaling usage.
5. Reduce logging verbosity to warning-level-appropriate messages only.
## 14. Version History
 
**Unreleased — P&L correctness and UI fixes**
- Fixed a missing import that prevented the module from loading after certain changes.
- Introduced a shared, correct reversal mechanism so that resetting an invoice to draft, or unlinking it from a trade, properly reverses its contribution to `additional_costs`/`additional_revenue` — closing three related bugs that previously allowed costs/revenue to be double-counted or left stale.
- Corrected the Open Positions card to show cost basis scoped to the open quantity rather than the full original position.
- Corrected `sales_price` to show a properly converted average instead of freezing on a stale value when sale orders span multiple currencies.
- Separated editable "Invoicing & Cost Details" fields from computed summary output in the UI, and clarified the relationship between Sales Price and Avg Sale Price with an explanatory tooltip.
> **Data note:** any trade that went through a draft-reset or unlink cycle *before* the fixes above may still hold incorrect `additional_costs`/`additional_revenue` values inherited from the earlier bugs. These will not self-correct automatically and should be reviewed manually.
 
**1.0.0 — Initial functional version**
- Core trade lifecycle (create from PO/SO, position tracking, P&L, auto-close).
- Multi-currency conversion framework.
- Futures contract tracking.
- Stock lot linkage.
## 15. Glossary
 
| Term | Definition |
|---|---|
| **Long trade** | A position opened by buying first; the business holds inventory awaiting sale. |
| **Short trade** | A position opened by selling first, without (yet) an existing purchase. |
| **Open position** | The quantity purchased but not yet sold (or vice versa for short trades). |
| **Realized P&L** | Profit/loss on the portion of a trade that has been both bought and sold. |
| **Unrealized P&L** | Paper profit/loss on the still-open portion, based on a manually entered market price. |
| **Reporting currency** | The single currency all of a trade's figures are converted into for consistent comparison. |
| **Fully matched** | A trade where purchased and sold quantities are equal — triggers automatic closure. |
| **Additional costs / revenue** | Amounts from invoices/bills not captured in the original PO/SO value (e.g. freight, storage, adjustments). |

