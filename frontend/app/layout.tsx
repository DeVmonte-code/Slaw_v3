import "./globals.css";
import type { ReactNode } from "react";

export const metadata = {
  title: "Swiss Legal Rights Scan",
  description: "Discover rights, deductions, and protections under Swiss law.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans antialiased">{children}</body>
    </html>
  );
}
