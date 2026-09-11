import Link from "next/link";
import {
  ArrowRight,
  Boxes,
  Brain,
  Check,
  Compass,
  Globe,
  LayoutDashboard,
  Library,
  Network,
  Plug,
  ShieldCheck,
  Sparkles,
  Users,
  Zap,
} from "lucide-react";
import { Constellation } from "@/components/brand/constellation";
import { Nebula } from "@/components/brand/nebula";
import { Wordmark } from "@/components/brand/wordmark";
import { ChatDemo } from "@/components/landing/chat-demo";
import { GithubNavLink, GithubStatsCard } from "@/components/landing/github-stats";
import { Parallax } from "@/components/landing/parallax";
import { Reveal } from "@/components/landing/reveal";
import { SignedInRedirect } from "@/components/auth/signed-in-redirect";
import { ThemeToggle } from "@/components/theme-toggle";

type IconType = typeof Users;

const PRIMITIVES: { icon: IconType; title: string; body: string }[] = [
  { icon: Users, title: "Human + AI Team Collaboration", body: "Humans, AI personas, and autonomous agents work together in the same workspace — solving problems collectively instead of in isolated chats." },
  { icon: Brain, title: "Shared Context", body: "Every project has its own structured knowledge base. All participants operate on the same single source of truth — no scattered context." },
  { icon: Plug, title: "Model-Agnostic Intelligence", body: "Works with any AI model — hosted providers or local models via Ollama. No vendor lock-in, full flexibility to switch or combine." },
  { icon: Boxes, title: "Future-Ready AI Framework", body: "A flexible orchestration layer designed to adapt to new models, emerging tools, and changing workflows — built for the long term." },
  { icon: ShieldCheck, title: "Data Sovereignty & Deployment", body: "Run locally, in the cloud, or fully self-hosted on your own infrastructure. You decide where data lives — secure by design." },
  { icon: Zap, title: "Action-Oriented AI (MCP)", body: "Through the Model Context Protocol, agents interact with real databases, APIs, codebases, and infrastructure — they act, not just answer." },
  { icon: LayoutDashboard, title: "Dynamic Workspace", body: "Beyond chat — forms, charts, code execution, terminal commands, and structured outputs. A complete environment, not a messaging tool." },
  { icon: Network, title: "Multi-Agent Orchestration", body: "Multiple AI agents divide tasks, collaborate, and contribute specialized expertise — coordinated workflows instead of isolated calls." },
  { icon: Library, title: "Structured Knowledge Management", body: "Knowledge organized per project and reusable, with selective @context invocation for precise, controlled AI usage." },
  { icon: Globe, title: "Open-Source Core & Ecosystem", body: "Built on the COSS model — an open core extended by a community of agents, integrations, and plugins. Transparent and scalable." },
];

const STEPS = [
  { n: "01", title: "Connect your server", body: "Sign in once, then point the app at any NeuralOps server you belong to — office, home lab, or a client's deployment. Every conversation stays on its server." },
  { n: "02", title: "Build a persona", body: "Register a model with your own key, hand it tools through an MCP server, and give it a name and a role — or start from a template like Project Manager or Developer." },
  { n: "03", title: "Mention it in chat", body: "Type @Layla summarize the quarter @chart in any topic. The answer streams in live — as text, a chart, a table, a diagram, a form, or a working page." },
];

const COMPARISON: { category: string; a: string; b: string; nexus: string }[] = [
  { category: "Core Role", a: "AI assistant platform for teams", b: "Open-source multi-model AI chat platform", nexus: "AI workforce orchestration platform" },
  { category: "Interaction Model", a: "1 user ↔ 1 AI (shared workspace)", b: "Multi-user chat with AI access", nexus: "Multi-human + multi-agent collaboration in same workspace" },
  { category: "AI Coordination", a: "Limited / experimental agents", b: "Basic agents & tool usage", nexus: "Native multi-agent orchestration (agents collaborate & divide tasks)" },
  { category: "Model Support", a: "Vendor-specific", b: "Multi-model (hosted, local APIs)", nexus: "Fully model-agnostic (cloud + local + hybrid)" },
  { category: "Deployment", a: "Cloud-first", b: "Self-hosted friendly", nexus: "Local, cloud, or fully enterprise self-hosted" },
  { category: "Data Control", a: "Limited control", b: "High control (self-hosted)", nexus: "Full control (data + model + infra flexibility)" },
  { category: "Knowledge Handling", a: "Files + context windows", b: "Chat memory + files", nexus: "Structured knowledge bases + controlled @context" },
  { category: "Execution Capability", a: "Limited tools", b: "MCP + tools + code execution", nexus: "MCP-first architecture for real system workflows" },
  { category: "Workspace Type", a: "Chat + shared projects", b: "Chat + tools interface", nexus: "Dynamic workspace (chat, forms, workflows, execution layer)" },
  { category: "Extensibility", a: "Custom assistants (limited scope)", b: "Open-source + plugins", nexus: "Open-source + deeply extensible orchestration ecosystem" },
  { category: "Ecosystem", a: "Vendor-driven", b: "Open-source community", nexus: "Community + modular + platform ecosystem" },
  { category: "Strategic Position", a: "Productivity layer", b: "Open AI interface layer", nexus: "Coordination layer for AI-driven organizations" },
];

const MVP_CAPABILITIES: { icon: IconType; title: string; body: string }[] = [
  { icon: Compass, title: "Architecture Designed", body: "System architecture validated and ready for scale" },
  { icon: Users, title: "Human + AI Collaboration", body: "Shared workspace for seamless human-AI interaction" },
  { icon: Network, title: "Multi-Agent System", body: "Multiple agents working together within projects" },
  { icon: Library, title: "Knowledge Base", body: "Knowledge integration for context awareness" },
  { icon: Plug, title: "Model-Agnostic", body: "Connect any AI model via LiteLLM integration" },
];

// Tiers describe what each will offer — no prices or checkout while the model
// is still being finalized. Community is real today (AGPL self-host); the rest
// are on the roadmap and marked "Coming soon" instead of a call to action.
const PLANS: { name: string; tagline: string; soon?: boolean; highlight?: boolean; features: string[] }[] = [
  {
    name: "Community",
    tagline: "Self-hosted, free forever",
    highlight: true,
    features: [
      "The full platform under AGPL-3.0",
      "All primitives — personas, agents, MCP tools",
      "Bring your own models & keys (cloud or local)",
      "Unlimited projects, channels, and members",
      "Runs on your own infrastructure",
    ],
  },
  {
    name: "Cloud",
    tagline: "Managed hosting",
    soon: true,
    features: [
      "Everything in Community, fully managed",
      "Automatic updates, backups, and scaling",
      "Team management & single sign-on",
      "Usage insights",
      "Priority support",
    ],
  },
  {
    name: "Enterprise",
    tagline: "For regulated & large teams",
    soon: true,
    features: [
      "Private or air-gapped deployment",
      "SLAs & dedicated support",
      "Advanced roles & audit logs",
      "Security & compliance reviews",
      "Onboarding & solution engineering",
    ],
  },
];

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-bg text-ink">
      <SignedInRedirect />
      <header className="fixed inset-x-0 top-0 z-40 border-b border-line/60 bg-bg/70 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-7 px-6">
          <Link href="/" aria-label="NeuralOps Nexus home"><Wordmark className="text-[17px]" /></Link>
          <nav className="ml-2 hidden gap-6 text-[13.5px] text-ink2 md:flex">
            <a className="hover:text-ink" href="#how">How it works</a>
            <a className="hover:text-ink" href="#platform">Platform</a>
            <a className="hover:text-ink" href="#compare">Compare</a>
            <a className="hover:text-ink" href="#plans">Plans</a>
            <a className="hover:text-ink" href="#status">Status</a>
          </nav>
          <div className="flex-1" />
          <GithubNavLink />
          <ThemeToggle />
          <Link href="/login" className="hidden h-9 items-center rounded-[10px] bg-accent px-4 text-[13.5px] font-semibold text-accent-ink shadow-[0_8px_24px_-10px_var(--accent-deep)] hover:brightness-110 sm:inline-flex">
            Open the app
          </Link>
        </div>
      </header>

      {/* ── Hero ── */}
      <section className="relative overflow-hidden px-6 pb-24 pt-36">
        <Parallax speed={-0.08} className="absolute inset-0"><Nebula /></Parallax>
        <Parallax speed={-0.14} className="absolute inset-0"><Constellation /></Parallax>
        <div className="relative mx-auto grid max-w-6xl items-center gap-14 lg:grid-cols-[1.05fr_.95fr]">
          <div>
            <span className="nx-rise mb-5 inline-flex items-center gap-2 rounded-full border border-accent/30 bg-accent/10 px-3.5 py-1 font-mono text-[11px] font-semibold uppercase tracking-[.14em] text-accent">
              <Sparkles size={12} strokeWidth={2} /> Open source · Now in private beta
            </span>
            <h1 className="nx-rise font-display text-[clamp(36px,5.2vw,60px)] font-extrabold leading-[1.08]" style={{ animationDelay: "90ms" }}>
              Orchestrating the<br />
              <em className="nx-gradient bg-gradient-to-r from-accent via-live to-accent bg-clip-text not-italic text-transparent">Human–AI</em> digital workforce.
            </h1>
            <p className="nx-rise mt-5 max-w-xl text-lg text-ink2" style={{ animationDelay: "180ms" }}>
              NeuralOps Nexus is the operating system for AI-driven teams — a unified workspace where humans, AI
              personas, and autonomous agents collaborate on complex problems through a single shared reality.
              One platform. One source of truth.
            </p>
            <div className="nx-rise mt-8 flex flex-wrap gap-3" style={{ animationDelay: "270ms" }}>
              <Link href="/login" className="inline-flex h-11 items-center gap-2 rounded-[10px] bg-accent px-6 text-[15px] font-semibold text-accent-ink shadow-[0_8px_24px_-10px_var(--accent-deep)] transition-[filter] hover:brightness-110">
                Open the app <ArrowRight size={16} strokeWidth={2} />
              </Link>
              <a href="#how" className="inline-flex h-11 items-center rounded-[10px] border border-line bg-surface/80 px-6 text-[15px] font-semibold backdrop-blur transition-colors hover:border-accent">
                See how it works
              </a>
            </div>
            <p className="nx-rise mt-5 text-[12.5px] text-ink2" style={{ animationDelay: "360ms" }}>
              Model-agnostic — <Chip>anthropic/…</Chip> <Chip>openai/…</Chip> <Chip>ollama/…</Chip> — and any MCP tool server.
            </p>
          </div>
          <Parallax speed={0.05}>
            <div className="nx-rise" style={{ animationDelay: "200ms" }}><ChatDemo /></div>
          </Parallax>
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how" className="border-t border-line bg-bg2 px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <Eyebrow>How it works</Eyebrow>
            <h2 className="font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">From zero to an AI teammate in three moves</h2>
          </Reveal>
          <div className="mt-11 grid gap-4 md:grid-cols-3">
            {STEPS.map((s) => (
              <Reveal key={s.n}>
                <div className="group h-full rounded-2xl border border-line bg-surface p-6 transition-[border-color,box-shadow] hover:border-accent/50 hover:shadow-[0_18px_50px_-28px_var(--accent-deep)]">
                  <p className="mb-3 font-mono text-xs text-accent">{s.n}</p>
                  <h3 className="mb-2 font-display text-[17.5px] font-bold">{s.title}</h3>
                  <p className="text-sm text-ink2">{s.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Core features ── */}
      <section id="platform" className="relative overflow-hidden px-6 py-24">
        <Parallax speed={-0.06} className="absolute inset-0"><Nebula dim /></Parallax>
        <div className="relative mx-auto max-w-6xl">
          <Reveal>
            <Eyebrow>Core features</Eyebrow>
            <h2 className="font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">One platform. Ten primitives for the AI workforce.</h2>
            <p className="mt-4 max-w-2xl text-ink2">Everything you need to coordinate humans, agents, knowledge, and execution — in a single, model-agnostic system.</p>
          </Reveal>
          <div className="mt-11 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {PRIMITIVES.map((f) => (
              <Reveal key={f.title}>
                <div className="group h-full rounded-2xl border border-line bg-surface/90 p-6 backdrop-blur transition-[border-color,box-shadow] hover:border-accent/50 hover:shadow-[0_18px_50px_-28px_var(--accent-deep)]">
                  <span className="mb-3.5 flex size-9 items-center justify-center rounded-[10px] border border-accent/30 bg-accent/10 text-accent transition-transform group-hover:scale-110">
                    <f.icon size={17} strokeWidth={2} />
                  </span>
                  <h3 className="mb-2 font-display text-[16px] font-bold">{f.title}</h3>
                  <p className="text-sm text-ink2">{f.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Platform comparison ── */}
      <section id="compare" className="border-y border-line bg-bg2 px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <Eyebrow>Platform comparison</Eyebrow>
            <h2 className="font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">
              How NeuralOps Nexus <span className="nx-gradient bg-gradient-to-r from-accent via-live to-accent bg-clip-text text-transparent">compares</span>
            </h2>
            <p className="mt-4 max-w-2xl text-ink2">A side-by-side view across leading AI assistant platforms and open chat frameworks.</p>
          </Reveal>
          <Reveal>
            <div className="mt-11 overflow-x-auto rounded-2xl border border-line bg-surface">
              <table className="w-full min-w-[820px] border-collapse text-[13.5px]">
                <thead>
                  <tr className="border-b border-line text-left">
                    <th className="px-5 py-4 font-mono text-[11px] font-semibold uppercase tracking-[.1em] text-ink2">Category</th>
                    <th className="px-5 py-4"><p className="font-display text-[14.5px] font-bold">Assistant platforms</p><p className="font-mono text-[10.5px] uppercase tracking-[.08em] text-ink2">Productivity layer</p></th>
                    <th className="px-5 py-4"><p className="font-display text-[14.5px] font-bold">Open chat frameworks</p><p className="font-mono text-[10.5px] uppercase tracking-[.08em] text-ink2">Open AI interface layer</p></th>
                    <th className="bg-accent/5 px-5 py-4"><p className="font-display text-[14.5px] font-bold text-accent">NeuralOps Nexus</p><p className="font-mono text-[10.5px] uppercase tracking-[.08em] text-ink2">Coordination layer</p></th>
                  </tr>
                </thead>
                <tbody>
                  {COMPARISON.map((r) => (
                    <tr key={r.category} className="border-b border-line last:border-b-0">
                      <td className="px-5 py-3.5 font-semibold">{r.category}</td>
                      <td className="px-5 py-3.5 text-ink2">{r.a}</td>
                      <td className="px-5 py-3.5 text-ink2">{r.b}</td>
                      <td className="bg-accent/5 px-5 py-3.5">{r.nexus}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-[12px] text-ink2 lg:hidden">Tip: scroll the table horizontally on smaller screens.</p>
          </Reveal>
        </div>
      </section>

      {/* ── Plans ── */}
      <section id="plans" className="px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal className="text-center">
            <Eyebrow center>Plans</Eyebrow>
            <h2 className="font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">Start free, self-hosted</h2>
            <p className="mx-auto mt-4 max-w-2xl text-ink2">
              The Community edition is the full platform today. Managed and enterprise offerings are on the way —
              here&apos;s what each will include.
            </p>
          </Reveal>
          <div className="mt-11 grid gap-4 md:grid-cols-3">
            {PLANS.map((p) => (
              <Reveal key={p.name}>
                <div className={`flex h-full flex-col rounded-2xl border bg-surface p-6 ${p.highlight ? "border-accent/50 shadow-[0_18px_50px_-30px_var(--accent-deep)]" : "border-line"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <h3 className="font-display text-[19px] font-bold">{p.name}</h3>
                    <span className={`flex-none rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${p.soon ? "bg-surface2 text-ink2" : "bg-ok/12 text-ok"}`}>
                      {p.soon ? "Coming soon" : "Available now"}
                    </span>
                  </div>
                  <p className="mt-1 text-[13.5px] text-ink2">{p.tagline}</p>
                  <ul className="mt-5 flex flex-1 flex-col gap-2.5">
                    {p.features.map((f) => (
                      <li key={f} className="flex items-start gap-2 text-[13.5px]">
                        <Check aria-hidden size={15} strokeWidth={2.5} className={`mt-0.5 flex-none ${p.soon ? "text-ink2" : "text-ok"}`} />
                        <span className={p.soon ? "text-ink2" : ""}>{f}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ── Product status ── */}
      <section id="status" className="px-6 py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal className="text-center">
            <span className="inline-flex rounded-full bg-accent px-3.5 py-1 text-[11.5px] font-semibold text-accent-ink">Development</span>
            <h2 className="mt-4 font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">Product status</h2>
            <p className="mx-auto mt-3 max-w-xl text-ink2">MVP in development — foundation already defined. We are building the core today, and scaling into a full platform.</p>
          </Reveal>
          <Reveal className="mt-10">
            <div className="grid gap-3 rounded-2xl border border-line bg-surface p-6 sm:grid-cols-3">
              {[["Architecture", "designed and validated"], ["Core system", "under active development"], ["Open-source", "community contributing"]].map(([k, v]) => (
                <p key={k} className="flex items-start gap-2 text-[13.5px] text-ink2">
                  <Check aria-hidden size={15} strokeWidth={2.5} className="mt-0.5 flex-none text-ok" />
                  <span><b className="text-ink">{k}</b> {v}</span>
                </p>
              ))}
            </div>
          </Reveal>
          <Reveal className="mt-10">
            <h3 className="text-center font-display text-[19px] font-bold">MVP capabilities</h3>
            <div className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {MVP_CAPABILITIES.map((c) => (
                <div key={c.title} className="flex gap-3.5 rounded-2xl border border-line bg-surface p-5">
                  <span className="flex size-9 flex-none items-center justify-center rounded-[10px] border border-accent/30 bg-accent/10 text-accent">
                    <c.icon size={16} strokeWidth={2} />
                  </span>
                  <div>
                    <h4 className="text-[14.5px] font-bold">{c.title}</h4>
                    <p className="mt-1 text-[13px] text-ink2">{c.body}</p>
                  </div>
                </div>
              ))}
            </div>
            <p className="mx-auto mt-8 max-w-2xl text-center text-[13.5px] text-ink2">
              <b className="text-ink">Focus:</b> delivering a functional MVP with human + AI collaboration, multi-agent
              interaction, knowledge base integration, and model-agnostic connectivity.
            </p>
          </Reveal>
        </div>
      </section>

      {/* ── Open source ── */}
      <section id="opensource" className="border-t border-line bg-bg2 px-6 py-24">
        <div className="mx-auto max-w-4xl">
          <Reveal className="text-center">
            <Eyebrow center>Open source</Eyebrow>
            <h2 className="font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">Built in the open</h2>
            <p className="mx-auto mt-4 max-w-2xl text-ink2">
              NeuralOps Nexus is free software under AGPL-3.0. Read the code, open issues, and contribute on GitHub.
            </p>
          </Reveal>
          <Reveal className="mt-10"><GithubStatsCard /></Reveal>
        </div>
      </section>

      {/* ── Final CTA ── */}
      <section className="relative overflow-hidden border-t border-line bg-bg2 px-6 py-28 text-center">
        <Parallax speed={-0.08} className="absolute inset-0"><Nebula /></Parallax>
        <Parallax speed={-0.13} className="absolute inset-0"><Constellation density={26} /></Parallax>
        <Reveal className="relative">
          <h2 className="mx-auto font-display text-[clamp(28px,3.6vw,40px)] font-extrabold">Give your team its first AI teammate today.</h2>
          <p className="mx-auto mt-4 max-w-xl text-ink2">Connect to your server, build a persona, and @mention it — ten minutes from sign-in to your first chart.</p>
          <div className="mt-9 flex justify-center gap-3">
            <Link href="/login" className="inline-flex h-11 items-center gap-2 rounded-[10px] bg-accent px-6 text-[15px] font-semibold text-accent-ink shadow-[0_8px_24px_-10px_var(--accent-deep)] transition-[filter] hover:brightness-110">
              Open the app <ArrowRight size={16} strokeWidth={2} />
            </Link>
          </div>
        </Reveal>
      </section>

      <footer className="border-t border-line px-6 py-8 text-[12.5px] text-ink2">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4">
          <span>© 2026 NeuralOps, Inc. · Free software under AGPL-3.0 · The operating system for AI-driven teams.</span>
          <span className="flex-1" />
          <span className="font-mono text-[11.5px]">built for teams who ship with AI</span>
        </div>
      </footer>
    </div>
  );
}

function Eyebrow({ children, center }: { children: React.ReactNode; center?: boolean }) {
  return <p className={`mb-3.5 font-mono text-[11.5px] font-semibold uppercase tracking-[.16em] text-accent ${center ? "text-center" : ""}`}>{children}</p>;
}

function Chip({ children }: { children: React.ReactNode }) {
  return <code className="rounded-md border border-line bg-surface2 px-1.5 py-0.5 font-mono text-[11.5px]">{children}</code>;
}
