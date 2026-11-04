"""Regression coverage for the user's actual export *structures* (synthetic amounts only)."""
from datetime import date
import pytest
import base64
from backend.core import daily_reporting, general_ledger, financial, inspect_uploads, DEFAULT_CONFIG, ValidationError
from openpyxl import Workbook
import io

def xlsx(rows, sheets=None):
    w = Workbook()
    ws = w.active
    ws.title = "Report"
    for row in rows:
        ws.append(row)
    for name, content in (sheets or {}).items():
        ws = w.create_sheet(name)
        for row in content:
            ws.append(row)
    stream = io.BytesIO()
    w.save(stream)
    return stream.getvalue()


def test_drs_real_sheet_names_and_labeled_rows():
    dates = [date(2026, 8, d) for d in range(1, 32)]
    rows = [
        ["Metric"] + ["Value"] * 31,
        ["Date"] + dates,
        ["Order range"] + ["#1-#2"] * 31,
        ["Number of orders"] + [2] * 31,
        ["Gross sales (A$)"] + [500] * 31,
        ["Discounts (A$)"] + [-80] * 31,
        ["Returns"] + [-15] * 31,
        ["Net sales"] + [405] * 31,
        ["Shipping charges collected (A$)"] + [10] * 31,
        ["Rounding"] + [0] * 31,
        ["Total sales (A$)"] + [415] * 31,
        [],
        ["Product revenue"] + [400] * 31,
        ["Shipping revenue"] + [15] * 31,
        ["Other shipping"] + [0] * 31,
        ["Refund"] + [20] * 31,
    ]
    product = [[], [], ["1-Nov-2025", "Frames", 100, 0, -5, 95, 100, 100],
               [None, "Total", 100, 0, -5, 95, 100, 100]]
    country = [[], [], ["", "Country", "Revenue (ex GST)", "Percentage"],
               [None, "Australia", 95, 100], [None, "Total", 95, 100]]
    raw = xlsx([], {"Daily Reporting": rows, "Productwise Sales": product, "Countrywise Sales": country})
    parsed = daily_reporting(raw, "2026-08", DEFAULT_CONFIG)
    assert parsed["totals"]["orders"] == "62"
    assert parsed["totals"]["sales"] == "12865"
    assert parsed["totals"]["refunds"] == "620"
    assert parsed["products"]["total"][0] == "Total"
    assert len(parsed["daily"]) == 31


def test_xero_grouped_gl_debit_credit_and_period():
    rows = [
        ["General Ledger Detail"], ["Saint Eyewear Pty Ltd"],
        ["For the period 1 August 2026 to 31 August 2026"], [],
        ["Date", "Source", "Description", "Reference", "Debit", "Credit", "Running Balance"],
        [], ["Software Expense"],
        [date(2026, 8, 3), "Payable Invoice", "Redo Tech", "R-15", 125, 0, 125],
        [date(2026, 8, 5), "Spend Money", "Other vendor", "R-16", 0, 20, 105],
    ]
    result = general_ledger(xlsx(rows), "2026-08")
    assert result["count"] == 2
    assert result["transactions"][0]["account"] == "Software Expense"
    assert result["transactions"][0]["vendor"] == "Redo Tech"
    assert result["transactions"][1]["amount"] == "-20"


def test_xero_gl_rejects_half_month():
    rows = [["General Ledger Detail"], ["Saint Eyewear Pty Ltd"],
            ["For the period 1 October 2026 to 15 October 2026"], [],
            ["Date", "Source", "Description", "Reference", "Debit", "Credit"],
            [], ["Software Expense"], [date(2026, 10, 3), "Spend Money", "Vendor", "1", 10, 0]]
    with pytest.raises(ValidationError, match="complete"):
        general_ledger(xlsx(rows), "2026-10")


def test_balance_sheet_real_spaced_columns_and_month_end():
    rows = [["Balance Sheet"], ["Saint Eyewear Pty Ltd"], ["As at 31 August 2026"], [],
            [None, "Account", "31 Aug 2026", None, "31 July 2026", None, "30 June 2026"],
            [], ["Assets"], [None, "Bank"],
            [None, "Savings", 300, None, 200, None, 100],
            [None, "Net Assets", 300, None, 200, None, 100],
            ["Total Equity", None, 300, None, 200, None, 100],
            [None, "Current Year Earnings", 100, None, 50, None, 25]]
    result = financial(xlsx(rows), "Balance Sheet", "2026-08")
    assert result["months"]["2026-08"]["Net Assets"] == "300"
    assert result["months"]["2026-07"]["Savings"] == "200"


def test_balance_sheet_rejects_interim_dates():
    rows = [["Balance Sheet"], ["Saint Eyewear Pty Ltd"], ["As at 15 October 2026"], [],
            [None, "Account", "15 Oct 2026", None, "30 Sept 2026", None, "31 Aug 2026"],
            [], [None, "Cash", 1, None, 2, None, 3]]
    with pytest.raises(ValidationError, match="month-end"):
        financial(xlsx(rows), "Balance Sheet", "2026-10")

def test_auto_identifies_four_files_independent_of_filename_or_upload_order():
    dates = [date(2026, 8, d) for d in range(1, 32)]
    daily = [["Date"] + dates, [], [],
             ["Orders"] + [1]*31, [], [],
             ["Sales"] + [100]*31, [],
             ["Refunds"] + [0]*31]
    drs = xlsx([], {"Daily Reporting": daily,
                    "Productwise Sales": [[], [], [None, "Frame", 100], [None, "Total", 100]],
                    "Countrywise Sales": [[], [], [], [None, "Australia", 100], [None, "Total", 100]]})
    pnl = xlsx([["Profit and Loss"], ["Saint Eyewear Pty Ltd"], [],
                ["Account", "Aug 2026", "July 2026", "June 2026"]])
    bs = xlsx([["Balance Sheet"], ["Saint Eyewear Pty Ltd"], [],
               ["Account", "31 Aug 2026", "31 July 2026", "30 June 2026"]])
    gl = xlsx([["General Ledger Detail"], ["Saint Eyewear Pty Ltd"],
               ["For the period 1 August 2026 to 31 August 2026"]])
    uploaded = {"gl":drs, "drs":bs, "bs":pnl, "pnl":gl}
    result = inspect_uploads({"files":{k:base64.b64encode(v).decode() for k,v in uploaded.items()}})
    assert result["month"] == "2026-08"
    assert result["source_map"] == {"drs":"gl", "bs":"drs", "pnl":"bs", "gl":"pnl"}


def test_drs_ignores_non_reporting_working_sheets():
    dates = [date(2026, 8, d) for d in range(1, 32)]
    daily = [["Metric"]+["Value"]*31, ["Date"]+dates,
             ["Order range"]+["#1"]*31, ["Number of orders"]+[1]*31,
             ["Gross sales"]+[100]*31, [], [], [], [], [],
             ["Total sales (A$)"]+[100]*31, [], [], [], [], ["Refund"]+[0]*31]
    p = [[], [], [None, "Frames", 100], [None, "Total Sales", 100]]
    c = [[], [], [], [None, "Australia", 100], [None, "Total", 100]]
    # A deliberately invalid unneeded tab (more than 1000 columns) must not
    # prevent parsing the three report tabs needed for calculations.
    raw = xlsx([], {"Daily Reporting":daily,"Productwise Sales":p,
                    "Countrywise Sales":c,"August Breakdown Sheet":[[None]*1001+["irrelevant"]]})
    result = daily_reporting(raw, "2026-08", DEFAULT_CONFIG)
    assert result["totals"]["orders"] == "31"
