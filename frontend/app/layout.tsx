import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "@/components/providers";

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
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
      </head>
      <body className="min-h-screen antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
