import { X } from "@phosphor-icons/react";
import { useId, useRef, useState } from "react";
import "./KeywordTags.css";

type Props = {
  label: string;
  value: string[];
  onChange: (value: string[]) => void;
  disabled?: boolean;
  hint?: string;
};

export function KeywordTags({ label, value, onChange, disabled = false, hint }: Props) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const composing = useRef(false);
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState<number | null>(null);
  const [error, setError] = useState("");

  function commit() {
    const word = draft.trim();
    if (!word || composing.current) return;
    if (value.some((item, index) => index !== editing && item.toLocaleLowerCase() === word.toLocaleLowerCase())) {
      setError("这个排除词已经存在");
      return;
    }
    if (editing === null && value.length >= 100) { setError("最多添加 100 个排除词"); return; }
    onChange(editing === null ? [...value, word] : value.map((item, index) => index === editing ? word : item));
    setDraft(""); setEditing(null); setError("");
  }

  function remove(index: number) {
    onChange(value.filter((_, item) => item !== index));
    if (editing === index) { setEditing(null); setDraft(""); }
    else if (editing !== null && index < editing) setEditing(editing - 1);
    setError("");
  }

  return <div className="keyword-field">
    <label htmlFor={id}>{label}</label>
    <div className="keyword-tags" role="group" aria-label={`${label}标签`}>
      {value.map((word, index) => <span className={`keyword-tag${editing === index ? " editing" : ""}`} key={`${index}-${word}`}>
        <button type="button" className="keyword-tag-edit" aria-label={`编辑排除词 ${word}`} title="点击修改" disabled={disabled} onMouseDown={(e) => e.preventDefault()} onClick={() => { setDraft(word); setEditing(index); setError(""); input.current?.focus(); }}>{word}</button>
        <button type="button" className="keyword-tag-remove" aria-label={`删除排除词 ${word}`} disabled={disabled} onMouseDown={(e) => e.preventDefault()} onClick={() => remove(index)}><X size={12} /></button>
      </span>)}
      <input id={id} ref={input} className="keyword-tags-input" value={draft} disabled={disabled} maxLength={200} placeholder={editing === null ? "输入后按回车添加" : "修改后按回车确认"} aria-describedby={`${id}-hint`} aria-invalid={Boolean(error)}
        onChange={(event) => { setDraft(event.target.value); setError(""); }} onBlur={commit}
        onCompositionStart={() => { composing.current = true; }} onCompositionEnd={() => { composing.current = false; }}
        onKeyDown={(event) => {
          if (event.nativeEvent.isComposing || composing.current || event.keyCode === 229) return;
          if (event.key === "Enter") { event.preventDefault(); event.stopPropagation(); commit(); }
          if (event.key === "Escape" && (draft || editing !== null)) { event.preventDefault(); event.stopPropagation(); setDraft(""); setEditing(null); setError(""); }
        }} />
    </div>
    <p id={`${id}-hint`} className="keyword-tags-hint">{hint ?? "回车添加，点击标签修改，× 删除。"}</p>
    {error ? <p role="alert" className="keyword-tags-error">{error}</p> : null}
  </div>;
}
