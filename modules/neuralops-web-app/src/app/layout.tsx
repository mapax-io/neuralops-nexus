import type { Metadata } from "next";
import { Bricolage_Grotesque, Inter, JetBrains_Mono } from "next/font/google";
import { AppToaster } from "@/components/app-toaster";
import { InteractionRipple } from "@/components/interaction-ripple";
import { ThemeProvider } from "@/theme/theme-provider";
import { AppProviders } from "@/lib/providers";
import { APP_NAME } from "@/lib/version";
import "./globals.css";

const inter = Inter({ variable: "--font-inter", subsets: ["latin"] });
const bricolage = Bricolage_Grotesque({ variable: "--font-bricolage", subsets: ["latin"] });
const jetbrains = JetBrains_Mono({ variable: "--font-jetbrains", subsets: ["latin"] });

export const metadata: Metadata = {
  title: APP_NAME,
  description: "A private team workspace where AI personas work beside you — on your own server.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      suppressHydrationWarning
      className={`${inter.variable} ${bricolage.variable} ${jetbrains.variable} h-full antialiased`}
    >
      {/* suppressHydrationWarning: browser extensions (ColorZilla, Grammarly, …)
          inject attributes into <body> before React hydrates. Attribute-only —
          child mismatches still surface. */}
      <body suppressHydrationWarning className="min-h-full flex flex-col">
        <ThemeProvider>
          <AppProviders>{children}</AppProviders>
          <AppToaster />
          <InteractionRipple />
        </ThemeProvider>
      </body>
    </html>
  );
}
