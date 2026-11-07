"""E-signature. Two providers behind one interface:
* internal: a signer opens a personal link, reads the exact version, types their name and agrees. We record time, IP, browser and the SHA-256 of the document, and issue a
  completion certificate. Fine for NDAs and low-risk papers; it is not a qualified/advanced e-signature.
* docusign: creates a DocuSign envelope (REST v2.1), authenticates with a JWT grant (or a given access token), and reads status / the signed PDF back.
When everyone has signed, a signature block is appended to the document as a new version, so extraction picks up the signatories and dates like any executed contract."""
from __future__ import annotations

import base64
import hashlib
import os
import time
from datetime import datetime, timezone

import httpx
import jwt


def simulated() -> bool:
    """Demo mode: no DocuSign credentials are set and SIMULATORS=1, so the built-in stand-in service is used."""
    return os.environ.get("SIMULATORS", "0") == "1" and not os.environ.get("DOCUSIGN_ACCOUNT_ID")


def doc_hash(md: str) -> str:
    return hashlib.sha256((md or "").encode()).hexdigest()


def signature_block(signers: list[dict]) -> str:
    cols = [s for s in signers if s["status"] == "signed"]
    names = {"customer": "Customer", "supplier": "Supplier"}
    head = "| | " + " | ".join(names.get(s["role"], "Signatory") for s in cols) + " |"
    sep = "|---|" + "---|" * len(cols)
    rows = [("Signed by", [s["typed_signature"] or s["name"] for s in cols]), ("Email", [s["email"] for s in cols]),
            ("Date", [s["signed_at"].strftime("%d %B %Y") if hasattr(s["signed_at"], "strftime") else str(s["signed_at"])[:10] for s in cols])]
    body = "\n".join("| **" + k + "** | " + " | ".join(v) + " |" for k, v in rows)
    return f"\n\n## Signatures\n\nSigned electronically.\n\n{head}\n{sep}\n{body}\n"


# ------------------------------------------------------------------ DocuSign
class DocuSign:
    def __init__(self):
        sim = simulated()
        self.base = (os.environ.get("DOCUSIGN_BASE_URI") or (os.environ.get("PUBLIC_API_URL", "http://localhost:8000").rstrip("/") + "/sim/docusign/restapi" if sim else "https://demo.docusign.net/restapi")).rstrip("/")
        self.account = os.environ.get("DOCUSIGN_ACCOUNT_ID") or ("sim-account" if sim else "")
        self.oauth = os.environ.get("DOCUSIGN_OAUTH_HOST", "https://account-d.docusign.com").rstrip("/")
        self._tok: tuple[str, float] | None = None

    @staticmethod
    def configured() -> bool:
        return bool(os.environ.get("DOCUSIGN_ACCOUNT_ID") and (os.environ.get("DOCUSIGN_ACCESS_TOKEN") or os.environ.get("DOCUSIGN_PRIVATE_KEY"))) or simulated()

    def token(self) -> str:
        if os.environ.get("DOCUSIGN_ACCESS_TOKEN"):
            return os.environ["DOCUSIGN_ACCESS_TOKEN"]
        if simulated() and not os.environ.get("DOCUSIGN_PRIVATE_KEY"):
            return "sim-token"
        if self._tok and self._tok[1] > time.time() + 60:
            return self._tok[0]
        now = int(time.time())
        assertion = jwt.encode({"iss": os.environ["DOCUSIGN_INTEGRATION_KEY"], "sub": os.environ["DOCUSIGN_USER_ID"], "aud": self.oauth.split("//")[-1], "iat": now, "exp": now + 3000, "scope": "signature impersonation"},
                               os.environ["DOCUSIGN_PRIVATE_KEY"].replace("\\n", "\n"), algorithm="RS256")
        r = httpx.post(f"{self.oauth}/oauth/token", data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}, timeout=20)
        r.raise_for_status()
        self._tok = (r.json()["access_token"], time.time() + int(r.json().get("expires_in", 3600)))
        return self._tok[0]

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    def send(self, title: str, pdf_or_docx: bytes, filename: str, signers: list[dict]) -> tuple[str, list[dict]]:
        ext = filename.rsplit(".", 1)[-1]
        body = {"emailSubject": f"Please sign: {title}", "status": "sent",
                "documents": [{"documentBase64": base64.b64encode(pdf_or_docx).decode(), "name": title, "fileExtension": ext, "documentId": "1"}],
                "recipients": {"signers": [{"email": s["email"], "name": s["name"], "recipientId": str(i + 1), "routingOrder": str(i + 1)} for i, s in enumerate(signers)]}}
        if os.environ.get("PUBLIC_API_URL"):                  # DocuSign Connect: tell us when the envelope changes
            body["eventNotification"] = {"url": os.environ["PUBLIC_API_URL"].rstrip("/") + "/api/signatures/webhook/docusign", "requireAcknowledgment": "true", "envelopeEvents": [{"envelopeEventStatusCode": "completed"}, {"envelopeEventStatusCode": "declined"}]}
        r = httpx.post(f"{self.base}/v2.1/accounts/{self.account}/envelopes", json=body, headers=self._h(), timeout=60)
        r.raise_for_status()
        j = r.json()
        return j["envelopeId"], (j.get("simulator") or {}).get("signing_links", [])

    def status(self, envelope_id: str) -> dict:
        r = httpx.get(f"{self.base}/v2.1/accounts/{self.account}/envelopes/{envelope_id}", headers=self._h(), timeout=30)
        r.raise_for_status()
        return r.json()

    def signed_pdf(self, envelope_id: str) -> bytes:
        r = httpx.get(f"{self.base}/v2.1/accounts/{self.account}/envelopes/{envelope_id}/documents/combined", headers=self._h(), timeout=60)
        r.raise_for_status()
        return r.content


def certificate(req: dict, signers: list[dict]) -> dict:
    return {"document": req["title"], "version": req["version"], "sha256": req["doc_hash"], "provider": req["provider"],
            "completed_at": datetime.now(timezone.utc).isoformat(), "signers": [{"name": s["name"], "email": s["email"], "role": s["role"], "signed_at": str(s["signed_at"]), "ip": s["ip"], "signature": s["typed_signature"]} for s in signers]}
