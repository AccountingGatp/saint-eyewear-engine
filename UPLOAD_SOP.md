# Saint Eyewear — Monthly Upload SOP

For GATP staff. **One reporting month per run.** Select the month in the application first, then upload the following four **.xlsx** files. Keep original exported account names and workbook tabs. The application is currently an internal-review tool; generated Word files are drafts until historical issued-pack acceptance tests pass.

| Upload box | Source | Exact requirements |
|---|---|---|
| Profit and Loss | Xero → Profit and Loss → Export to Excel | First data column is the selected **full** calendar month; next two columns are the prior two **full** calendar months; include **Year to date** for the financial year starting 1 July. Export all account and total rows. |
| Balance Sheet | Xero → Balance Sheet → Monthly comparison → Excel | Selected month-end and preceding two month-end dates (not 15th/interim), with all account rows and Total Equity / Net Assets / Current Year Earnings. |
| General Ledger | Xero → General Ledger Detail → Excel | All transactions from the **1st through last day** of selected month. Keep Date, Description, Reference, Debit and Credit. Xero account-heading sections are supported; no repeated Account column is required. |
| Daily Reporting Sheet (DRS) | Client Google Sheet → File → Download → Microsoft Excel (.xlsx) | Keep entire workbook. **Daily Reporting** tab: dates for every day and rows labeled Number of orders, Total sales (A$), Refund. **Productwise Sales** tab and **Countrywise Sales** tab with their final Total rows. Legacy tab names Productwise/Countrywise are also supported. |

## Before you click Upload and validate

1. Ensure the four workbooks refer to **Saint Eyewear Pty Ltd** and the same month.
2. **Do not upload partial or split-half-month Xero reports.** An October 1–15 export is not a full October report.
3. Compare the P&L and GL **export dates**. Per the accounting SOP, they must be exported on the same day. If the exported files have no dates in their headers, the application cannot independently confirm this and must block final processing rather than inventing dates.
4. Recheck zero totals on Xero exports. If Total Trading Income, Gross Profit, Net Profit, Total Assets or Total Equity appears as zero while related accounts contain amounts, fix/re-export and do **not** replace the totals by hand.
5. Make sure cached Excel formulas recalculate and there are no errors in required data. Keep all dates, including zero-sales days.
6. File sizes: maximum **5 MB per workbook**, **12 MB combined**.

## After upload

The app validates input format, account group mappings, month and financial-year arithmetic. Xero P&L is the financial source of truth; GL is solely for transaction/vendor analysis; DRS is solely for daily, product and country details. Resolve all Block exceptions. A reviewer must explain each Review exception and sign off. Document downloads remain internal **DRAFT** until the approved August and September report packs have been reproduced and compared to the issued versions.

**If a file fails:** Read the specific error, correct the exported file or provide the necessary support, and try again. Do not conceal missing dates, substitute zero for unknown values, or force a wrong-period report through validation.

See the original Build SOP for the full 14-rule accounting specification and production acceptance conditions.
