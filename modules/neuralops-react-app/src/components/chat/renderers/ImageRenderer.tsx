import { useState } from "react";
import { Dialog, DialogContent } from "@/components/ui/dialog";

export function ImageRenderer({ content }: { content: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="block overflow-hidden rounded-md border border-border"
      >
        <img
          src={content}
          alt="attachment"
          className="max-h-[300px] w-auto object-contain"
        />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl bg-background p-2">
          <img src={content} alt="attachment full size" className="w-full" />
        </DialogContent>
      </Dialog>
    </>
  );
}
