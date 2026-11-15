"""Property-level API: properties as records, cross-property comparison of terms and rates, compliance certificates."""
from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import text

from app import certificates, onsite, properties, scope
from app.db import SessionLocal

router = APIRouter(prefix="/api")


@router.get("/properties")
def properties_list(request: Request):
    mine = scope.user_property(request)
    with SessionLocal() as s:
        ov = properties.overview(s)
    if mine:                                    # a property manager sees their own property only
        ov["properties"] = [p for p in ov["properties"] if p["property"] == mine]
    return ov


@router.get("/properties/compare")
def properties_compare():
    with SessionLocal() as s:
        return properties.compare(s)


@router.get("/properties/{pid}")
def property_detail(pid: int, request: Request):
    with SessionLocal() as s:
        d = properties.detail(s, pid)
    if not d:
        raise HTTPException(404, "property not found")
    scope.effective(request, d["property"])
    return d


class PropertyPatch(BaseModel):
    city: str | None = None
    country: str | None = None
    kind: str | None = None
    rooms: int | None = None
    opened_year: int | None = None


@router.patch("/properties/{pid}")
def property_patch(pid: int, b: PropertyPatch):
    data = b.model_dump(exclude_unset=True)
    if data.get("rooms") is not None and data["rooms"] <= 0:
        raise HTTPException(422, "rooms must be a positive number")
    with SessionLocal() as s:
        if not s.execute(text("SELECT 1 FROM properties WHERE id = :i"), {"i": pid}).first():
            raise HTTPException(404, "property not found")
        for k, v in data.items():
            s.execute(text(f"UPDATE properties SET {k} = :v WHERE id = :i"), {"v": v, "i": pid})      # k is a PropertyPatch field name, never user text
        s.commit()
        return properties.detail(s, pid)


class Coverage(BaseModel):
    property_ids: list[int]


@router.put("/contracts/{cid}/coverage")
def coverage_put(cid: int, b: Coverage):
    """State which properties a group-level agreement covers (an empty list returns it to the derived coverage)."""
    with SessionLocal() as s:
        c = s.execute(text("SELECT property FROM contracts WHERE id = :i"), {"i": cid}).first()
        if not c:
            raise HTTPException(404, "contract not found")
        if c[0]:
            raise HTTPException(409, "this contract already names its property")
        s.execute(text("DELETE FROM contract_coverage WHERE contract_id = :c"), {"c": cid})
        for p in set(b.property_ids):
            if not s.execute(text("SELECT 1 FROM properties WHERE id = :i"), {"i": p}).first():
                raise HTTPException(422, f"unknown property {p}")
            s.execute(text("INSERT INTO contract_coverage (contract_id, property_id) VALUES (:c, :p)"), {"c": cid, "p": p})
        s.commit()
        return [dict(r) for r in s.execute(text("SELECT property_id, property, basis, share FROM v_property_contracts WHERE contract_id = :c ORDER BY property"), {"c": cid}).mappings()]


@router.get("/certificates")
def certificates_list(request: Request, property: str | None = None):
    prop = scope.effective(request, property)
    with SessionLocal() as s:
        out = certificates.listing(s)
        if prop:
            vs = set(scope.vendors(s, prop))
            out["certificates"] = [c for c in out["certificates"] if c["vendor"] in vs]
            out["summary"] = {k: sum(1 for c in out["certificates"] if c["status"] == k) for k in out["summary"]}
        return {**out, "property": prop}


class CertificatePatch(BaseModel):
    expiry_date: date | None = None
    received_on: date | None = None
    reference: str | None = None
    note: str | None = None


@router.patch("/certificates/{cid}")
def certificate_patch(cid: int, b: CertificatePatch, request: Request):
    data = b.model_dump(exclude_unset=True)
    with SessionLocal() as s:
        row = s.execute(text("SELECT vendor FROM certificates WHERE id = :i"), {"i": cid}).first()
        if not row:
            raise HTTPException(404, "certificate not found")
        mine = scope.user_property(request)
        if mine and row[0] not in scope.vendors(s, mine):
            raise HTTPException(403, f"Your account is limited to {mine}")
        for k, v in data.items():
            s.execute(text(f"UPDATE certificates SET {k} = :v, source = 'person', updated_at = now() WHERE id = :i"), {"v": v, "i": cid})      # k is a CertificatePatch field name
        s.commit()
        return next(r for r in certificates.listing(s)["certificates"] if r["id"] == cid)


# ------------------------------------------------------------------ the property manager's page, service calls, supplier contacts
@router.get("/my-property")
def my_property(request: Request, property: str | None = None):
    prop = scope.effective(request, property)
    with SessionLocal() as s:
        if not prop:
            return {"choose": [r[0] for r in s.execute(text("SELECT name FROM properties ORDER BY name"))]}
        d = onsite.my_property(s, prop)
    if not d:
        raise HTTPException(404, "property not found")
    return d


@router.get("/service-events")
def service_events(request: Request, property: str | None = None, days: int = 90):
    prop = scope.effective(request, property)
    if not prop:
        raise HTTPException(422, "choose a property")
    with SessionLocal() as s:
        return onsite.service(s, prop, days)


class ServiceIn(BaseModel):
    property: str | None = None
    vendor: str
    kind: str = "fault"
    description: str | None = None
    reported_at: datetime | None = None
    attended_at: datetime | None = None
    resolved_at: datetime | None = None


@router.post("/service-events")
def service_add(b: ServiceIn, request: Request):
    from app.routes_auth import me

    prop = scope.effective(request, b.property)
    if not prop or b.kind not in ("fault", "emergency", "request", "planned"):
        raise HTTPException(422, "a property, a vendor and a kind of fault, emergency, request or planned are required")
    with SessionLocal() as s:
        if b.vendor not in scope.vendors(s, prop):
            raise HTTPException(422, f"{b.vendor} has no contract that applies at {prop}")
        reported = b.reported_at or datetime.now().astimezone()
        if b.attended_at and b.attended_at < reported or b.resolved_at and b.resolved_at < reported:
            raise HTTPException(422, "attended and resolved times cannot be before the call was reported")
        rid = s.execute(text("""INSERT INTO service_events (property, vendor, kind, description, reported_at, attended_at, resolved_at, reported_by)
                                VALUES (:p,:v,:k,:d,:r,:a,:z,:by) RETURNING id"""),
                        {"p": prop, "v": b.vendor, "k": b.kind, "d": b.description, "r": reported, "a": b.attended_at, "z": b.resolved_at, "by": me(request).get("email")}).scalar()
        s.commit()
    return {"id": rid}


class ServicePatch(BaseModel):
    attended_at: datetime | None = None
    resolved_at: datetime | None = None


@router.patch("/service-events/{eid}")
def service_patch(eid: int, b: ServicePatch, request: Request):
    data = b.model_dump(exclude_unset=True)
    with SessionLocal() as s:
        row = s.execute(text("SELECT property, reported_at FROM service_events WHERE id = :i"), {"i": eid}).first()
        if not row:
            raise HTTPException(404, "service call not found")
        scope.effective(request, row[0])
        for k, v in data.items():
            if v and v < row[1]:
                raise HTTPException(422, "a time cannot be before the call was reported")
            s.execute(text(f"UPDATE service_events SET {k} = :v WHERE id = :i"), {"v": v, "i": eid})      # k is a ServicePatch field name
        s.commit()
    return {"id": eid}


@router.get("/vendor-contacts")
def vendor_contacts(request: Request, property: str | None = None, vendor: str | None = None):
    prop = scope.effective(request, property)
    with SessionLocal() as s:
        return onsite.contacts(s, prop, vendor)


class ContactIn(BaseModel):
    vendor: str
    property: str | None = None
    name: str
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    note: str | None = None


@router.post("/vendor-contacts")
def contact_add(b: ContactIn, request: Request):
    mine = scope.user_property(request)
    prop = mine or (b.property or None)                  # a property manager's contacts are for their own property
    if not b.name.strip() or not b.vendor.strip():
        raise HTTPException(422, "a vendor and a name are required")
    with SessionLocal() as s:
        if mine and b.vendor not in scope.vendors(s, mine):
            raise HTTPException(422, f"{b.vendor} has no contract that applies at {mine}")
        cid = s.execute(text("""INSERT INTO vendor_contacts (vendor, property, name, role, phone, email, note) VALUES (:v,:p,:n,:r,:ph,:e,:no) RETURNING id"""),
                        {"v": b.vendor, "p": prop, "n": b.name.strip(), "r": b.role, "ph": b.phone, "e": b.email, "no": b.note}).scalar()
        s.commit()
    return {"id": cid}


@router.delete("/vendor-contacts/{cid}")
def contact_delete(cid: int, request: Request):
    mine = scope.user_property(request)
    with SessionLocal() as s:
        row = s.execute(text("SELECT property FROM vendor_contacts WHERE id = :i"), {"i": cid}).first()
        if not row:
            raise HTTPException(404, "contact not found")
        if mine and row[0] != mine:
            raise HTTPException(403, "only the contacts recorded for your property can be removed")
        s.execute(text("DELETE FROM vendor_contacts WHERE id = :i"), {"i": cid})
        s.commit()
    return {"deleted": cid}
