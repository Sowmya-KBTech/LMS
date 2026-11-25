"""
THE IMPORT / EXPORT ENGINE - shared by every module.

An import always happens in two steps:

  1. PREVIEW  - read the file, check every row, save NOTHING.
                Each row comes back as "new", "update" or "error" (+ why).
  2. IMPORT   - the same checks run again on the server (the preview is
                never trusted); if ANY row has an error nothing is saved.
                Otherwise every row is saved inside ONE transaction - all
                rows or none - and an ImportLog row records who did it.

Modes
  "add"     Add new only. A row that matches an existing record is an error
            (so an import can never change existing data by accident).
  "upsert"  Add and update. Matching rows are updated; only the cells that
            are filled in change - an empty cell never wipes a value.

To add a module's import, subclass Importer, describe `columns`, implement
the hooks, and register() it (see importers/users.py for a full example).
"""

from django.db import transaction

from .fields import CellError, as_text


# Returned by check_row when a row should be left alone (e.g. no mark typed).
SKIP = object()


class OptionError(Exception):
    """The page's selection (subject, IA...) is missing or not allowed."""

    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


class RowError(Exception):
    """One or more problems with a row (each message shown to the user)."""

    def __init__(self, messages):
        super().__init__("; ".join(messages))
        self.messages = messages if isinstance(messages, list) else [messages]


# ===================== BASE IMPORTER =====================
class Importer:
    key = ""              # url-safe id, e.g. "students"
    label = ""            # shown in the UI, e.g. "Students"
    description = ""      # one line for the import window
    file_stem = ""        # download names: <file_stem>-template.xlsx
    columns = []          # list of fields.Column
    match_column = None   # key of the column used to find existing records
    match_label = ""      # e.g. "roll number" (for messages)
    modes = ("add", "upsert")   # marks importers use ("upsert",): one simple
                                # "save marks" mode, no choice shown
    option_keys = []      # selection the page sends with every request,
                          # e.g. ["teaching_assignment", "number", "max_marks"]

    # ---------- the page's selection ----------
    def resolve_options(self, user, raw):
        """
        Check the page's selection and turn it into real objects. `raw` holds
        only the keys in option_keys. Raise OptionError if it's missing or
        this user may not use it (e.g. not their subject).
        """
        return {}

    def write_blocked(self, options):
        """Return a message if importing is not allowed right now (e.g. a locked IA)."""
        return None

    def file_name(self, options):
        """Download name without extension."""
        return self.file_stem

    # ---------- permissions ----------
    def can_use(self, user):
        return False

    # ---------- export ----------
    def export_queryset(self, user, params, options=None):
        raise NotImplementedError

    def export_row(self, obj):
        """dict of column key -> value, for one record."""
        raise NotImplementedError

    # ---------- import hooks ----------
    def prepare(self, user, options=None):
        """Build lookups once per import. Returns a context dict."""
        return {}

    def find_existing(self, values, ctx):
        """The existing record this row refers to, or None."""
        return None

    def check_row(self, values, existing, ctx, user):
        """
        Extra checks after every cell parsed. Return a "payload" (whatever
        save_row needs), or SKIP to leave the row alone. Raise RowError for
        problems.
        """
        return values

    def save_row(self, payload, existing, ctx, user):
        """Write one row. Return a dict of extra info to show (or None)."""
        raise NotImplementedError

    def check_lookups(self, values, existing, ctx):
        """
        Optional: cheap checks (e.g. "department exists") that should be
        reported even when other cells on the row are wrong, so the user can
        fix everything in one go. Return a list of messages.
        """
        return []

    def row_title(self, values, existing):
        """Short text identifying the row in the preview (e.g. a name)."""
        return ""

    def check_file(self, checked, ctx):
        """
        Optional: checks that need EVERY row at once (e.g. two exams in the
        same class on the same date + session). Called after each row passed
        on its own. `checked` is a list of (row_no, payload, existing).
        Return {row_no: [messages]} for rows that must be refused.
        """
        return {}

    def unique_in_file(self):
        """Column keys that must not repeat inside one file."""
        return [self.match_column] if self.match_column else []

    # ---------- template ----------
    def template_example(self):
        return [[c.example for c in self.columns]]

    def template_rows(self, user, options):
        """Rows written under the header. Pre-filled pages override this."""
        return self.template_example()

    def instructions(self):
        rows = [["Column", "Required", "What to enter", "Example"]]
        for c in self.columns:
            req = {"always": "Yes", "add": "For new rows"}.get(c.required, "No")
            rows.append([c.label, req, c.help, c.example])
        rows.append([])
        rows.append(["How it works", "", "Fill one row per record. Upload the file, check the preview, then confirm.", ""])
        if self.match_label:
            rows.append(["Updating", "", f"To change existing records, choose 'Add and update' - rows are matched by {self.match_label}. Empty cells never erase existing values.", ""])
        return rows


# ===================== RUN (preview or import) =====================
def run(importer, user, headers, rows, mode="add", commit=False, file_name="", options=None):
    """
    Check every row; if commit and there are no errors, save them all.
    Returns a report dict that the frontend renders.
    """
    mode = mode if mode in importer.modes else importer.modes[0]
    known = {c.key for c in importer.columns}
    by_key = {c.key: c for c in importer.columns}

    # A header may be written as the label ("Staff type", "Date of birth
    # (DD-MM-YYYY)") or as the field key ("role") - map both to the key.
    from .fields import norm_header
    alias = {}
    for c in importer.columns:
        alias[norm_header(c.key)] = c.key
        alias[norm_header(c.label)] = c.key
    headers = [alias.get(h, h) for h in headers]
    rows = [(n, {alias.get(k, k): v for k, v in raw.items()}) for n, raw in rows]

    report = {
        "importer": importer.key,
        "mode": mode,
        "file_errors": [],
        "warnings": [],
        "rows": [],
        "counts": {"total": len(rows), "new": 0, "update": 0, "skip": 0, "error": 0},
        "saved": False,
        "extra": [],
    }

    # ---- whole-file checks: required columns present, unknown columns ----
    missing = [c.label for c in importer.columns if c.required == "always" and c.key not in headers]
    if missing:
        report["file_errors"].append(f"Missing column(s): {', '.join(missing)}. Download the template to see the right columns.")
    unknown = [h for h in headers if h and h not in known]
    if unknown:
        report["warnings"].append(f"These columns aren't used and were ignored: {', '.join(unknown)}")
    if not rows:
        report["file_errors"].append("The file has no data rows.")
    if report["file_errors"]:
        report["counts"]["error"] = len(rows)
        return report

    ctx = importer.prepare(user, options or {})
    seen = {k: {} for k in importer.unique_in_file()}
    checked = []        # (row_no, payload, existing)

    for row_no, raw in rows:
        errors = []
        values = {}

        # 1) parse each cell with its column's parser
        for key in known:
            if key not in raw:
                continue
            text = raw[key]
            text = text if hasattr(text, "year") else as_text(text)   # keep Excel dates
            if text == "":
                continue
            col = by_key[key]
            try:
                values[key] = col.parse(text) if col.parse else text
            except CellError as e:
                errors.append(f"{col.label}: {e}")

        cell_errors = bool(errors)

        # 2) which existing record (if any) this row is about
        existing = None
        match_failed = False
        try:
            existing = importer.find_existing(values, ctx)
        except CellError as e:
            errors.append(str(e))
            match_failed = True

        if existing is not None and mode == "add":
            errors.append(
                f"Already exists ({importer.match_label} {values.get(importer.match_column, '')}). "
                f"Choose 'Add and update' to change it."
            )

        # 3) required cells (for new rows / every row)
        if not match_failed:
            for c in importer.columns:
                need = c.required == "always" or (c.required == "add" and existing is None)
                if need and c.key not in values and not any(m.startswith(c.label + ":") for m in errors):
                    errors.append(f"{c.label} is required")

        # 4) duplicates inside this file
        for k in seen:
            v = values.get(k)
            if v in (None, ""):
                continue
            v_norm = str(v).strip().lower()
            if v_norm in seen[k]:
                errors.append(f"{by_key[k].label} '{v}' appears twice in the file (also row {seen[k][v_norm]})")
            else:
                seen[k][v_norm] = row_no

        # 5) module-specific checks. The full check needs every cell to be
        #    readable (otherwise it repeats the same problem in other words);
        #    cheap lookups are reported either way.
        payload = None
        full_check = not errors
        if not full_check and not match_failed:
            errors.extend(m for m in importer.check_lookups(values, existing, ctx) if m not in errors)
        if full_check:
            try:
                payload = importer.check_row(values, existing, ctx, user)
            except RowError as e:
                errors.extend(e.messages)
            except CellError as e:
                errors.append(str(e))

        if errors:
            status = "error"
        elif payload is SKIP:
            status = "skip"
        else:
            status = "update" if existing is not None else "new"
        report["counts"][status] += 1
        report["rows"].append({
            "row": row_no,
            "status": status,
            "key": str(values.get(importer.match_column, "") or ""),
            "title": importer.row_title(values, existing),
            "messages": errors,
        })
        if status in ("new", "update"):
            checked.append((row_no, payload, existing))

    # ---- cross-row checks (all rows known now) ----
    if checked:
        file_errors = importer.check_file(checked, ctx) or {}
        if file_errors:
            by_row = {r["row"]: r for r in report["rows"]}
            for row_no, messages in file_errors.items():
                r = by_row.get(row_no)
                if r is None or not messages:
                    continue
                if r["status"] != "error":
                    report["counts"][r["status"]] -= 1
                    report["counts"]["error"] += 1
                    r["status"] = "error"
                r["messages"].extend(m for m in messages if m not in r["messages"])
            checked = [c for c in checked if not file_errors.get(c[0])]

    if not commit or report["counts"]["error"]:
        return report

    # ---- IMPORT: all rows or none ----
    from .models import ImportLog
    try:
        with transaction.atomic():
            for row_no, payload, existing in checked:
                try:
                    extra = importer.save_row(payload, existing, ctx, user)
                except RowError as e:
                    raise RowError([f"Row {row_no}: {m}" for m in e.messages])
                except Exception as e:   # anything unexpected -> roll everything back
                    raise RowError([f"Row {row_no}: {e}"])
                if extra:
                    report["extra"].append(extra)

            ImportLog.objects.create(
                importer=importer.key,
                file_name=file_name[:255],
                mode=mode,
                rows_total=len(rows),
                created_count=report["counts"]["new"],
                updated_count=report["counts"]["update"],
                imported_by=user if user.is_authenticated else None,
            )
    except RowError as e:
        report["file_errors"] = e.messages + ["Nothing was saved."]
        report["extra"] = []
        return report

    report["saved"] = True
    return report
