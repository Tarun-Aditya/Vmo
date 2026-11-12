import { useEffect, useRef } from "react";
import { htmlToMd, mdToHtml, wordCount } from "./mdhtml";

type Props = { value: string; onChange: (md: string) => void; readOnly?: boolean; title?: string; status?: string; right?: React.ReactNode; height?: string };

const cmd = (c: string, v?: string) => { document.execCommand(c, false, v); };

function Tool({ label, title, onClick, wide }: { label: React.ReactNode; title: string; onClick: () => void; wide?: boolean }) {
  return <button type="button" title={title} aria-label={title} onMouseDown={(e) => { e.preventDefault(); onClick(); }}
    className={`${wide ? "px-2" : "w-7"} h-7 rounded text-sm text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-600`}>{label}</button>;
}

/** A Word / Google-Docs-style page: toolbar, paper sheet, page breaks, highlighted placeholders. Stores Markdown. */
export default function DocEditor({ value, onChange, readOnly, title, status, right, height = "70vh" }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const last = useRef<string>("");
  useEffect(() => {
    if (ref.current && value !== last.current) { ref.current.innerHTML = mdToHtml(value); last.current = value; }
  }, [value]);
  const emit = () => { if (!ref.current) return; const md = htmlToMd(ref.current); last.current = md; onChange(md); };
  return (
    <div className="overflow-hidden rounded-lg border border-slate-300 bg-slate-200 dark:border-slate-600 dark:bg-slate-900">
      <div className="flex flex-wrap items-center gap-2 border-b border-slate-300 bg-white px-3 py-1.5 dark:border-slate-600 dark:bg-slate-800">
        <span className="mr-2 flex items-center gap-2 text-sm font-medium"><span className="grid h-6 w-6 place-items-center rounded bg-blue-600 text-xs font-bold text-white" aria-hidden>W</span><span className="max-w-[24rem] truncate">{title ?? "Document"}</span></span>
        {!readOnly && (
          <div role="toolbar" aria-label="Formatting" className="flex flex-wrap items-center gap-0.5">
            <Tool label="↶" title="Undo" onClick={() => cmd("undo")} /><Tool label="↷" title="Redo" onClick={() => cmd("redo")} />
            <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />
            <Tool wide label="Title" title="Title" onClick={() => cmd("formatBlock", "H1")} /><Tool wide label="Heading" title="Heading" onClick={() => cmd("formatBlock", "H2")} /><Tool wide label="Text" title="Normal text" onClick={() => cmd("formatBlock", "P")} />
            <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />
            <Tool label={<b>B</b>} title="Bold" onClick={() => cmd("bold")} /><Tool label={<i>I</i>} title="Italic" onClick={() => cmd("italic")} />
            <Tool label={<u>U</u>} title="Underline" onClick={() => cmd("underline")} />
            <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />
            <Tool wide label="Left" title="Align left" onClick={() => cmd("justifyLeft")} /><Tool wide label="Centre" title="Align centre" onClick={() => cmd("justifyCenter")} /><Tool wide label="Right" title="Align right" onClick={() => cmd("justifyRight")} /><Tool wide label="Justify" title="Justify" onClick={() => cmd("justifyFull")} />
            <span className="mx-1 h-5 w-px bg-slate-300 dark:bg-slate-600" />
            <Tool label="•" title="Bulleted list" onClick={() => cmd("insertUnorderedList")} /><Tool label="1." title="Numbered list" onClick={() => cmd("insertOrderedList")} /><Tool wide label="Indent" title="Indent" onClick={() => cmd("indent")} />
          </div>)}
        <span className="ml-auto flex items-center gap-3 text-xs text-slate-500">{status && <span>{status}</span>}<span>{wordCount(value).toLocaleString()} words</span>{right}</span>
      </div>
      <div className="overflow-auto px-2 py-6 sm:px-6" style={{ maxHeight: height, minHeight: "24rem" }}>
        <div ref={ref} className="docpage mx-auto" role="textbox" aria-multiline="true" aria-label="Contract text" contentEditable={!readOnly} suppressContentEditableWarning spellCheck
          onInput={emit} onBlur={emit} />
      </div>
      <div className="flex flex-wrap items-center gap-4 border-t border-slate-300 bg-white px-3 py-1 text-xs text-slate-500 dark:border-slate-600 dark:bg-slate-800" role="status">
        <span>{wordCount(value).toLocaleString()} words</span>{readOnly ? <span>Read only</span> : <span>Editing</span>}<span className="ml-auto">{status}</span>
      </div>
    </div>
  );
}
