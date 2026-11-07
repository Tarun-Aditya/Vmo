"""A tiny IMAP server for demos and tests: one mailbox with unread messages that carry contract attachments (read with the real imaplib-based connector), and an outbox that collects
what the app sends (SMTP via aiosmtpd when installed, Slack / Teams / webhook posts via /sim/hook/<name>). Not a mail server: IMAP4 subset (LOGIN, SELECT, SEARCH UNSEEN, FETCH BODY.PEEK[], STORE +FLAGS, LOGOUT)."""
from __future__ import annotations

import asyncio
import email.message
from datetime import date, timedelta

DEMO_USER, DEMO_PASS = "intake@arcadia.demo", "demo-mail-pass"
OUTBOX: list[dict] = []                      # messages the app sent to the simulated channels


def demo_messages() -> list[email.message.EmailMessage]:
    from app import docx_export
    from app.simulators.erp_contracts import _body

    today, out = date.today(), []
    for i, (kind, vendor, who, subj) in enumerate([("SaaS", "Foxglove Marketing Ltd", ("Ines Alba", "Director"), "Signed subscription agreement"), ("NDA", "Redwood Biotech Inc", ("Max Boyd", "CEO"), "NDA for the pilot")]):
        m = email.message.EmailMessage()
        m["From"], m["To"], m["Subject"], m["Message-ID"] = f"{who[0]} <{who[0].split()[0].lower()}@{vendor.split()[0].lower()}.demo>", DEMO_USER, subj, f"<demo{i}@arcadia.demo>"
        m.set_content("Please find the agreement attached.")
        md = _body(kind, vendor, today - timedelta(days=10 + i), 24, 45 if kind == "SaaS" else 0, 1.0 if kind == "SaaS" else None, 60 if kind == "SaaS" else None, "New York", 60 if kind == "SaaS" else None, 120000 if kind == "SaaS" else None, who)
        m.add_attachment(docx_export.md_to_docx(md), maintype="application", subtype="vnd.openxmlformats-officedocument.wordprocessingml.document", filename=f"{vendor.split()[0].lower()}_{kind.lower()}.docx")
        out.append(m)
    return out


class ImapSim:
    def __init__(self, messages: list[email.message.EmailMessage] | None = None):
        self.msgs = messages if messages is not None else demo_messages()
        self.seen: set[int] = set()

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        def w(s: str) -> None:
            writer.write(s.encode() + b"\r\n")

        w("* OK ContractIQ IMAP simulator ready")
        authed = False
        while line := await reader.readline():
            parts = line.decode(errors="replace").strip().split(" ", 2)
            if len(parts) < 2:
                continue
            tag, cmd, rest = parts[0], parts[1].upper(), (parts[2] if len(parts) > 2 else "")
            if cmd == "CAPABILITY":
                w("* CAPABILITY IMAP4rev1"); w(f"{tag} OK done")
            elif cmd == "LOGIN":
                u, _, p = rest.partition(" ")
                authed = u.strip('"') == DEMO_USER and p.strip('"') == DEMO_PASS
                w(f"{tag} OK logged in" if authed else f"{tag} NO [AUTHENTICATIONFAILED] invalid credentials")
            elif not authed:
                w(f"{tag} BAD login first")
            elif cmd == "SELECT":
                w(f"* {len(self.msgs)} EXISTS"); w(f"{tag} OK [READ-WRITE] selected")
            elif cmd == "SEARCH":
                ids = [str(i + 1) for i in range(len(self.msgs)) if (i + 1) not in self.seen] if "UNSEEN" in rest.upper() else [str(i + 1) for i in range(len(self.msgs))]
                w("* SEARCH " + " ".join(ids)); w(f"{tag} OK done")
            elif cmd == "FETCH":
                n = int(rest.split()[0])
                raw = self.msgs[n - 1].as_bytes()
                writer.write(f"* {n} FETCH (BODY[] {{{len(raw)}}}\r\n".encode() + raw + b")\r\n")
                w(f"{tag} OK done")
            elif cmd == "STORE":
                if "\\Seen" in rest:
                    self.seen.add(int(rest.split()[0]))
                w(f"{tag} OK done")
            elif cmd == "NOOP":
                w(f"{tag} OK done")
            elif cmd == "LOGOUT":
                w("* BYE"); w(f"{tag} OK logged out"); await writer.drain(); break
            else:
                w(f"{tag} BAD unsupported")
            await writer.drain()
        writer.close()


async def serve_imap(port: int, sim: ImapSim | None = None):
    sim = sim or ImapSim()
    return await asyncio.start_server(sim.handle, "127.0.0.1", port), sim


from fastapi import APIRouter, Request  # noqa: E402

router = APIRouter(prefix="/sim")


@router.post("/hook/{name}")
async def hook(name: str, request: Request):
    """Stands in for a Slack / Teams / generic webhook URL: keeps what it receives."""
    body = await request.json()
    OUTBOX.append({"channel": name, "kind": "webhook", "text": body.get("text") or body.get("title"), "body": body})
    return {"ok": True}


@router.get("/outbox")
def outbox():
    return OUTBOX[-100:][::-1]


@router.delete("/outbox")
def clear():
    OUTBOX.clear()
    return {"ok": True}


def start_smtp_sink(port: int):
    """SMTP sink for the e-mail channel (needs aiosmtpd, which ships in the dev extras); returns the controller or None."""
    try:
        from aiosmtpd.controller import Controller
    except ImportError:
        return None

    class H:
        async def handle_DATA(self, server, session, envelope):
            raw = envelope.content.decode("utf8", "replace")
            OUTBOX.append({"channel": "email", "kind": "email", "to": envelope.rcpt_tos, "text": next((ln[9:] for ln in raw.splitlines() if ln.lower().startswith("subject: ")), ""), "body": raw[:2000]})
            return "250 OK"

    c = Controller(H(), hostname="127.0.0.1", port=port)
    c.start()
    return c
