"use client";

import { useRef, useState } from "react";
import { X } from "lucide-react";
import { MANAGER_OPT_OUT } from "@/components/ui/field";
import { cn } from "@/lib/utils";

// A list of short tokens (globs, names) edited as chips. Enter or a comma adds
// what was typed; a pasted list becomes chips, one per line or comma (read
// from the paste itself — a single-line input drops the newlines before
// onChange sees them); Backspace on an empty draft removes the last chip; a
// draft still pending on blur is added, so an entry typed right before Save
// is never lost. Enter is always consumed — inside a dialog form it adds a
// chip, it never submits.
const SEPARATOR = /[\n,]/;

export function ChipInput({ id, label, value, onChange, placeholder, className }: {
  id: string;
  // The group's accessible name; pair with a <Label htmlFor={id}> for the text field.
  label: string;
  value: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  className?: string;
}) {
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const add = (parts: string[]) => {
    const next = [...value];
    for (const part of parts) {
      const t = part.trim();
      if (t && !next.includes(t)) next.push(t);
    }
    if (next.length !== value.length) onChange(next);
  };
  const edit = (text: string) => {
    if (!SEPARATOR.test(text)) {
      setDraft(text.trimStart()); // a token never starts with a space; typing one after a comma is common
      return;
    }
    const parts = text.split(SEPARATOR);
    const tail = parts.pop() ?? "";
    add(parts);
    setDraft(tail.trimStart());
  };
  const commit = () => {
    add([draft]);
    setDraft("");
  };

  return (
    <div
      role="group"
      aria-label={label}
      // The whole box reads as the field: a press on its padding or on a chip's
      // text lands the caret in the text input instead of blurring it.
      onPointerDown={(e) => {
        if (e.target === inputRef.current || (e.target as Element).closest("button")) return;
        e.preventDefault();
        inputRef.current?.focus();
      }}
      className={cn(
        "flex min-h-16 w-full cursor-text flex-wrap content-start items-center gap-1.5 rounded-[8px] border border-line bg-surface px-2 py-1.5 transition-[border-color] focus-within:border-accent",
        className,
      )}
    >
      {value.map((chip, i) => (
        <span key={`${i}-${chip}`} className="inline-flex items-center gap-0.5 rounded-full border border-line bg-surface2 py-0.5 pl-2 pr-0.5 font-mono text-[11.5px] text-ink">
          {chip}
          <button
            type="button"
            aria-label={`Remove ${chip}`}
            onClick={() => {
              onChange(value.filter((_, j) => j !== i));
              inputRef.current?.focus(); // the button under the pointer is gone; keep typing where the list is edited
            }}
            className="cursor-pointer rounded-full p-0.5 text-ink2 transition-colors hover:bg-line hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
          >
            <X size={11} strokeWidth={2.5} />
          </button>
        </span>
      ))}
      <input
        ref={inputRef}
        id={id}
        value={draft}
        onChange={(e) => edit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          } else if (e.key === "Backspace" && draft === "" && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={() => {
          if (draft) commit();
        }}
        onPaste={(e) => {
          const text = e.clipboardData.getData("text");
          if (!SEPARATOR.test(text)) return; // one token: lands in the draft as typed text would
          e.preventDefault();
          add(text.split(SEPARATOR));
        }}
        placeholder={value.length ? undefined : placeholder}
        spellCheck={false}
        autoComplete="off"
        {...MANAGER_OPT_OUT}
        className="h-6 min-w-[10ch] flex-1 bg-transparent font-mono text-[12.5px] text-ink outline-none placeholder:text-ink2/60"
      />
    </div>
  );
}
