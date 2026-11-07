"""REST connector for procurement / ERP systems (Coupa, SAP S/4HANA OData, SAP Ariba, anything with a JSON list endpoint).
Each record becomes a one-row invoice CSV in the feeds folder, which the feeds pipeline matches to contracts like any other invoice. Authentication: OAuth2 client credentials,
an API key header, or a bearer token. The presets only fill in paths and field names; every value can be overridden in the connector's config, because instances differ.
Field mapping: {invoice column: "json.path"} with optional transform suffix "|odata_date" or "|number"."""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime, timedelta, timezone
from typing import Iterator

from app.connectors.base import Connector, ConnectorError, RemoteFile, check, client

COLS = ["external_id", "vendor", "contract_title", "invoice_no", "invoice_date", "period_start", "period_end", "due_date", "paid_date", "amount", "description", "category"]

PRESETS = {
    "coupa": {"token_path": "/oauth2/token", "scope": "core.invoice.read", "path": "/api/invoices", "items_path": "", "params": {"limit": "50"}, "page_param": "offset", "page_size": 50,
              "auth": "oauth_client",
              "mapping": {"external_id": "id", "vendor": "supplier.name", "contract_title": "contract.name", "invoice_no": "invoice-number", "invoice_date": "invoice-date",
                          "due_date": "payment-due-date", "paid_date": "paid-date", "amount": "total-with-taxes|number", "description": "line-items.0.description"},
              "etag": "updated-at"},
    "sap": {"path": "/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice", "items_path": "d.results", "params": {"$format": "json", "$top": "100"}, "auth": "apikey",
            "mapping": {"external_id": "SupplierInvoice", "vendor": "InvoicingParty", "invoice_no": "SupplierInvoiceIDByInvcgParty", "invoice_date": "DocumentDate|odata_date",
                        "due_date": "PaymentDueDate|odata_date", "amount": "InvoiceGrossAmount|number", "description": "DocumentHeaderText"}, "etag": "LastChangeDate"},
    "ariba": {"token_path": "/v2/oauth/token", "path": "/procurement-reporting-details/v2/prod/invoices", "items_path": "Payload", "params": {}, "auth": "oauth_client",
              "mapping": {"external_id": "InvoiceId", "vendor": "SupplierName", "invoice_no": "InvoiceNumber", "invoice_date": "InvoiceDate", "due_date": "DueDate", "amount": "GrossAmount|number",
                          "description": "Description"}, "etag": "LastModified"},
    "rest": {"path": "", "items_path": "", "params": {}, "auth": "bearer", "mapping": {}, "etag": ""},
}


# contract documents: list the contract records, download each attachment (the system's own file, e.g. the signed Word / PDF)
CONTRACT_PRESETS = {
    "coupa": {"path": "/api/contracts", "items_path": "", "id": "id", "supplier": "supplier.name", "etag": "updated-at", "files_path": "attachments", "file_name": "file-name", "file_url": "url",
              "page_param": "offset", "page_size": 50, "scope": "core.contract.read", "params": {"limit": "50"}},
    "sap": {"path": "/sap/opu/odata/sap/API_PURCHASECONTRACT_PROCESS_SRV/A_PurchaseContract", "items_path": "d.results", "id": "PurchaseContract", "supplier": "Supplier", "etag": "LastChangeDate",
            "files_path": "", "file_name": "AttachmentFileName", "file_url": "AttachmentUrl", "params": {"$format": "json", "$top": "100"}},
    "ariba": {"path": "/contract-workspaces/v1/prod/workspaces", "items_path": "Payload", "id": "WorkspaceId", "supplier": "Supplier", "etag": "LastModified", "files_path": "Documents", "file_name": "FileName",
              "file_url": "DownloadUrl", "params": {}},
    "rest": {"path": "", "items_path": "", "id": "id", "supplier": "supplier", "etag": "", "files_path": "attachments", "file_name": "name", "file_url": "url", "params": {}},
}


def dig(obj, path: str):
    for part in [p for p in path.split(".") if p != ""]:
        if isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        elif isinstance(obj, dict):
            obj = obj.get(part)
        else:
            return None
        if obj is None:
            return None
    return obj


def transform(v, how: str | None):
    if v is None:
        return ""
    if how == "odata_date":                              # OData v2: /Date(1700000000000)/
        m = re.search(r"/Date\((-?\d+)", str(v))
        return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=int(m.group(1)))).date().isoformat() if m else str(v)[:10]
    if how == "number":
        return float(str(v).replace(",", ""))
    s = str(v)
    return s[:10] if re.match(r"\d{4}-\d{2}-\d{2}T", s) else s


class RestFeed(Connector):
    kind = "rest"

    def __init__(self, config: dict, secrets: dict, kind: str = "rest"):
        super().__init__(config, secrets)
        self.kind = kind
        self.p = {**PRESETS[kind], **{k: v for k, v in config.items() if v not in (None, "")}}
        self.p["mapping"] = {**PRESETS[kind]["mapping"], **(config.get("mapping") or {})}
        self._rows: dict[str, bytes] = {}

    def _headers(self, c) -> dict:
        a = self.p.get("auth")
        if a == "apikey":
            return {"APIKey": self.sec.get("api_key", ""), "Accept": "application/json"}
        if a == "oauth_client":
            base = (self.p.get("token_url") or self.p.get("base_url", "").rstrip("/") + self.p.get("token_path", "/oauth2/token"))
            data = {"grant_type": "client_credentials", "client_id": self.sec.get("client_id", ""), "client_secret": self.sec.get("client_secret", "")}
            if self.p.get("scope"):
                data["scope"] = self.p["scope"]
            r = check(c.post(base, data=data), "token request")
            return {"Authorization": f"Bearer {r.json()['access_token']}", "Accept": "application/json"}
        return {"Authorization": f"Bearer {self.sec.get('token', '')}", "Accept": "application/json"}

    def _pages(self, c, h) -> Iterator[list]:
        url = self.p.get("base_url", "").rstrip("/") + self.p["path"]
        params, offset, size = dict(self.p.get("params") or {}), 0, int(self.p.get("page_size") or 0)
        while True:
            q = {**params, **({self.p["page_param"]: offset} if self.p.get("page_param") else {})}
            data = check(c.get(url, params=q, headers=h), "list request").json()
            items = dig(data, self.p.get("items_path", "")) if self.p.get("items_path") else data
            if not isinstance(items, list):
                raise ConnectorError("the response has no list of records at items_path " + repr(self.p.get("items_path")))
            yield items
            if not size or len(items) < size:
                return
            offset += size

    def _contracts(self) -> Iterator[RemoteFile]:
        cp = {**CONTRACT_PRESETS[self.kind], **{k: v for k, v in self.cfg.items() if k in CONTRACT_PRESETS[self.kind] and v not in (None, "")}}
        self.p = {**self.p, **{k: cp[k] for k in ("path", "items_path", "params", "page_param", "page_size") if k in cp}, "scope": cp.get("scope", self.p.get("scope"))}
        self._urls: dict[str, str] = {}
        with client() as c:
            h = self._headers(c)
            for items in self._pages(c, h):
                for it in items:
                    files = dig(it, cp["files_path"]) if cp["files_path"] else [it]
                    for f in files or []:
                        name, url, cid = dig(f, cp["file_name"]), dig(f, cp["file_url"]), dig(it, cp["id"])
                        if not name or not url:
                            continue
                        sup = re.sub(r"[^\w .-]+", "_", str(dig(it, cp["supplier"]) or "supplier"))
                        rid = f"{self.kind}:{cid}:{name}"
                        self._urls[rid] = url
                        yield RemoteFile(id=rid, name=name, path=f"{sup}/{name}", etag=str(dig(it, cp["etag"]) or ""), modified=str(dig(it, cp["etag"]) or ""),
                                         web_url=f"{self.p['base_url'].rstrip('/')}/contracts/{cid}", extra={"system": self.kind, "record": str(cid)})

    def test(self) -> dict:
        if not self.p.get("base_url"):
            raise ConnectorError("base_url is required")
        with client() as c:
            h = self._headers(c)
            first = next(self._pages(c, h), [])
        return {"ok": True, "detail": f"connected; first page has {len(first)} record(s)"}

    def list_files(self) -> Iterator[RemoteFile]:
        if not self.p.get("base_url"):
            raise ConnectorError("base_url is required")
        if self.cfg.get("mode") == "contracts":
            yield from self._contracts()
            return
        with client() as c:
            h = self._headers(c)
            for items in self._pages(c, h):
                for it in items:
                    row = {col: "" for col in COLS}
                    for col, spec in self.p["mapping"].items():
                        src, _, how = spec.partition("|")
                        row[col] = transform(dig(it, src), how or None)
                    if not row["external_id"] or not row["amount"]:
                        continue
                    row["external_id"] = f"{self.kind}:{row['external_id']}"
                    row["category"] = row["category"] or "Procurement"
                    buf = io.StringIO()
                    w = csv.DictWriter(buf, COLS)
                    w.writeheader()
                    w.writerow(row)
                    rid = row["external_id"]
                    self._rows[rid] = buf.getvalue().encode()
                    yield RemoteFile(id=rid, name=f"invoice_{re.sub(r'[^A-Za-z0-9]+', '_', rid)}.csv", path=f"invoice_{re.sub(r'[^A-Za-z0-9]+', '_', rid)}.csv", size=len(self._rows[rid]),
                                     etag=str(dig(it, self.p.get("etag") or "") or buf.getvalue().__hash__()))

    def download(self, f: RemoteFile) -> bytes:
        if f.id in getattr(self, "_urls", {}):
            with client() as c:
                return check(c.get(self._urls[f.id], headers=self._headers(c)), "document download").content
        return self._rows[f.id]
