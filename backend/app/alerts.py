"""Alerts: rules evaluated over the live data (contracts, obligations, SLA, spend, vendor risk, review queue, connectors), each event raised once
(dedupe key), shown in the notification centre and delivered to the channels the admin configured (e-mail, Slack, Teams, any webhook)."""
from __future__ import annotations

import json
import smtplib
import time
from datetime import date, timedelta
from email.message import EmailMessage

import httpx
from sqlalchemy import text

from app.connectors import crypto
from app.db import SessionLocal

SEV_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}

# (key, name, description, kind, severity, params, channels)
DEFAULT_RULES = [
    ("renewal_notice_passed", "Auto-renewal notice deadline passed", "An auto-renewing contract's non-renewal notice deadline has passed and it has not expired.", "renewal_notice", "critical", {"days": 0}, ["in_app", "email", "chat"]),
    ("renewal_notice_soon", "Auto-renewal notice due soon", "The non-renewal notice deadline of an auto-renewing contract is near.", "renewal_notice", "high", {"days": 30}, ["in_app", "email", "chat"]),
    ("contract_expiring_30", "Contract expiring within 30 days", "", "expiring", "high", {"days": 30}, ["in_app", "email"]),
    ("contract_expiring_90", "Contract expiring within 90 days", "", "expiring", "medium", {"days": 90}, ["in_app"]),
    ("obligation_overdue", "Obligation overdue", "An open obligation is past its date.", "obligation_overdue", "high", {}, ["in_app", "email", "chat"]),
    ("obligation_due_soon", "Obligation due soon", "", "obligation_due", "medium", {"days": 7}, ["in_app"]),
    ("sla_breach", "SLA breached", "A monthly SLA actual missed the contract target.", "sla_breach", "high", {"months": 2}, ["in_app", "email", "chat"]),
    ("spend_exception", "Serious spend exception", "An invoice or contract breaks a spend rule at or above this severity.", "spend_exception", "high", {"min_severity": "high"}, ["in_app", "email", "chat"]),
    ("vendor_risk_tier", "Vendor risk tier high or critical", "A vendor's risk score reached the 'high' or 'critical' tier.", "vendor_tier", "high", {"min_tier": "high"}, ["in_app", "chat"]),
    ("review_waiting", "Draft waiting for review", "A vendor draft has been in the review queue longer than this.", "review_waiting", "medium", {"days": 5}, ["in_app"]),
    ("approval_waiting", "Approval step stalled", "An approver has not decided a step for longer than the rule's reminder period.", "approval_waiting", "medium", {}, ["in_app", "email"]),
    ("certificate_expiry", "Vendor certificate expired or about to", "A certificate a vendor must hold under its contract (insurance, food safety, inspection, payment-card) has run out or is about to.", "certificate", "high", {"days": 30}, ["in_app", "email", "chat"]),
    ("connector_error", "Connector sync failed", "A cloud-storage connector could not sync.", "connector_error", "high", {}, ["in_app", "email"]),
]


def ensure_defaults(s) -> None:
    for i, (k, n, d, kind, sev, params, ch) in enumerate(DEFAULT_RULES):
        s.execute(text("INSERT INTO alert_rules (key, name, description, kind, severity, params, channels, builtin, sort_order) VALUES (:k,:n,:d,:kd,:s,CAST(:p AS jsonb),:c,true,:o) ON CONFLICT DO NOTHING"),
                  {"k": k, "n": n, "d": d, "kd": kind, "s": sev, "p": json.dumps(params), "c": ch, "o": i})


def _candidates(s, r: dict, today: date) -> list[dict]:
    kind, p, out = r["kind"], r["params"] or {}, []
    if kind == "renewal_notice":
        rows = s.execute(text("SELECT contract_id, title, vendor, notice_deadline, notice_days_left, expiry_date FROM v_renewals WHERE auto_renew AND days_left >= 0"))
        for x in rows.mappings():
            left = x["notice_days_left"]
            passed = r["key"].endswith("passed")
            if passed and left is not None and left < 0 or (not passed and left is not None and 0 <= left <= int(p.get("days", 30))):
                out.append(dict(dedupe=f"{r['key']}:{x['contract_id']}:{x['notice_deadline']}", title=f"{'Notice deadline passed' if passed else 'Notice due in ' + str(left) + ' days'}: {x['title']}",
                                body=f"{x['vendor']} auto-renews; the non-renewal notice deadline is {x['notice_deadline']:%d %b %Y} and the contract ends {x['expiry_date']:%d %b %Y}.", contract_id=x["contract_id"], vendor=x["vendor"], link=f"/contracts/{x['contract_id']}"))
    elif kind == "expiring":
        days = int(p.get("days", 30))
        lo = 0 if r["key"].endswith("30") else 31
        for x in s.execute(text("SELECT contract_id, title, vendor, expiry_date, days_left FROM v_renewals WHERE days_left BETWEEN :lo AND :hi"), {"lo": lo, "hi": days}).mappings():
            out.append(dict(dedupe=f"{r['key']}:{x['contract_id']}:{x['expiry_date']}", title=f"Expires in {x['days_left']} days: {x['title']}", body=f"{x['vendor']} · ends {x['expiry_date']:%d %b %Y}.", contract_id=x["contract_id"], vendor=x["vendor"], link=f"/contracts/{x['contract_id']}"))
    elif kind in ("obligation_overdue", "obligation_due"):
        cond = "status = 'overdue'" if kind == "obligation_overdue" else f"status = 'open' AND days_left BETWEEN 0 AND {int(p.get('days', 7))}"
        for x in s.execute(text(f"SELECT obligation_id, contract_id, title, vendor, obligation, due_date, days_left FROM v_obligations WHERE contract_status <> 'draft' AND {cond}")).mappings():
            out.append(dict(dedupe=f"{r['key']}:{x['obligation_id']}:{x['due_date']}", title=f"{'Overdue' if kind == 'obligation_overdue' else 'Due in ' + str(x['days_left']) + ' days'}: {x['obligation']}",
                            body=f"{x['title']} ({x['vendor']}), due {x['due_date']:%d %b %Y}.", contract_id=x["contract_id"], vendor=x["vendor"], link="/obligations"))
    elif kind == "sla_breach":
        since = today - timedelta(days=31 * int(p.get("months", 2)))
        for x in s.execute(text("SELECT contract_id, title, vendor, metric_key, period, actual, target FROM v_sla WHERE breach AND period >= :d"), {"d": since}).mappings():
            out.append(dict(dedupe=f"{r['key']}:{x['contract_id']}:{x['metric_key']}:{x['period']}", title=f"SLA missed {x['period']:%b %Y}: {float(x['actual']):g} vs target {float(x['target']):g}", body=f"{x['title']} ({x['vendor']}).",
                            contract_id=x["contract_id"], vendor=x["vendor"], link="/obligations"))
    elif kind == "spend_exception":
        mn = SEV_RANK[p.get("min_severity", "high")]
        # one alert per vendor and kind of problem, however many invoices show it: five duplicate invoices from one supplier are one thing to chase, not five
        groups: dict[tuple, list[dict]] = {}
        for x in s.execute(text("SELECT exception_id, kind, severity, detail, vendor, contract_id, amount_at_risk FROM v_spend_exceptions ORDER BY amount_at_risk DESC")).mappings():
            if SEV_RANK[x["severity"]] >= mn:
                groups.setdefault((x["vendor"], x["kind"]), []).append(dict(x))
        for (vendor, k), xs in groups.items():
            total = sum(float(x["amount_at_risk"]) for x in xs)
            sev = max((x["severity"] for x in xs), key=lambda v: SEV_RANK[v])
            what = k.replace("_", " ")
            title = f"Spend exception ({sev}): {what} — {vendor}" if len(xs) == 1 else f"{len(xs)} spend exceptions ({sev}): {what} — {vendor}, ${total:,.0f}"
            body = xs[0]["detail"] if len(xs) == 1 else xs[0]["detail"] + f" And {len(xs) - 1} more of the same kind."
            cids = {x["contract_id"] for x in xs}
            out.append(dict(dedupe=f"{r['key']}:{k}:{vendor}:{len(xs)}:{round(total)}", title=title, body=body, contract_id=cids.pop() if len(cids) == 1 else None, vendor=vendor, link="/spend", severity=sev))
    elif kind == "certificate":
        from app import certificates

        for x in certificates.listing(s, today)["certificates"]:
            if x["status"] == "expired" or (x["status"] == "expiring" and x["days_left"] <= int(p.get("days", 30))):
                when = f"expired {-x['days_left']} days ago" if x["status"] == "expired" else f"expires in {x['days_left']} days"
                out.append(dict(dedupe=f"{r['key']}:{x['id']}:{x['expiry_date']}", title=f"{x['name']} {when}: {x['vendor']}", body=f"Required by {x['contract_title'] or 'the contract'}. Ask the vendor for the renewed certificate.",
                                contract_id=x["contract_id"], vendor=x["vendor"], link="/certificates", severity="critical" if x["status"] == "expired" else "high"))
    elif kind == "vendor_tier":
        order = ["low", "medium", "high", "critical"]
        for x in s.execute(text("SELECT vendor, score, tier FROM vendor_scores")).mappings():
            if order.index(x["tier"]) >= order.index(p.get("min_tier", "high")):
                out.append(dict(dedupe=f"{r['key']}:{x['vendor']}:{x['tier']}", title=f"{x['vendor']} is {x['tier']} risk (score {float(x['score']):.0f})", body="See the vendor scorecard for the drivers.", vendor=x["vendor"], link=f"/vendors/{x['vendor']}", severity=x["tier"]))
    elif kind == "review_waiting":
        for x in s.execute(text("""SELECT c.id, c.title, c.vendor, (CURRENT_DATE - c.ingested_at::date) AS days FROM contracts c LEFT JOIN contract_reviews v ON v.contract_id = c.id
                                   WHERE c.status='draft' AND COALESCE(v.status,'pending') IN ('pending','in_review') AND (CURRENT_DATE - c.ingested_at::date) >= :d"""), {"d": int(p.get("days", 5))}).mappings():
            out.append(dict(dedupe=f"{r['key']}:{x['id']}", title=f"Draft waiting {x['days']} days for review: {x['title']}", body=f"{x['vendor']}", contract_id=x["id"], vendor=x["vendor"], link=f"/redline/{x['id']}"))
    elif kind == "approval_waiting":
        for x in s.execute(text("""SELECT s.id, s.label, s.approvers, a.id AS aid, c.id AS cid, c.title, c.vendor, (CURRENT_DATE - s.activated_at::date) AS d, COALESCE(r.remind_after_days, 3) AS lim
                                   FROM approval_steps s JOIN approvals a ON a.id=s.approval_id JOIN contracts c ON c.id=a.contract_id LEFT JOIN approval_rules r ON r.id=a.rule_id
                                   WHERE a.status='pending' AND s.status='pending'""")).mappings():
            if x["d"] >= x["lim"]:
                out.append(dict(dedupe=f"{r['key']}:{x['id']}:{x['d'] // max(x['lim'], 1)}", title=f"Approval waiting {x['d']} days ({x['label']}): {x['title']}", body=f"Approvers: {', '.join(x['approvers'])}",
                                contract_id=x["cid"], vendor=x["vendor"], link=f"/redline/{x['cid']}"))
    elif kind == "connector_error":
        for x in s.execute(text("SELECT id, name, last_message, last_sync_at FROM connectors WHERE last_status = 'error'")).mappings():
            out.append(dict(dedupe=f"{r['key']}:{x['id']}:{x['last_sync_at']}", title=f"Connector “{x['name']}” failed to sync", body=x["last_message"], link="/admin/connectors"))
    return out


def evaluate(today: date | None = None, deliver: bool = True) -> dict:
    """Raise every alert whose event has not been raised before; returns counts."""
    today = today or date.today()
    new = 0
    delivered_n = 0
    with SessionLocal() as s:
        ensure_defaults(s)
        rules = [dict(r) for r in s.execute(text("SELECT * FROM alert_rules WHERE enabled ORDER BY sort_order")).mappings()]
        fresh: list[tuple[dict, dict]] = []
        for r in rules:
            cands = _candidates(s, r, today)
            # an open alert whose cause is gone (the invoice was matched, the certificate renewed, the document re-read correctly) is closed, not left to pile up
            s.execute(text("UPDATE alerts SET status = 'resolved' WHERE rule_key = :r AND status = 'open' AND NOT (dedupe_key = ANY(:keep))"), {"r": r["key"], "keep": [c["dedupe"] for c in cands]})
            for c in cands:
                ins = s.execute(text("""INSERT INTO alerts (rule_key, dedupe_key, title, body, severity, link, contract_id, vendor) VALUES (:r,:d,:t,:b,:s,:l,:c,:v)
                                        ON CONFLICT (dedupe_key) DO NOTHING RETURNING id"""),
                                {"r": r["key"], "d": c["dedupe"], "t": c["title"], "b": c.get("body"), "s": c.get("severity") or r["severity"], "l": c.get("link"), "c": c.get("contract_id"), "v": c.get("vendor")}).scalar()
                if ins:
                    new += 1
                    fresh.append((r, {**c, "id": ins, "severity": c.get("severity") or r["severity"]}))
        s.commit()
        channels = [dict(r) for r in s.execute(text("SELECT * FROM alert_channels WHERE enabled")).mappings()]
    if deliver and fresh and channels:
        for r, a in fresh:
            res = {}
            for ch in channels:
                if "chat" not in r["channels"] and ch["kind"] in ("slack", "teams", "webhook") and "webhook" not in r["channels"]:
                    continue
                if "email" not in r["channels"] and ch["kind"] == "email":
                    continue
                if SEV_RANK.get(a["severity"], 1) < SEV_RANK.get(ch["min_severity"], 1):
                    continue
                res[ch["name"]] = send(ch, a)
                delivered_n += res[ch["name"]].get("ok", False)
            if res:
                with SessionLocal() as s:
                    s.execute(text("UPDATE alerts SET delivered=CAST(:d AS jsonb) WHERE id=:i"), {"d": json.dumps(res), "i": a["id"]})
                    s.commit()
    return {"new": new, "delivered": delivered_n}


# ------------------------------------------------------------------ delivery
def send(ch: dict, a: dict) -> dict:
    """Send one alert to one channel. Never raises: the result is recorded on the channel and the alert."""
    cfg, sec = ch["config"] or {}, crypto.decrypt(ch["secrets_enc"])
    t0 = time.time()
    try:
        if ch["kind"] == "email":
            msg = EmailMessage()
            msg["Subject"] = f"[ContractIQ · {a['severity']}] {a['title']}"
            msg["From"] = cfg.get("from") or "contractiq@localhost"
            msg["To"] = cfg.get("to") or ""
            base = cfg.get("app_url", "").rstrip("/")
            msg.set_content(f"{a['title']}\n\n{a.get('body') or ''}\n\n{base + a['link'] if a.get('link') and base else ''}")
            port = int(cfg.get("port") or 25)
            smtp_cls = smtplib.SMTP_SSL if cfg.get("ssl") else smtplib.SMTP
            with smtp_cls(cfg["host"], port, timeout=15) as sm:
                if cfg.get("starttls"):
                    sm.starttls()
                if sec.get("password"):
                    sm.login(cfg.get("username", ""), sec["password"])
                sm.send_message(msg)
        else:
            url = sec.get("url") or cfg.get("url")
            if not url:
                return {"ok": False, "error": "no webhook URL"}
            line = f"*{a['severity'].upper()}* {a['title']}" + (f"\n{a['body']}" if a.get("body") else "")
            payload = {"text": line} if ch["kind"] in ("slack", "teams") else {"title": a["title"], "severity": a["severity"], "body": a.get("body"), "link": a.get("link"), "vendor": a.get("vendor")}
            r = httpx.post(url, json=payload, timeout=15)
            if r.status_code >= 400:
                raise RuntimeError(f"HTTP {r.status_code}")
        out = {"ok": True, "ms": int((time.time() - t0) * 1000)}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"[:200]}
    with SessionLocal() as s:
        s.execute(text("UPDATE alert_channels SET last_status=:st, last_message=:m, last_sent_at=now() WHERE id=:i"), {"st": "ok" if out["ok"] else "error", "m": out.get("error") or "delivered", "i": ch["id"]})
        s.commit()
    return out
