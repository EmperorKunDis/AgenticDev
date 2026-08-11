/**
 * praut-git — automatika kolem gitu pro Pi.
 *
 * Extension je záměrně tenká. Veškerou logiku dělá `bin/praut-git`,
 * deterministický shell nástroj. Extension jen volá ve správný čas.
 * Když se Pi API změní, opravuješ pár řádků, ne celý workflow.
 *
 * POZOR: signatury Pi API ověř proti docs/extensions.md ve své verzi.
 * Tohle je napsané podle veřejné dokumentace, ne odzkoušené proti běžícímu Pi.
 */
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";

const GIT = "bin/praut-git";

function run(args: string[]): string {
  try {
    return execFileSync(GIT, args, { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  } catch (e: any) {
    return `chyba: ${e?.stderr ?? e?.message ?? e}`;
  }
}

function branch(): string {
  try {
    return execFileSync("git", ["branch", "--show-current"], { encoding: "utf8" }).trim();
  } catch { return ""; }
}

export default function prautGit(api: any) {
  if (!existsSync(GIT)) return;

  // ── nástroje pro agenta ──
  api.addTool?.({
    name: "git_start",
    description: "Založí větev a worktree pro nový úkol. Vrátí cestu k worktree.",
    parameters: { type: "object", required: ["popis"], properties: {
      popis: { type: "string", description: "krátký popis úkolu" },
      taskId: { type: "string", description: "ID úkolu z nástěnky, volitelné" } } },
    handler: ({ popis, taskId }: any) => run(["start", popis, taskId ?? ""]),
  });

  api.addTool?.({
    name: "git_checkpoint",
    description: "Uloží průběžný bod návratu. Volej po každém smysluplném kusu práce.",
    parameters: { type: "object", required: ["zprava"], properties: {
      zprava: { type: "string" } } },
    handler: ({ zprava }: any) => run(["checkpoint", zprava]),
  });

  api.addTool?.({
    name: "git_save",
    description: "Pořádný commit podle Conventional Commits. Až když je kus hotový a otestovaný.",
    parameters: { type: "object", required: ["typ", "scope", "zprava"], properties: {
      typ: { type: "string", enum: ["feat","fix","refactor","test","docs","chore","perf","build","ci"] },
      scope: { type: "string" }, zprava: { type: "string" } } },
    handler: ({ typ, scope, zprava }: any) => run(["save", typ, scope, zprava]),
  });

  api.addTool?.({
    name: "git_finish",
    description: "Sesype checkpointy, narovná na main, odešle a otevře PR.",
    parameters: { type: "object", properties: { titulek: { type: "string" } } },
    handler: ({ titulek }: any) => run(["finish", titulek ?? ""]),
  });

  // ── slash příkazy pro člověka ──
  api.addCommand?.({ name: "git-list",  description: "rozdělané úkoly",
                     handler: () => run(["list"]) });
  api.addCommand?.({ name: "git-sync",  description: "rebase na aktuální main",
                     handler: () => run(["sync"]) });
  api.addCommand?.({ name: "git-clean", description: "smaže smergované větve a worktrees",
                     handler: () => run(["cleanup"]) });

  // ── automatika ──

  // 1) Varování hned na začátku, když sedíš na main.
  api.on?.("session_start", () => {
    if (["main", "master"].includes(branch())) {
      api.notify?.("Jsi na main. Než začneš psát: git_start(\"popis úkolu\")");
    }
  });

  // 2) Automatický checkpoint po každé sérii editací.
  //    Bez tokenů — jen shell. Práce se nikdy neztratí.
  let dirty = 0;
  api.on?.("tool_result", ({ tool }: any) => {
    if (!["write", "edit", "apply_patch", "str_replace"].includes(String(tool))) return;
    if (["main", "master"].includes(branch())) return;
    if (++dirty >= 3) { dirty = 0; run(["checkpoint", "průběžně"]); }
  });

  // 3) Checkpoint před koncem session — nedokončená práce přežije.
  api.on?.("session_end", () => {
    if (!["main", "master"].includes(branch())) run(["checkpoint", "konec session"]);
  });
}
