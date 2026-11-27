import {
  Activity,
  Archive,
  Boxes,
  Dna,
  Layers,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
}

export const NAV_ITEMS: NavItem[] = [
  { href: "/", label: "Overview", icon: Activity },
  { href: "/campaigns", label: "Campaigns", icon: Dna },
  { href: "/vault", label: "Vault", icon: Archive },
  { href: "/portfolios", label: "Portfolios", icon: Boxes },
  { href: "/incubation", label: "Incubation", icon: Layers },
];
