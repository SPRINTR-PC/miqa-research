// Keyboard commands other than tool keys (tools/registry.ts) and preset digits (tools/presets.ts).
// Built in: I = invert, Esc = reset. Tickets register theirs from their own module, e.g.
// V = orientation cycle (#282), Ctrl/⌘+S = save (#289), with `commands.register(...)`.
import type { ViewerContext } from "./context.ts";

export interface Command {
  id: string;
  /** `KeyboardEvent.key`, lower case ("i", "escape", "s"). */
  key: string;
  /** Needs Ctrl (or ⌘ on macOS). */
  ctrlOrMeta?: boolean;
  label: string;
  /** Whether the command applies now (role, view kind); default always. */
  available?(ctx: ViewerContext): boolean;
  run(ctx: ViewerContext): void;
}

export class CommandRegistry {
  private readonly all: Command[] = [];

  register(command: Command): void {
    const key = command.key.toLowerCase();
    const mod = !!command.ctrlOrMeta;
    const clash = this.all.find((c) => c.id === command.id || (c.key === key && !!c.ctrlOrMeta === mod));
    if (clash) throw new Error(`Command ${command.id} clashes with ${clash.id}`);
    this.all.push({ ...command, key });
  }

  forKey(key: string, ctrlOrMeta: boolean, ctx: ViewerContext): Command | undefined {
    const k = key.toLowerCase();
    return this.all.find((c) => c.key === k && !!c.ctrlOrMeta === ctrlOrMeta && (c.available?.(ctx) ?? true));
  }
}

export const commands = new CommandRegistry();

commands.register({ id: "invert", key: "i", label: "Invert", run: (ctx) => ctx.view?.toggleInvert() });
commands.register({ id: "reset", key: "escape", label: "Reset view", run: (ctx) => ctx.view?.resetView() });
