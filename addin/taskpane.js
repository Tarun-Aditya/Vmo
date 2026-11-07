/* ContractIQ task pane: threads of one draft, insert suggested wording, comment on the selection, resolve. Talks to the same REST API as the web app. */
const $ = (id) => document.getElementById(id);
const store = (k, v) => { try { if (v === undefined) return localStorage.getItem("ciq_" + k) || ""; localStorage.setItem("ciq_" + k, v); } catch (e) { return ""; } };
async function api(path, init = {}) {
  const base = $("api").value.replace(/\/$/, ""), tok = $("tok").value;
  const r = await fetch(base + path, { ...init, headers: { "Content-Type": "application/json", ...(tok ? { Authorization: "Bearer " + tok } : {}) } });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.status);
  return r.json();
}
const say = (t) => { $("msg").textContent = t; };
async function load() {
  ["api", "tok", "doc"].forEach((k) => store(k, $(k).value));
  try {
    const d = await api(`/api/documents/${$("doc").value}/threads`);
    $("list").innerHTML = "";
    say(`${d.open} open comment(s)`);
    for (const t of d.threads) {
      const el = document.createElement("div"); el.className = "t " + t.status;
      el.innerHTML = (t.source === "ai" ? '<span class="ai">ContractIQ</span> ' : "") + (t.anchor_text ? `<div class="q">“${t.anchor_text.slice(0, 120)}”</div>` : "") +
        t.comments.map((c) => `<div><b>${c.author}</b>: ${c.body.replace(/</g, "&lt;")}</div>`).join("");
      const sug = (t.comments[0]?.body.match(/Suggested wording: ([\s\S]*)$/) || [])[1];
      if (sug) { const b = document.createElement("button"); b.textContent = "Insert suggested wording"; b.onclick = () => insert(sug.trim()); el.appendChild(b); }
      const r = document.createElement("button"); r.textContent = t.status === "open" ? "Resolve" : "Reopen";
      r.onclick = async () => { await api(`/api/threads/${t.id}`, { method: "PUT", body: JSON.stringify({ status: t.status === "open" ? "resolved" : "open" }) }); load(); }; el.appendChild(r);
      $("list").appendChild(el);
    }
  } catch (e) { say("Could not load: " + e.message); }
}
function insert(text) { Word.run(async (ctx) => { ctx.document.getSelection().insertText(text, "Replace"); await ctx.sync(); say("Inserted."); }).catch((e) => say(e.message)); }
function comment() {
  Word.run(async (ctx) => {
    const sel = ctx.document.getSelection(); sel.load("text"); await ctx.sync();
    await api(`/api/documents/${$("doc").value}/threads`, { method: "POST", body: JSON.stringify({ body: $("body").value, anchor_text: sel.text.slice(0, 300) || null }) });
    $("body").value = ""; load();
  }).catch((e) => say(e.message));
}
Office.onReady(() => { ["api", "tok", "doc"].forEach((k) => ($(k).value = store(k))); $("load").onclick = load; $("add").onclick = comment; if ($("api").value && $("doc").value) load(); });
