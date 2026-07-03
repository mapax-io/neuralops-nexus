import { useEffect, useRef } from "react";
import { MessageItem } from "./MessageItem";
import type { ChatMessage } from "./types";

const MOCK_MESSAGES: ChatMessage[] = [
  {
    id: "1",
    type: "text",
    content: "Hello! I'm Nova. How can I help you with this project today?",
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 600000).toISOString(),
  },
  {
    id: "2",
    type: "text",
    content: "Can you write a Python function to calculate fibonacci numbers?",
    sender: { id: "u1", name: "Noaman", type: "human", avatar: null },
    timestamp: new Date(Date.now() - 540000).toISOString(),
  },
  {
    id: "3",
    type: "code",
    content: `def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Example usage
for i in range(10):
    print(f"fibonacci({i}) = {fibonacci(i)}")`,
    language: "python",
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 480000).toISOString(),
  },
  {
    id: "4",
    type: "terminal",
    content:
      "$ python fibonacci.py\nfibonacci(0) = 0\nfibonacci(1) = 1\nfibonacci(2) = 1\nfibonacci(3) = 2\nfibonacci(4) = 3\nfibonacci(5) = 5",
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 360000).toISOString(),
  },
  {
    id: "5",
    type: "chart",
    content: "Fibonacci sequence growth",
    metadata: {
      chartType: "bar",
      data: [
        { name: "n=1", value: 1 },
        { name: "n=2", value: 1 },
        { name: "n=3", value: 2 },
        { name: "n=4", value: 3 },
        { name: "n=5", value: 5 },
        { name: "n=6", value: 8 },
        { name: "n=7", value: 13 },
      ],
    },
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 240000).toISOString(),
  },
  {
    id: "6",
    type: "form",
    content: "Please fill in the deployment configuration:",
    metadata: {
      schema: {
        title: "Deployment Config",
        type: "object",
        properties: {
          environment: {
            type: "string",
            title: "Environment",
            enum: ["development", "staging", "production"],
          },
          replicas: {
            type: "number",
            title: "Number of Replicas",
          },
          enable_monitoring: {
            type: "boolean",
            title: "Enable Monitoring",
          },
        },
        required: ["environment", "replicas"],
      },
    },
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 120000).toISOString(),
  },
  {
    id: "7",
    type: "web",
    content: "https://example.com",
    sender: { id: "p1", name: "Nova", type: "persona", avatar: null },
    timestamp: new Date(Date.now() - 60000).toISOString(),
  },
];

export function MessageList({ messages }: { messages?: ChatMessage[] }) {
  const list = messages ?? MOCK_MESSAGES;
  // Ref on the scroll container itself — we scroll it directly via scrollTop
  // so only the message list scrolls, not the whole page
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [list.length]);

  if (list.length === 0) {
    return (
      <div className="flex h-full items-center justify-center px-6 text-center">
        <p className="text-sm text-muted-foreground">
          No messages yet. Start the conversation below.
        </p>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto py-4">
      {list.map((m) => (
        <MessageItem key={m.id} message={m} />
      ))}
    </div>
  );
}
