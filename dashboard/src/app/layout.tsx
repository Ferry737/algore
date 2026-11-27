import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { ToastProvider } from "@/components/providers/toast-provider";
import { AlgoDataProvider } from "@/lib/data-provider";
import { AppShell } from "@/components/shell/app-shell";
import { PwaRegister } from "@/components/pwa-register";

export const metadata: Metadata = {
  applicationName: "AlgoRE",
  title: {
    default: "AlgoRE — strategy command",
    template: "%s · AlgoRE",
  },
  description:
    "Clean-room trading strategy breeding, out-of-sample validation, and the live incubation ladder.",
  manifest: "/manifest.webmanifest",
  appleWebApp: {
    capable: true,
    statusBarStyle: "black-translucent",
    title: "AlgoRE",
  },
  formatDetection: { telephone: false },
  icons: {
    icon: [
      { url: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
      { url: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
    ],
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#09090B",
  colorScheme: "dark",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" data-type="software" data-kind="software">
      <body>
        <ToastProvider>
          <AlgoDataProvider>
            <AppShell>{children}</AppShell>
            <PwaRegister />
          </AlgoDataProvider>
        </ToastProvider>
      </body>
    </html>
  );
}
