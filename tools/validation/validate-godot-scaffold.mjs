import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const root = resolve("apps/quest-godot");
const project = readFileSync(resolve(root, "project.godot"), "utf8");
const scene = readFileSync(resolve(root, "main.tscn"), "utf8");
const script = readFileSync(resolve(root, "src/foundation_status.gd"), "utf8");

const required = [
  [project, "config_version=5", "Godot config format"],
  [project, 'run/main_scene="res://main.tscn"', "main scene"],
  [scene, 'type="Control"', "root scene node"],
  [scene, "res://src/foundation_status.gd", "foundation script resource"],
  [script, "const MILESTONE := 0", "milestone marker"],
  [
    script,
    "const PHYSICAL_CONTROL_ENABLED := false",
    "physical-control denial",
  ],
  [script, "const OPENXR_CONFIGURED := false", "OpenXR limitation"],
];

for (const [content, marker, label] of required) {
  if (!content.includes(marker)) {
    throw new Error(`Quest Godot scaffold is missing ${label}: ${marker}`);
  }
}

if (project.toLowerCase().includes("openxr")) {
  throw new Error("Milestone 0 project.godot must not configure OpenXR");
}

process.stdout.write(
  "Quest Godot Milestone 0 scaffold is structurally valid.\n",
);
