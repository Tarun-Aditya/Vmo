"""A simulated procurement / ERP system for demos and tests: Coupa-shaped and SAP S/4HANA OData-shaped invoice APIs with the same authentication (OAuth client credentials / API key),
paging and field names the connectors expect. The invoices are NOT canned: they are generated from the contracts currently loaded (this month's fee for each active SOW / SaaS,
plus a resend, an over-run, a vendor with no contract and an unsigned contract picked by rule), so the story always matches the data on screen.
Enabled with SIMULATORS=1. Demo credentials: Coupa client demo-client / demo-secret, SAP API key demo-sap-key."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Form, Header, HTTPException, Request
from sqlalchemy import text

from app.db import SessionLocal

router = APIRouter(prefix="/sim")
COUPA_ID, COUPA_SECRET, SAP_KEY = "demo-client", "demo-secret", "demo-sap-key"
_TOKENS: dict[str, float] = {}


def demo_invoices(today: date | None = None, system: str | None = None) -> list[dict]:
    """This month's invoices as an ERP would hold them, derived from the loaded contracts by rule. `system` splits them like a real estate would: SaaS subscriptions sit in the
    SAP system, services (SOWs, vendors without a contract) in Coupa, so connecting both never duplicates an invoice."""
    today = today or date.today()
    with SessionLocal() as s:
        cons = [{**dict(r), "annual_value": float(r["annual_value"] or 0)} for r in s.execute(text("""SELECT contract_id, title, vendor, type, annual_value, total_value, payment_terms_days, expiry_date, fully_executed
                                                   FROM v_effective_terms WHERE status <> 'draft' AND expiry_date >= :t AND COALESCE(annual_value, 0) > 0 AND type IN ('SOW','SaaS') ORDER BY contract_id"""), {"t": today}).mappings()]
        draft_only = [r[0] for r in s.execute(text("SELECT DISTINCT vendor FROM contracts WHERE status='draft' AND vendor NOT IN (SELECT vendor FROM contracts WHERE status <> 'draft') ORDER BY 1"))]
    out = []

    def inv(c, amount, desc, no=None, day=None, vendor=None, title=None, tag=""):
        d = day or today - timedelta(days=3 + (c["contract_id"] * 2) % 20 if c else 9)
        v = vendor or c["vendor"]
        no = no or f"{v[:3].upper()}-{d:%y%m}-S{(c or {'contract_id': 0})['contract_id']:03d}"
        key = f"{no}|{tag}"
        out.append(dict(system="sap" if c and c["type"] == "SaaS" else "coupa", id=int(hashlib.sha1(key.encode()).hexdigest()[:7], 16), vendor=v, contract_title=title if title is not None else (c["title"] if c else ""), invoice_no=no, invoice_date=d,
                        due_date=d + timedelta(days=int((c or {}).get("payment_terms_days") or 45)), amount=round(float(amount), 2), description=desc, updated=datetime(d.year, d.month, d.day, 12, tzinfo=timezone.utc)))

    for c in cons:
        inv(c, c["annual_value"] / 12, f"Services {today:%B %Y}")
    if cons:                                                       # a resend: the same invoice number arrives again under a new ERP id
        c = cons[0]
        inv(c, c["annual_value"] / 12, f"Services {today:%B %Y} (resent)", tag="resend", day=today - timedelta(days=3 + (c["contract_id"] * 2) % 20))
    if len(cons) > 1:                                              # an over-run: out-of-scope work billed on top
        c = cons[1]
        inv(c, c["annual_value"] / 12 * 1.55, f"Services {today:%B %Y} incl. change requests", no=f"{c['vendor'][:3].upper()}-{today:%y%m}-S{c['contract_id']:03d}-CR", tag="overrun")
    if draft_only:                                                 # a vendor with no contract on file
        inv(None, 62500, "Managed services (no statement of work)", vendor=draft_only[0], no=f"{draft_only[0][:3].upper()}-{today:%y%m}-014", tag="nocontract", title="")
    unsigned = [c for c in cons if not c["fully_executed"]]
    if unsigned:
        inv(unsigned[0], unsigned[0]["annual_value"] / 12 * 0.5, "Mobilisation fee", no=f"{unsigned[0]['vendor'][:3].upper()}-{today:%y%m}-MOB", tag="unsigned")
    return [r for r in out if system in (None, r["system"])]


def _ms(d: date) -> str:
    return f"/Date({int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp() * 1000)})/"


# ------------------------------------------------------------------ Coupa-shaped
@router.post("/coupa/oauth2/token")
def coupa_token(grant_type: str = Form(...), client_id: str = Form(""), client_secret: str = Form(""), scope: str = Form("")):
    if grant_type != "client_credentials" or client_id != COUPA_ID or client_secret != COUPA_SECRET:
        raise HTTPException(401, "invalid_client")
    tok = secrets.token_urlsafe(24)
    _TOKENS[tok] = datetime.now().timestamp() + 86400
    return {"access_token": tok, "token_type": "bearer", "expires_in": 86400, "scope": scope}


@router.get("/coupa/api/invoices")
def coupa_invoices(request: Request, limit: int = 50, offset: int = 0):
    tok = (request.headers.get("authorization") or "")[7:]
    if _TOKENS.get(tok, 0) < datetime.now().timestamp():
        raise HTTPException(401, "invalid_token")
    rows = demo_invoices(system="coupa")[offset:offset + limit]
    return [{"id": r["id"], "invoice-number": r["invoice_no"], "invoice-date": r["invoice_date"].isoformat(), "payment-due-date": r["due_date"].isoformat(), "paid-date": None,
             "total-with-taxes": f"{r['amount']:.2f}", "currency": {"code": "USD"}, "status": "approved", "supplier": {"name": r["vendor"]}, "contract": {"name": r["contract_title"]} if r["contract_title"] else None,
             "line-items": [{"description": r["description"]}], "updated-at": r["updated"].isoformat()} for r in rows]


# ------------------------------------------------------------------ SAP S/4HANA OData v2-shaped
@router.get("/sap/sap/opu/odata/sap/API_SUPPLIERINVOICE_PROCESS_SRV/A_SupplierInvoice")
def sap_invoices(apikey: str | None = Header(None, alias="APIKey")):
    if apikey != SAP_KEY:
        raise HTTPException(401, "API key is missing or invalid")
    return {"d": {"results": [{"SupplierInvoice": str(r["id"]), "FiscalYear": str(r["invoice_date"].year), "InvoicingParty": r["vendor"], "SupplierInvoiceIDByInvcgParty": r["invoice_no"],
                               "DocumentDate": _ms(r["invoice_date"]), "PaymentDueDate": _ms(r["due_date"]), "InvoiceGrossAmount": f"{r['amount']:.2f}", "DocumentCurrency": "USD",
                               "DocumentHeaderText": r["description"], "LastChangeDate": r["updated"].strftime("%Y%m%d")} for r in demo_invoices(system="sap")]}}


# ------------------------------------------------------------------ contracts held in the systems (documents + metadata)
from fastapi.responses import Response  # noqa: E402

from app.simulators import erp_contracts  # noqa: E402


def _docx(c: dict) -> bytes:
    from app import docx_export

    return docx_export.md_to_docx(c["md"])


def _pick(system: str) -> list[dict]:
    return [c for c in erp_contracts.erp_contracts() if c["system"] == system]


def _bearer(request: Request) -> None:
    if _TOKENS.get((request.headers.get("authorization") or "")[7:], 0) < datetime.now().timestamp():
        raise HTTPException(401, "invalid_token")


@router.get("/coupa/api/contracts")
def coupa_contracts(request: Request, limit: int = 50, offset: int = 0):
    _bearer(request)
    base = str(request.base_url).rstrip("/")
    return [{"id": c["id"], "name": c["name"], "status": c["status"], "start-date": c["start"].isoformat(), "end-date": c["end"].isoformat(), "supplier": {"name": c["vendor"]},
             "updated-at": f"{c['start'].isoformat()}T09:00:00Z", "attachments": [{"id": c["id"], "file-name": c["filename"], "url": f"{base}/sim/coupa/api/attachments/{c['id']}/file"}]}
            for c in _pick("coupa")[offset:offset + limit]]


@router.get("/coupa/api/attachments/{aid}/file")
def coupa_attachment(aid: int, request: Request):
    _bearer(request)
    c = next((x for x in erp_contracts.erp_contracts() if x["id"] == aid and x["system"] == "coupa"), None)
    if not c:
        raise HTTPException(404, "not found")
    return Response(_docx(c), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.get("/sap/sap/opu/odata/sap/API_PURCHASECONTRACT_PROCESS_SRV/A_PurchaseContract")
def sap_contracts(request: Request, apikey: str | None = Header(None, alias="APIKey")):
    if apikey != SAP_KEY:
        raise HTTPException(401, "API key is missing or invalid")
    base = str(request.base_url).rstrip("/")
    return {"d": {"results": [{"PurchaseContract": str(c["id"]), "PurchaseContractType": "MK", "Supplier": c["vendor"], "PurchasingDocumentName": c["name"], "ValidityStartDate": _ms(c["start"]), "ValidityEndDate": _ms(c["end"]),
                               "LastChangeDate": c["start"].strftime("%Y%m%d"), "AttachmentFileName": c["filename"], "AttachmentUrl": f"{base}/sim/sap/sap/opu/odata/sap/API_CV_ATTACHMENT_SRV/Original/{c['id']}"}
                              for c in _pick("sap")]}}


@router.get("/sap/sap/opu/odata/sap/API_CV_ATTACHMENT_SRV/Original/{cid}")
def sap_attachment(cid: int, apikey: str | None = Header(None, alias="APIKey")):
    if apikey != SAP_KEY:
        raise HTTPException(401, "API key is missing or invalid")
    c = next((x for x in erp_contracts.erp_contracts() if x["id"] == cid and x["system"] == "sap"), None)
    if not c:
        raise HTTPException(404, "not found")
    return Response(_docx(c), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@router.post("/ariba/v2/oauth/token")
def ariba_token(grant_type: str = Form(...), client_id: str = Form(""), client_secret: str = Form("")):
    if grant_type != "client_credentials" or client_id != "demo-ariba-key" or client_secret != "demo-ariba-secret":
        raise HTTPException(401, "invalid_client")
    tok = secrets.token_urlsafe(24)
    _TOKENS[tok] = datetime.now().timestamp() + 86400
    return {"access_token": tok, "token_type": "bearer", "expires_in": 86400}


@router.get("/ariba/contract-workspaces/v1/prod/workspaces")
def ariba_contracts(request: Request):
    _bearer(request)
    base = str(request.base_url).rstrip("/")
    return {"Payload": [{"WorkspaceId": f"CW{c['id']}", "Title": c["name"], "Supplier": c["vendor"], "AgreementDate": c["start"].isoformat(), "ExpirationDate": c["end"].isoformat(), "Status": c["status"],
                         "LastModified": f"{c['start'].isoformat()}T09:00:00Z", "Documents": [{"FileName": c["filename"], "DownloadUrl": f"{base}/sim/ariba/contract-workspaces/v1/prod/documents/{c['id']}"}]}
                        for c in _pick("ariba")]}


@router.get("/ariba/contract-workspaces/v1/prod/documents/{cid}")
def ariba_document(cid: int, request: Request):
    _bearer(request)
    c = next((x for x in erp_contracts.erp_contracts() if x["id"] == cid and x["system"] == "ariba"), None)
    if not c:
        raise HTTPException(404, "not found")
    return Response(_docx(c), media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
