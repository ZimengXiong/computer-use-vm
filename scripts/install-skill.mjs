#!/usr/bin/env node
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const root = path.resolve(path.dirname(__filename), "..");
const source = path.join(root, "skills", "codex-vm-computer");
const codexHome = process.env.CODEX_HOME || path.join(os.homedir(), ".codex");
const targetRoot = path.join(codexHome, "skills");
const target = path.join(targetRoot, "codex-vm-computer");
const bridgeBin = path.join(root, "bin", "codex-vm-bridge");

function usage() {
  console.log(`Usage:
  npx computer-use-vm install-skill
  npx computer-use-vm add
  npx computer-use-vm

Installs the codex-vm-computer skill into $CODEX_HOME/skills.
Each machine builds its own base locally. That keeps Apple software, privacy grants, user state, caches, and machine-specific data out of GitHub, npm, releases, and Hugging Face.`);
}

function copyDir(src, dst) {
  fs.rmSync(dst, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.cpSync(src, dst, {
    recursive: true,
    filter: (item) => !item.endsWith(".DS_Store") && !item.includes(`${path.sep}__pycache__${path.sep}`),
  });
}

function patchWrapper() {
  const wrapper = path.join(target, "scripts", "codex-vm-bridge");
  let text = fs.readFileSync(wrapper, "utf8");
  text = text.replaceAll("__CODEX_VM_BRIDGE_ROOT__", root);
  fs.writeFileSync(wrapper, text, { mode: 0o755 });
}

const command = process.argv[2] || "install-skill";
if (command === "help" || command === "--help" || command === "-h") {
  usage();
  process.exit(0);
}
if (command !== "install-skill" && command !== "add") {
  console.error(`Unknown command: ${command}`);
  usage();
  process.exit(2);
}

if (!fs.existsSync(source)) {
  console.error(`Skill source not found: ${source}`);
  process.exit(1);
}
if (!fs.existsSync(bridgeBin)) {
  console.error(`Bridge executable not found: ${bridgeBin}`);
  process.exit(1);
}

fs.mkdirSync(targetRoot, { recursive: true });
copyDir(source, target);
patchWrapper();

console.log(`Installed codex-vm-computer skill to ${target}`);
console.log(`Bridge root: ${root}`);
console.log("");
console.log("Next steps:");
console.log("  1. Run: codex-vm-bridge diagnose");
console.log("  2. Build a local base VM with the README Quick Start commands.");
console.log("  3. Each machine builds its own base locally.");
