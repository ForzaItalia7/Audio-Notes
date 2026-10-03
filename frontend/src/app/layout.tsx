import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Gnani Audio Notes",
  description: "Turn audio recordings into transcripts and structured notes.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
