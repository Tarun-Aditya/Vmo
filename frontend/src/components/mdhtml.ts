// Markdown <-> HTML for the contract editor. The documents use a small subset: page markers, # / ## headings,
// "**Label:** value" header lines, paragraphs, lists and **bold** / *italic*.
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function inline(s: string): string {
  let t = esc(s);
  t = t.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/(^|[^*])\*(?!\s)(.+?)\*(?!\*)/g, "$1<i>$2</i>");
  return t.replace(/\[([^\]\n]{2,120})\]/g, '<mark class="ph">[$1]</mark>');       // unresolved placeholders stand out
}

export function mdToHtml(md: string): string {
  const out: string[] = [];
  let list: "ul" | "ol" | null = null;
  const close = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of md.replace(/\r/g, "").split("\n")) {
    const line = raw.trimEnd();
    const pg = line.match(/^<!--\s*page:\s*(\d+)\s*-->$/);
    if (pg) { close(); if (pg[1] !== "1") out.push(`<div class="pagebreak" contenteditable="false" data-page="${pg[1]}">Page ${pg[1]}</div>`); else out.push(`<div class="pagebreak first" contenteditable="false" data-page="1"></div>`); continue; }
    if (!line.trim()) { close(); continue; }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) { close(); out.push(h[1].length === 1 ? `<h1>${inline(h[2])}</h1>` : `<h2>${inline(h[2])}</h2>`); continue; }
    const li = line.match(/^\s*(?:[-*•]\s+|(\d+)[.)]\s+)(.*)$/);
    if (li && !/^\*\*/.test(line)) {
      const kind = li[1] ? "ol" : "ul";
      if (list !== kind) { close(); out.push(`<${kind}>`); list = kind; }
      out.push(`<li>${inline(li[2])}</li>`); continue;
    }
    close();
    out.push(`<p>${inline(line)}</p>`);
  }
  close();
  return out.join("\n");
}

function walk(n: Node): string {
  if (n.nodeType === Node.TEXT_NODE) return (n.textContent ?? "").replace(/ /g, " ");
  if (n.nodeType !== Node.ELEMENT_NODE) return "";
  const e = n as HTMLElement;
  const kids = () => Array.from(e.childNodes).map(walk).join("");
  switch (e.tagName) {
    case "B": case "STRONG": { const k = kids(); return k.trim() ? `**${k}**` : k; }
    case "I": case "EM": { const k = kids(); return k.trim() ? `*${k}*` : k; }
    case "BR": return " ";
    case "DEL": return "";
    default: return kids();
  }
}

export function htmlToMd(root: HTMLElement): string {
  const blocks: { t: string; header: boolean }[] = [];
  const push = (t: string, header = false) => { if (t.trim()) blocks.push({ t: t.replace(/[ \t]+/g, " ").trim(), header }); };
  const visit = (el: Element) => {
    for (const c of Array.from(el.children)) {
      const tag = c.tagName;
      if (c.classList.contains("pagebreak")) { blocks.push({ t: `<!-- page: ${c.getAttribute("data-page")} -->`, header: false }); continue; }
      if (tag === "H1") push(`# ${walk(c)}`);
      else if (/^H[2-6]$/.test(tag)) push(`## ${walk(c)}`);
      else if (tag === "UL" || tag === "OL") Array.from(c.children).forEach((li, i) => push(`${tag === "OL" ? `${i + 1}.` : "-"} ${walk(li)}`));
      else if (tag === "P") { const t = walk(c); push(t, /^\*\*[^*]+:\*\*/.test(t)); }
      else if (tag === "DIV" && c.children.length && Array.from(c.children).some((k) => /^(P|H\d|UL|OL|DIV)$/.test(k.tagName))) visit(c);
      else push(walk(c), /^\*\*[^*]+:\*\*/.test(walk(c)));
    }
    // loose text directly under the root (typed into an empty editor)
    Array.from(el.childNodes).filter((n) => n.nodeType === Node.TEXT_NODE && (n.textContent ?? "").trim()).forEach((n) => push(n.textContent ?? ""));
  };
  visit(root);
  let md = "";
  blocks.forEach((b, i) => { md += (i === 0 ? "" : blocks[i - 1].header && b.header ? "\n" : "\n\n") + b.t; });
  return md.trim() + "\n";
}

export const wordCount = (md: string) => (md.replace(/<!--.*?-->/g, " ").match(/\S+/g) ?? []).length;
