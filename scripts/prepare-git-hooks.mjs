// Best-effort git hook setup.
//
// Husky is a devDependency, so production/CI installs (Vercel) do not have it.
// Running `husky install` there only printed "sh: line 1: husky: command not
// found" into the build log. Hooks are a local convenience, never a build step:
// skip quietly when husky or the git directory is missing, and never fail.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

if (!existsSync("node_modules/husky") || !existsSync(".git")) {
  process.exit(0);
}

try {
  execFileSync(process.execPath, ["node_modules/husky/bin.js"], {
    stdio: "ignore",
  });
} catch {
  // Ignored on purpose: a missing hook must not break `npm install`.
}
