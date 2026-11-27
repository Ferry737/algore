import type {
  CampaignStage,
  FrozenReason,
  HealthWord,
  PilotState,
  Severity,
} from "@/lib/types";
import { Badge, Dot, type BadgeTone } from "./badge";

export function healthTone(word: HealthWord): BadgeTone {
  switch (word) {
    case "OK":
      return "emerald";
    case "WATCH":
    case "DUPLICATE":
      return "amber";
    case "REPLACE":
      return "rose";
    case "EARLY":
    default:
      return "ink";
  }
}

export function HealthBadge({ word }: { word: HealthWord }) {
  return (
    <Badge tone={healthTone(word)} dot>
      {word}
    </Badge>
  );
}

export function FrozenBadge({ reason }: { reason: FrozenReason | null }) {
  if (!reason) {
    return (
      <Badge tone="neutral" dot>
        unfrozen
      </Badge>
    );
  }
  return (
    <Badge tone={reason === "LOSS" ? "rose" : "amber"} dot>
      frozen · {reason.toLowerCase().replace("_", " ")}
    </Badge>
  );
}

export function PilotBadge({ state }: { state: PilotState }) {
  const tone: BadgeTone = state === "ONLINE" ? "emerald" : "amber";
  return (
    <Badge tone={tone} dot>
      {state === "ONLINE" ? "pilot online" : state === "EA_SILENT" ? "EA silent" : "pilot offline"}
    </Badge>
  );
}

export function StageBadge({ stage }: { stage: CampaignStage }) {
  const tone: BadgeTone =
    stage === "done"
      ? "emerald"
      : stage === "breeding" || stage === "init"
        ? "ink"
        : "amber";
  return (
    <Badge tone={tone} dot>
      {stage === "final_war" ? "final war" : stage}
    </Badge>
  );
}

export function SeverityDot({ severity }: { severity: Severity }) {
  const tone: BadgeTone = severity === "low" ? "emerald" : "amber";
  return <Dot tone={tone} />;
}
