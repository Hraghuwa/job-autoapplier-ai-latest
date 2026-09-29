import type { Metadata } from "next";
import { Fraunces, DM_Sans, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

// Self-hosted at build time (Turbopack drops remote CSS @import, and this keeps
// the CSP free of third-party font origins).
const display = Fraunces({ subsets: ["latin"], style: ["normal", "italic"], axes: ["opsz"], variable: "--font-fraunces", display: "swap" });
const body = DM_Sans({ subsets: ["latin"], style: ["normal", "italic"], axes: ["opsz"], variable: "--font-dm-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jetbrains-mono", display: "swap" });

export const metadata: Metadata = {
  title: "JobAgent — AI-Powered Job Auto-Applier",
  description: "Automate your job applications across LinkedIn, Wellfound, Internshala, and more. AI-powered resume matching, cover letters, and one-click mass apply.",
  keywords: ["job auto applier", "AI job search", "automated applications", "LinkedIn applier", "job automation"],
  openGraph: {
    title: "JobAgent — AI-Powered Job Auto-Applier",
    description: "Automate your job applications across LinkedIn, Wellfound, and more with AI.",
    type: "website",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${display.variable} ${body.variable} ${mono.variable}`}>
      <body className="min-h-screen antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
