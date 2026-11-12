"""Fictional invoices, service-level reports and acceptance certificates, written as DOCUMENTS (Markdown, Word, PDF) in three layouts each, for demos and tests.
Rows come from feeds.generate_rows() (which plants problems by rule over whatever contracts are loaded); ground truth is written to labels_ops.json from the rows,
independently of the document text. The product only ever reads the documents."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from sqlalchemy import text

from app import feeds
from app.config import data_path
from app.db import SessionLocal

def _customer() -> str:
    """The fixtures are addressed to the loaded corpus's customer (hotel group or retailer), not to a fixed name."""
    import os

    n = (os.environ.get("CUSTOMER_NAMES") or "Arcadia").split(",")[0].strip()
    return {"arcadia": "Arcadia Retail Inc.", "seabright": "Seabright Hotels & Resorts Ltd"}.get(n.lower(), n)


CUSTOMER = _customer()
FMT = ["md", "docx", "pdf"]


def _amt(v) -> str:
    return f"USD {float(v):,.2f}"


def invoice_md(r: dict, style: int) -> str:
    d, due, paid = r["invoice_date"], r["due_date"], r["paid_date"] or None
    ps, pe, ref, desc = r["period_start"] or None, r["period_end"] or None, r["contract_title"], r["description"]
    if style == 0:
        return (f"# INVOICE\n\n**Invoice No.:** {r['invoice_no']}\n\n**Invoice date:** {d:%d %B %Y}\n\n**Due date:** {due:%d %B %Y}\n\n**From:** {r['vendor']}\n\n**Bill to:** {CUSTOMER}\n\n"
                + (f"**Reference:** {ref}\n\n" if ref else "") + (f"**Service period:** {ps:%d %b %Y} – {pe:%d %b %Y}\n\n" if ps and pe else "")
                + f"| Description | Amount (USD) |\n|---|---|\n| {desc} | {float(r['amount']):,.2f} |\n\n**Total due: {_amt(r['amount'])}**\n\n" + (f"Paid on: {paid:%d %B %Y}\n" if paid else ""))
    if style == 1:
        return (f"# TAX INVOICE\n\n{r['vendor']}\n\nDate of issue: {d:%B %d, %Y}\n\nInvoice number: {r['invoice_no']}\n\n" + (f"Your ref: {ref}\n\n" if ref else "") + f"To: {CUSTOMER}\n\n"
                f"For: {desc}\n\n" + (f"Billing period: {ps:%d %B %Y} to {pe:%d %B %Y}\n\n" if ps and pe else "") + f"Amount payable: {_amt(r['amount'])}\n\nPayment due by {due:%d %B %Y}\n\n"
                + (f"Payment received on {paid:%d %B %Y}\n" if paid else ""))
    rows = [("Invoice number", r["invoice_no"]), ("Date", f"{d:%Y-%m-%d}")] + ([("Agreement", ref)] if ref else []) + [("Description", desc)] + ([("Period", f"{ps:%Y-%m-%d} to {pe:%Y-%m-%d}")] if ps and pe else []) \
        + [("Total", _amt(r["amount"])), ("Due date", f"{due:%Y-%m-%d}")] + ([("Date paid", f"{paid:%Y-%m-%d}")] if paid else [])
    return f"# {r['vendor']}\n\n## Invoice\n\n| | |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows) + f"\n\nBilled to {CUSTOMER}\n"


def sla_md(vendor: str, title: str, period: date, rows: list[dict], names: dict[str, str], style: int) -> str:
    head = f"# Monthly Service Level Report\n\n**Vendor:** {vendor}\n\n**Agreement:** {title}\n\n**Reporting period:** {period:%B %Y}\n\n"
    if style == 0:
        body = "| Service level | Target | Actual | Incidents | Comment |\n|---|---|---|---|---|\n" + "\n".join(f"| {names[r['metric_key']]} | – | {r['actual']:g} | {r['incidents']} | {r['note']} |" for r in rows)
    else:
        body = "| Service level | Target | Actual | Incidents | Comment |\n|---|---|---|---|---|\n" + "\n".join(f"| {names[r['metric_key']]} | per contract | {r['actual']:g} | {r['incidents']} | {r['note'] or 'No issues'} |" for r in rows)
    return head + body + "\n"


def acceptance_md(vendor: str, title: str, milestone: str, due: date, done: date, note: str, style: int) -> str:
    if style == 0:
        return (f"# Milestone Acceptance Certificate\n\n**Vendor:** {vendor}\n\n**Agreement:** {title}\n\n**Milestone:** {milestone}\n\n**Due date:** {due:%d %B %Y}\n\n"
                f"**Accepted on:** {done:%d %B %Y}\n\n**Comments:** {note}\n\nSigned for {CUSTOMER}\n")
    return (f"# Certificate of Acceptance\n\nSupplier: {vendor}\n\nReference: {title}\n\nMilestone: {milestone} (due {due:%d %B %Y})\n\nThe Customer confirms the deliverables were accepted on {done:%B %d, %Y}.\n\n"
            f"Remarks: {note}\n")


def _write(out: Path, stem: str, md: str, fmt: str, batch: list[Path], tmp: Path) -> str:
    if fmt == "md":
        (out / f"{stem}.md").write_text(md)
        return f"{stem}.md"
    src = tmp / f"{stem}.md"
    src.write_text(md)
    dst = (out if fmt == "docx" else tmp) / f"{stem}.docx"
    subprocess.run(["pandoc", str(src), "-o", str(dst)], check=True, timeout=60)
    if fmt == "pdf":
        batch.append(dst)
    return f"{stem}.{fmt}"


def generate(today: date | None = None) -> dict:
    today = today or date.today()
    invoices, sla, status = feeds.generate_rows(today)
    root = data_path() / "feeds"
    if root.exists():
        shutil.rmtree(root)
    inv_dir, sla_dir, acc_dir = (root / "invoices", root / "reports", root / "acceptance")
    for d in (inv_dir, sla_dir, acc_dir):
        d.mkdir(parents=True)
    labels: dict = {"invoices": {}, "sla": {}, "acceptance": {}}
    pdfs: list[tuple[Path, Path]] = []
    with SessionLocal() as s:
        names = {r[0]: r[1] for r in s.execute(text("SELECT key, name FROM metrics"))}
        obl = {(r["title"], r["vendor"], r["key"]): dict(r) for r in s.execute(text("SELECT c.title, c.vendor, o.key, o.title AS otitle, o.due_date FROM obligations o JOIN contracts c ON c.id=o.contract_id WHERE o.kind='milestone'")).mappings()}
    with tempfile.TemporaryDirectory() as td:
        tmp, batch = Path(td), []
        for i, r in enumerate(invoices):
            stem, fmt = f"invoice_{i + 1:03d}", FMT[i % 3]
            fn = _write(inv_dir, stem, invoice_md(r, (i // 3) % 3), fmt, batch, tmp)
            if fmt == "pdf":
                pdfs.append((tmp / f"{stem}.pdf", inv_dir / fn))
            labels["invoices"][fn] = {k: (str(v) if isinstance(v, date) else v) for k, v in r.items() if k in ("vendor", "contract_title", "invoice_no", "invoice_date", "due_date", "paid_date", "amount")}
            labels["invoices"][fn]["paid_date"] = labels["invoices"][fn]["paid_date"] or None
        groups: dict[tuple, list] = {}
        for r in sla:
            groups.setdefault((r["contract_title"], r["vendor"], r["period"]), []).append(r)
        for j, ((title, vendor, period), rows) in enumerate(sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))):
            stem, fmt = f"sla_report_{j + 1:03d}", FMT[j % 3]
            fn = _write(sla_dir, stem, sla_md(vendor, title, period, rows, names, j % 2), fmt, batch, tmp)
            if fmt == "pdf":
                pdfs.append((tmp / f"{stem}.pdf", sla_dir / fn))
            labels["sla"][fn] = {"contract_title": title, "vendor": vendor, "period": str(period), "rows": [{k: r[k] for k in ("metric_key", "actual", "incidents")} for r in rows]}
        for k, r in enumerate(status):
            o = obl.get((r["contract_title"], r["vendor"], r["key"]))
            if not o:
                continue
            stem, fmt = f"acceptance_{k + 1:03d}", FMT[k % 3]
            fn = _write(acc_dir, stem, acceptance_md(r["vendor"], r["contract_title"], o["otitle"].removeprefix("Milestone: "), o["due_date"], r["completed_on"], r["note"], k % 2), fmt, batch, tmp)
            if fmt == "pdf":
                pdfs.append((tmp / f"{stem}.pdf", acc_dir / fn))
            labels["acceptance"][fn] = {"contract_title": r["contract_title"], "vendor": r["vendor"], "key": r["key"], "completed_on": str(r["completed_on"])}
        if batch:
            subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", td, *map(str, batch)], check=True, capture_output=True, timeout=900)
            for src, dst in pdfs:
                shutil.copy(src, dst)
    (data_path() / "labels_ops.json").write_text(json.dumps(labels, indent=1, default=str))
    return {"invoices": len(labels["invoices"]), "sla_reports": len(labels["sla"]), "acceptance": len(labels["acceptance"])}
