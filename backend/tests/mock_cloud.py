"""Local stand-ins for the Google Drive v3 and Microsoft Graph APIs (and their token endpoints), so connectors are tested end to end
without credentials: same URL shapes, auth checks, paging, redirects on download, Google-native export."""
from __future__ import annotations

import socket
import threading
import time
from contextlib import contextmanager

import jwt
import uvicorn
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextmanager
def serve(factory):
    """factory(base_url) -> FastAPI app; yields the base URL of the running server."""
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(factory(base), host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        yield base
    finally:
        server.should_exit = True
        t.join(timeout=5)


# ------------------------------------------------------------------ Google Drive
class DriveState:
    def __init__(self, public_key_pem: str, client_email: str):
        self.pub, self.email = public_key_pem, client_email
        self.folders = {"root1": {"name": "Contracts", "parent": None}}          # id -> {name, parent}
        self.files: dict[str, dict] = {}                                          # id -> {name, parent, mime, content, modified, md5}
        self.tokens: set[str] = set()
        self.calls: list[str] = []

    def add_folder(self, fid, name, parent):
        self.folders[fid] = {"name": name, "parent": parent}

    def add_file(self, fid, name, parent, content: bytes, mime="application/octet-stream", modified="2026-11-01T10:00:00.000Z"):
        self.files[fid] = dict(name=name, parent=parent, mime=mime, content=content, modified=modified, md5=f"md5-{fid}-{modified}")


def google_app(st: DriveState, base: str) -> FastAPI:
    app = FastAPI()

    @app.post("/token")
    def token(grant_type: str = Form(...), assertion: str = Form(None), refresh_token: str = Form(None), client_id: str = Form(None), client_secret: str = Form(None)):
        if assertion:
            try:
                claims = jwt.decode(assertion, st.pub, algorithms=["RS256"], audience=f"{base}/token")
            except Exception as e:
                return JSONResponse({"error": "invalid_grant", "error_description": str(e)}, status_code=400)
            if claims["iss"] != st.email or "drive" not in claims["scope"]:
                return JSONResponse({"error": "invalid_grant", "error_description": "bad issuer or scope"}, status_code=400)
        elif refresh_token != "good-refresh" or client_secret != "good-secret":
            return JSONResponse({"error": "invalid_grant", "error_description": "bad refresh token"}, status_code=400)
        tok = f"tok-{len(st.tokens)}"
        st.tokens.add(tok)
        return {"access_token": tok, "expires_in": 3600}

    def auth(req: Request):
        if req.headers.get("authorization", "").removeprefix("Bearer ") not in st.tokens:
            raise HTTPException(401, "bad token")

    def meta(fid):
        if fid in st.folders:
            return {"id": fid, "name": st.folders[fid]["name"], "mimeType": "application/vnd.google-apps.folder"}
        f = st.files.get(fid)
        if not f:
            raise HTTPException(404, "not found")
        return {"id": fid, "name": f["name"], "mimeType": f["mime"], "size": str(len(f["content"])), "modifiedTime": f["modified"], "md5Checksum": f["md5"], "webViewLink": f"https://drive.google.com/file/d/{fid}/view"}

    @app.get("/drive/v3/files")
    def list_files(req: Request, q: str, pageToken: str | None = None, pageSize: int = 200):
        auth(req)
        st.calls.append("list")
        import re

        parent = re.search(r"'([^']+)' in parents", q).group(1)
        items = [meta(i) for i, f in st.folders.items() if f["parent"] == parent] + [meta(i) for i, f in st.files.items() if f["parent"] == parent]
        for it in items:
            if it["mimeType"] != "application/vnd.google-apps.folder" and "md5Checksum" in it and it["mimeType"].startswith("application/vnd.google-apps."):
                it.pop("md5Checksum", None)                         # native Google files have no checksum
        start = int(pageToken or 0)
        page = items[start:start + 2]                                # tiny pages to exercise paging
        out = {"files": page}
        if start + 2 < len(items):
            out["nextPageToken"] = str(start + 2)
        return out

    @app.get("/drive/v3/files/{fid}/export")
    def export(req: Request, fid: str, mimeType: str):
        auth(req)
        st.calls.append("export")
        f = st.files[fid]
        return Response(f["content"], media_type=mimeType)

    @app.get("/drive/v3/files/{fid}")
    def get_file(req: Request, fid: str, alt: str | None = None, fields: str | None = None):
        auth(req)
        if alt == "media":
            st.calls.append("download")
            return Response(st.files[fid]["content"], media_type="application/octet-stream")
        return meta(fid)

    return app


# ------------------------------------------------------------------ Microsoft Graph
class GraphState:
    def __init__(self, tenant: str, secret: str):
        self.tenant, self.secret = tenant, secret
        self.drives: dict[str, dict] = {}            # drive id -> {name, items: {id: {name, parent, folder?, content, modified, etag}}}
        self.users = {}                              # upn -> drive id
        self.sites = {}                              # 'host:/path' -> {id, drives: [drive ids]}
        self.tokens: set[str] = set()
        self.calls: list[str] = []

    def drive(self, did, name):
        self.drives[did] = {"name": name, "items": {}}

    def folder(self, did, iid, name, parent="root"):
        self.drives[did]["items"][iid] = dict(name=name, parent=parent, folder=True)

    def file(self, did, iid, name, parent, content: bytes, modified="2026-11-01T10:00:00Z"):
        self.drives[did]["items"][iid] = dict(name=name, parent=parent, content=content, modified=modified, etag=f'"{iid}-{modified}"')


def graph_app(st: GraphState, base: str) -> FastAPI:
    app = FastAPI()

    @app.post("/{tenant}/oauth2/v2.0/token")
    def token(tenant: str, grant_type: str = Form(...), client_id: str = Form(...), client_secret: str = Form(...), scope: str = Form(...)):
        if tenant != st.tenant or client_secret != st.secret or "graph.microsoft.com" not in scope:
            return JSONResponse({"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret provided."}, status_code=401)
        tok = f"gtok-{len(st.tokens)}"
        st.tokens.add(tok)
        return {"access_token": tok, "expires_in": 3600}

    def auth(req: Request):
        if req.headers.get("authorization", "").removeprefix("Bearer ") not in st.tokens:
            raise HTTPException(401, "InvalidAuthenticationToken")

    def item_json(did, iid, it):
        j = {"id": iid, "name": it["name"], "webUrl": f"https://contoso.sharepoint.com/{did}/{it['name']}", "lastModifiedDateTime": it.get("modified"), "size": len(it.get("content", b""))}
        if it.get("folder"):
            j["folder"] = {"childCount": 1}
        else:
            j["file"] = {"mimeType": "application/octet-stream"}
            j["eTag"] = it["etag"]
        return j

    def children(did, parent, skip):
        items = [(i, it) for i, it in st.drives[did]["items"].items() if it["parent"] == parent]
        page = items[skip:skip + 2]
        out = {"value": [item_json(did, i, it) for i, it in page]}
        if skip + 2 < len(items):
            out["@odata.nextLink"] = f"{base}/v1.0/drives/{did}/_page/{parent}/{skip + 2}"
        return out

    @app.get("/v1.0/users/{upn}/drive")
    def user_drive(req: Request, upn: str):
        auth(req)
        if upn not in st.users:
            raise HTTPException(404, "user not found")
        return {"id": st.users[upn]}

    @app.get("/v1.0/sites/{spec:path}")
    def sites(req: Request, spec: str):
        auth(req)
        if spec.endswith("/drives"):
            sid = spec[:-len("/drives")]
            site = next((s for s in st.sites.values() if s["id"] == sid), None)
            return {"value": [{"id": d, "name": st.drives[d]["name"]} for d in site["drives"]]}
        if spec not in st.sites:
            raise HTTPException(404, "site not found")
        return {"id": st.sites[spec]["id"]}

    @app.get("/v1.0/drives/{did}/root/children")
    def root_children(req: Request, did: str):
        auth(req)
        st.calls.append("root-children")
        return children(did, "root", 0)

    @app.get("/v1.0/drives/{did}/_page/{parent}/{skip}")
    def page(req: Request, did: str, parent: str, skip: int):
        auth(req)
        return children(did, parent, skip)

    @app.get("/v1.0/drives/{did}/items/{iid}/children")
    def item_children(req: Request, did: str, iid: str):
        auth(req)
        return children(did, iid, 0)

    @app.get("/v1.0/drives/{did}/items/{iid}/content")
    def content(req: Request, did: str, iid: str):
        auth(req)
        st.calls.append("download")
        return RedirectResponse(f"{base}/dl/{did}/{iid}")

    @app.get("/dl/{did}/{iid}")
    def dl(req: Request, did: str, iid: str):
        if req.headers.get("authorization"):
            raise HTTPException(400, "the pre-authenticated URL must not receive the bearer token")
        return Response(st.drives[did]["items"][iid]["content"])

    @app.get("/v1.0/drives/{did}/{rest:path}")
    def path_children(req: Request, did: str, rest: str):
        auth(req)
        m = rest.split(":")
        if len(m) >= 2 and rest.endswith(":/children"):
            from urllib.parse import unquote

            names = [x for x in unquote(m[1]).strip("/").split("/") if x]
            parent = "root"
            for n in names:
                nxt = next((i for i, it in st.drives[did]["items"].items() if it["parent"] == parent and it["name"] == n and it.get("folder")), None)
                if not nxt:
                    raise HTTPException(404, "itemNotFound")
                parent = nxt
            return children(did, parent, 0)
        raise HTTPException(404, rest)

    return app
