"""
Reading uploaded files and writing Excel / CSV downloads.

Uploads:   .xlsx (first sheet) or .csv (UTF-8, or Excel's default encoding)
Downloads: .xlsx by default, .csv on request (?format=csv)
"""

import csv
import datetime
import io

from .fields import as_text, norm_header

MAX_ROWS = 5000
MAX_BYTES = 5 * 1024 * 1024   # 5 MB


class FileError(ValueError):
    """The whole file can't be used (wrong type, too big, no header...)."""


EXCEL_MISSING = (
    "Excel support isn't installed on the server. In the backend folder, with the "
    "virtual environment active, run:  python -m pip install openpyxl  - then restart the backend."
)


# ===================== READ =====================
def read_upload(upload):
    """
    Returns (headers, rows)
      headers: list of normalised header keys, in file order
      rows:    list of (row_number, {header_key: value})
               row_number is the line number the user sees in Excel (header = 1)
    """
    if upload is None:
        raise FileError("Choose a file to upload.")
    if upload.size and upload.size > MAX_BYTES:
        raise FileError("The file is larger than 5 MB. Split it into smaller files.")

    name = (upload.name or "").lower()
    if name.endswith(".xlsx"):
        table = _read_xlsx(upload)
    elif name.endswith(".csv"):
        table = _read_csv(upload)
    elif name.endswith(".xls"):
        raise FileError("Old .xls files aren't supported. In Excel use File > Save As > Excel Workbook (.xlsx).")
    else:
        raise FileError("Upload an Excel (.xlsx) or CSV (.csv) file.")

    # first non-empty row is the header
    while table and not any(as_text(c) for c in table[0]):
        table.pop(0)
    if not table:
        raise FileError("The file is empty.")

    headers = [norm_header(h) for h in table[0]]
    rows = []
    for offset, cells in enumerate(table[1:], start=2):
        values = {}
        for i, key in enumerate(headers):
            if not key:
                continue
            values[key] = cells[i] if i < len(cells) else ""
        if not any(as_text(v) for v in values.values()):
            continue            # fully blank row - ignore silently
        rows.append((offset, values))

    if len(rows) > MAX_ROWS:
        raise FileError(f"The file has {len(rows)} rows. The limit is {MAX_ROWS} per file.")
    return headers, rows


def _read_csv(upload):
    raw = upload.read()
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise FileError("Couldn't read the file. Save it as 'CSV UTF-8' and try again.")
    return [row for row in csv.reader(io.StringIO(text))]


def _read_xlsx(upload):
    try:
        from openpyxl import load_workbook
    except ImportError:   # pragma: no cover - dependency missing on the server
        raise FileError(EXCEL_MISSING)
    try:
        wb = load_workbook(upload, read_only=True, data_only=True)
    except Exception:
        raise FileError("Couldn't open this Excel file. Make sure it's a real .xlsx file.")
    ws = wb.worksheets[0]
    table = []
    for row in ws.iter_rows(values_only=True):
        table.append([_cell(v) for v in row])
    wb.close()
    return table


def _cell(v):
    """Keep real Excel dates as dates; everything else becomes text."""
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return as_text(v)


# ===================== WRITE =====================
def write_csv(headers, rows):
    out = io.StringIO()
    out.write("\ufeff")                     # so Excel opens UTF-8 correctly
    w = csv.writer(out)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return out.getvalue().encode("utf-8")


def write_xlsx(sheet_title, headers, rows, instructions=None, text_rows=0):
    """
    headers:      header texts (row 1, bold, frozen)
    rows:         list of lists of cell values
    instructions: optional list of rows for a second "Instructions" sheet
    text_rows:    format this many data rows as Text, so Excel doesn't turn
                  roll numbers / pincodes / dates into numbers (templates)
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        raise FileError(EXCEL_MISSING)

    wb = Workbook()
    ws = wb.active
    ws.title = sheet_title[:31]

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="4B32C3")
    ws.append(headers)
    for c in ws[1]:
        c.font = head_font
        c.fill = head_fill
        c.alignment = Alignment(vertical="center")
    ws.freeze_panes = "A2"

    for r in rows:
        ws.append(["" if v is None else v for v in r])

    for i, h in enumerate(headers, start=1):
        width = max([len(str(h))] + [len(str(r[i - 1])) for r in rows[:200] if i - 1 < len(r)]) + 2
        ws.column_dimensions[get_column_letter(i)].width = min(max(width, 10), 40)
        if text_rows:
            for row_idx in range(2, text_rows + 2):
                ws.cell(row=row_idx, column=i).number_format = "@"

    if instructions:
        ins = wb.create_sheet("Instructions")
        for r in instructions:
            ins.append(r)
        for c in ins[1]:
            c.font = Font(bold=True)
        ins.column_dimensions["A"].width = 30
        ins.column_dimensions["B"].width = 14
        ins.column_dimensions["C"].width = 70
        ins.column_dimensions["D"].width = 22

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
