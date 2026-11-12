"""Property-level API: properties as records, cross-property comparison of terms and rates, compliance certificates."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import certificates, properties
from app.db import SessionLocal

router = APIRouter(prefix="/api")


@router.get("/properties")
def properties_list():
    with SessionLocal() as s:
        return properties.overview(s)


@router.get("/properties/compare")
def properties_compare():
    with SessionLocal() as s:
        return properties.compare(s)


@router.get("/properties/{pid}")
def property_detail(pid: int):
    with SessionLocal() as s:
        d = properties.detail(s, pid)
    if not d:
        raise HTTPException(404, "property not found")
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
def certificates_list():
    with SessionLocal() as s:
        return certificates.listing(s)


class CertificatePatch(BaseModel):
    expiry_date: date | None = None
    received_on: date | None = None
    reference: str | None = None
    note: str | None = None


@router.patch("/certificates/{cid}")
def certificate_patch(cid: int, b: CertificatePatch):
    data = b.model_dump(exclude_unset=True)
    with SessionLocal() as s:
        if not s.execute(text("SELECT 1 FROM certificates WHERE id = :i"), {"i": cid}).first():
            raise HTTPException(404, "certificate not found")
        for k, v in data.items():
            s.execute(text(f"UPDATE certificates SET {k} = :v, source = 'person', updated_at = now() WHERE id = :i"), {"v": v, "i": cid})      # k is a CertificatePatch field name
        s.commit()
        return next(r for r in certificates.listing(s)["certificates"] if r["id"] == cid)
