# Data Dictionary — Retail Sales Data Engineering Pipeline

## Source Dataset

**Name:** Online Retail II  
**Provider:** UCI Machine Learning Repository via Kaggle  
**Period:** December 2009 to December 2011  
**Geography:** UK-based online retailer, international customers  
**Granularity:** One row = one transaction line (one product in one invoice)

---

## Column Definitions

### invoice
- **Type:** VARCHAR
- **Nullable:** No (rejected if missing)
- **Source header(s):** `Invoice`, `InvoiceNo`
- **Description:** Invoice/transaction identifier. A single invoice (order) contains multiple rows, one per product.
- **Business rule:** Invoice numbers starting with **'C'** indicate a **cancellation** (not a new order). These are kept in the dataset with `is_cancellation = True`.
- **Example values:** `536365`, `C536379`

### stockcode
- **Type:** VARCHAR
- **Nullable:** No (rejected if missing)
- **Source header(s):** `StockCode`
- **Description:** Product/item identifier. Not always numeric.
- **Example values:** `85123A`, `71053`, `POST`, `DOT`
- **Note:** Non-product codes like `POST` (postage), `BANK CHARGES` exist in the data.

### description
- **Type:** TEXT
- **Nullable:** Yes (kept but logged)
- **Source header(s):** `Description`
- **Description:** Free-text product name. About 2-3% of rows have missing descriptions.
- **Example values:** `WHITE HANGING HEART T-LIGHT HOLDER`, `CREAM CUPID HEARTS COAT HANGER`

### quantity
- **Type:** INTEGER
- **Nullable:** No (rejected if missing or non-numeric)
- **Source header(s):** `Quantity`
- **Description:** Number of units sold. **Negative values are allowed** — they represent returns or credit notes.
- **Business rule:** `quantity < 0` on a non-cancellation invoice → return/credit note (kept, not rejected).
- **Example values:** `6`, `-1`, `80`, `-24`

### invoicedate
- **Type:** TIMESTAMP
- **Nullable:** No (rejected if missing or invalid)
- **Source header(s):** `InvoiceDate`
- **Description:** Date and time of the transaction.
- **Example values:** `2010-12-01 08:26:00`, `2011-11-14 13:05:00`

### price
- **Type:** FLOAT / NUMERIC(10,4)
- **Nullable:** No (rejected if missing or non-numeric)
- **Source header(s):** `Price`, `UnitPrice`
- **Description:** Unit price in GBP (£).
- **Business rule:** `price < 0` is **rejected**. `price = 0` is **kept** (free items, samples).
- **Example values:** `2.55`, `3.75`, `0.0`, `12.75`

### customerid
- **Type:** FLOAT / NUMERIC(10,0)
- **Nullable:** Yes (kept but flagged)
- **Source header(s):** `Customer ID`, `CustomerID`
- **Description:** Unique customer identifier. Approximately 25% of rows have no customer ID (guest transactions).
- **Example values:** `17850.0`, `13047.0`, `NaN`

### country
- **Type:** VARCHAR
- **Nullable:** Yes (kept but logged)
- **Source header(s):** `Country`
- **Description:** Country from which the customer ordered.
- **Example values:** `United Kingdom`, `Germany`, `France`, `Australia`

---

## Derived Columns (added by pipeline)

### line_amount
- **Type:** FLOAT / NUMERIC(12,4)
- **Formula:** `quantity × price`
- **Description:** Revenue or cost of one transaction line.
- **Interpretation:**
  - Positive → sale revenue
  - Negative → return credit (customer gets money back)
  - For cancellations: reflects the value of the cancelled order
- **Example:** `quantity=6, price=2.55 → line_amount=15.30`

### is_cancellation
- **Type:** BOOLEAN
- **Formula:** `invoice.startswith('C')`
- **Description:** True if this invoice is a cancellation. Does NOT mean a simple return.
- **Business rule:** Cancellations are excluded from net sales calculations.

---

## Validation Rules Summary

| Condition | Action | Rejection Reason |
|---|---|---|
| `invoice` is NULL or blank | Reject | `null_invoice` |
| `stockcode` is NULL or blank | Reject | `null_stockcode` |
| `quantity` is NULL | Reject | `null_quantity` |
| `price` is NULL | Reject | `null_price` |
| `invoicedate` is NULL | Reject | `null_invoicedate` |
| `quantity` is non-numeric text | Reject | `non_numeric_quantity` |
| `price` is non-numeric text | Reject | `non_numeric_price` |
| `invoicedate` cannot be parsed | Reject | `invalid_date` |
| `price < 0` | Reject | `negative_price` |
| Exact duplicate row | Reject (2nd+) | `duplicate` |
| `customerid` is NULL | Keep, flag | — |
| `description` is NULL | Keep, flag | — |
| `quantity < 0` (not cancelled) | Keep as return | — |
| Invoice starts with 'C' | Keep, `is_cancellation=True` | — |

---

## Reconciliation Invariant

```
input_rows = clean_rows + rejected_rows
```

Where `rejected_rows` includes duplicate rows. This invariant must hold after every pipeline run.

---

## Analytics Metrics

| Metric | Formula |
|---|---|
| Gross Revenue | `SUM(line_amount) WHERE transaction_type = 'sale'` |
| Return Amount | `ABS(SUM(line_amount)) WHERE transaction_type = 'return'` |
| Net Revenue | Gross Revenue + Return Amount (returns are negative) |
| Average Order Value (AOV) | `Net Revenue / COUNT(DISTINCT invoice)` |
| Return Rate | `COUNT(return rows) / COUNT(all rows) * 100` |
