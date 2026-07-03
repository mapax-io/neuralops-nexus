import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

// JSON Schema property definition
type JsonSchemaProp = {
  type?: string;
  title?: string;
  enum?: string[];
};

// JSON Schema format (what the AI sends)
type JsonSchema = {
  title?: string;
  type?: string;
  properties?: Record<string, JsonSchemaProp>;
  required?: string[];
};

function deriveFieldType(prop: JsonSchemaProp): "text" | "number" | "select" | "checkbox" {
  if (prop.enum && prop.enum.length > 0) return "select";
  if (prop.type === "boolean") return "checkbox";
  if (prop.type === "number" || prop.type === "integer") return "number";
  return "text";
}

export function FormRenderer({
  content,
  metadata,
}: {
  content: string;
  metadata?: Record<string, unknown>;
}) {
  const schema = (metadata?.schema as JsonSchema) ?? {};
  const properties = schema.properties ?? {};
  const fieldKeys = Object.keys(properties);

  const [values, setValues] = useState<Record<string, unknown>>({});
  const [submitted, setSubmitted] = useState(false);

  function update(name: string, val: unknown) {
    setValues((v) => ({ ...v, [name]: val }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitted(true);
  }

  if (fieldKeys.length === 0) {
    return (
      <div className="rounded-md border border-border bg-card p-4 text-sm text-muted-foreground">
        {content || "Form schema is empty."}
      </div>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 rounded-md border border-border bg-card p-4"
    >
      {schema.title && (
        <div className="text-sm font-medium text-foreground">{schema.title}</div>
      )}
      {content && (
        <div className="text-sm text-muted-foreground">{content}</div>
      )}
      {fieldKeys.map((key) => {
        const prop = properties[key];
        const fieldType = deriveFieldType(prop);
        const label = prop.title ?? key;

        return (
          <div key={key} className="space-y-1.5">
            <Label htmlFor={key}>{label}</Label>
            {fieldType === "select" ? (
              <Select
                onValueChange={(v) => update(key, v)}
                value={(values[key] as string) ?? ""}
              >
                <SelectTrigger id={key}>
                  <SelectValue placeholder="Select..." />
                </SelectTrigger>
                <SelectContent>
                  {prop.enum?.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            ) : fieldType === "checkbox" ? (
              <div className="flex items-center gap-2">
                <Checkbox
                  id={key}
                  checked={!!values[key]}
                  onCheckedChange={(v) => update(key, !!v)}
                />
                <label htmlFor={key} className="text-sm text-foreground cursor-pointer">
                  {label}
                </label>
              </div>
            ) : (
              <Input
                id={key}
                type={fieldType}
                value={(values[key] as string) ?? ""}
                onChange={(e) => update(key, e.target.value)}
              />
            )}
          </div>
        );
      })}
      <Button type="submit" size="sm" disabled={submitted}>
        {submitted ? "Sent ✓" : "Send Response"}
      </Button>
    </form>
  );
}
