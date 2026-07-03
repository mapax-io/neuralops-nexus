import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Datum = { name: string; value: number };

export function ChartRenderer({
  content,
  metadata,
}: {
  content: string;
  metadata?: Record<string, unknown>;
}) {
  const chartType = (metadata?.chartType as string) ?? "bar";
  const data = (metadata?.data as Datum[]) ?? [];

  const primary = "var(--primary)";

  return (
    <div className="rounded-md border border-border bg-card p-4">
      <div className="mb-2 text-sm font-medium text-foreground">{content}</div>
      <div className="h-[260px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          {chartType === "line" ? (
            <LineChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="name" stroke="var(--foreground-muted)" fontSize={12} />
              <YAxis stroke="var(--foreground-muted)" fontSize={12} />
              <Tooltip />
              <Line type="monotone" dataKey="value" stroke={primary} strokeWidth={2} />
            </LineChart>
          ) : chartType === "pie" ? (
            <PieChart>
              <Tooltip />
              <Pie data={data} dataKey="value" nameKey="name" outerRadius={90}>
                {data.map((_, i) => (
                  <Cell key={i} fill={i % 2 === 0 ? primary : "var(--accent-foreground)"} />
                ))}
              </Pie>
            </PieChart>
          ) : (
            <BarChart data={data}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
              <XAxis dataKey="name" stroke="var(--foreground-muted)" fontSize={12} />
              <YAxis stroke="var(--foreground-muted)" fontSize={12} />
              <Tooltip />
              <Bar dataKey="value" fill={primary} radius={[4, 4, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}
