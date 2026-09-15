/** One iconography set for channels, shared by tiles, tabs and detail views. */

import {
  CloudRain,
  Droplets,
  Gauge,
  Sun,
  Thermometer,
  Wind,
  type LucideIcon,
} from "lucide-react";

const ICONS: Record<string, LucideIcon> = {
  thermometer: Thermometer,
  droplets: Droplets,
  gauge: Gauge,
  wind: Wind,
  sun: Sun,
  "cloud-rain": CloudRain,
  cloudrain: CloudRain,
  rain: CloudRain,
  pressure: Gauge,
  "air-quality": Wind,
  light: Sun,
  temperature: Thermometer,
  humidity: Droplets,
};

export function channelIcon(name: string | null | undefined): LucideIcon {
  if (!name) return Gauge;
  return ICONS[name.toLowerCase()] ?? ICONS[name.toLowerCase().replace(/_/g, "-")] ?? Gauge;
}
