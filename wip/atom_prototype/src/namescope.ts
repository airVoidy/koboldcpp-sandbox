/**
 * Local Namescope — two-detached-list pattern.
 *
 * Architectural idea:
 *   - Every atomic type (incl. virtual) has a hash UID. Hashes are primary
 *     identity; names are opt-in overlays.
 *   - Sometimes a caller needs a readable name (hash not available, or
 *     shorter mental model). Polluting the global namespace is undesirable.
 *   - Solution: two detached virtual lists with a ONE-WAY arrow.
 *
 *          LEFT (consumers)      one-way ref        RIGHT (registry + aliases)
 *          ┌──────────────┐   ─────────────▶        ┌────────────────────────┐
 *          │ cell_A       │                          │ virtual type catalog   │
 *          │ cell_B       │                          │   hash → {type,payload}│
 *          │ cell_C       │                          │                        │
 *          └──────────────┘                          │ shared aliases         │
 *                                                    │   name → hash          │
 *                                                    │                        │
 *                                                    │ personal aliases       │
 *                                                    │   cellId → (name→hash) │
 *                                                    └────────────────────────┘
 *
 *   - Right side (Namescope) holds: virtual type catalog, shared aliases,
 *     per-cell personal aliases. Knows nothing about cells directly.
 *   - Left side (NamescopeCell) each has a stable `cellId` and a ref to one
 *     Namescope. Cells are detached from each other — no cross-cell visibility
 *     of personal aliases.
 *
 * Alias resolution:
 *   1. Try personal alias for the cell
 *   2. Fall back to shared alias
 *   3. Otherwise undefined
 *
 * So names project either:
 *   - relative to one's own local cell (personal, visible only to self)
 *   - relative to the scope-wide shared namespace
 *
 * Global alias pollution avoided; every cell can still have human-friendly
 * names without stepping on other cells' names.
 */

export type Hash = string

export interface VirtualTypeEntry {
  hash: Hash
  type: string
  payload: unknown
  tags?: string[]
}

/**
 * Right-side container in the two-detached-list pattern.
 *
 * One-way: cells hold refs to this instance; this instance does NOT hold
 * any list of cells. Personal aliases are indexed by cellId (a plain string),
 * not by cell object reference — cells can be created and collected freely
 * without the Namescope caring.
 */
export class Namescope {
  private readonly types = new Map<Hash, VirtualTypeEntry>()
  private readonly shared = new Map<string, Hash>()
  // cellId → (alias → hash)
  private readonly personal = new Map<string, Map<string, Hash>>()

  /* --- virtual type catalog --- */

  registerType(entry: VirtualTypeEntry): void {
    this.types.set(entry.hash, entry)
  }

  unregisterType(hash: Hash): boolean {
    return this.types.delete(hash)
  }

  has(hash: Hash): boolean {
    return this.types.has(hash)
  }

  get(hash: Hash): VirtualTypeEntry | undefined {
    return this.types.get(hash)
  }

  entries(): VirtualTypeEntry[] {
    return [...this.types.values()]
  }

  size(): number {
    return this.types.size
  }

  /* --- query ops, delegated by cells --- */

  filter(pred: (e: VirtualTypeEntry) => boolean): VirtualTypeEntry[] {
    return this.entries().filter(pred)
  }

  sort(cmp: (a: VirtualTypeEntry, b: VirtualTypeEntry) => number): VirtualTypeEntry[] {
    return [...this.entries()].sort(cmp)
  }

  pick(pred: (e: VirtualTypeEntry) => boolean): VirtualTypeEntry | undefined {
    return this.entries().find(pred)
  }

  /* --- alias projection --- */

  setSharedAlias(name: string, hash: Hash): void {
    if (!this.types.has(hash)) {
      throw new Error(`cannot alias: hash "${hash}" not registered as a virtual type`)
    }
    this.shared.set(name, hash)
  }

  setPersonalAlias(cellId: string, name: string, hash: Hash): void {
    if (!this.types.has(hash)) {
      throw new Error(`cannot alias: hash "${hash}" not registered as a virtual type`)
    }
    let map = this.personal.get(cellId)
    if (!map) {
      map = new Map()
      this.personal.set(cellId, map)
    }
    map.set(name, hash)
  }

  /**
   * Resolve an alias. If cellId is given, personal takes precedence over shared.
   * Without cellId, only shared is considered.
   */
  resolve(name: string, cellId?: string): Hash | undefined {
    if (cellId !== undefined) {
      const personal = this.personal.get(cellId)?.get(name)
      if (personal !== undefined) return personal
    }
    return this.shared.get(name)
  }

  sharedAliases(): Array<[string, Hash]> {
    return [...this.shared.entries()]
  }

  personalAliasesFor(cellId: string): Array<[string, Hash]> {
    return [...(this.personal.get(cellId)?.entries() ?? [])]
  }

  removeSharedAlias(name: string): boolean {
    return this.shared.delete(name)
  }

  removePersonalAlias(cellId: string, name: string): boolean {
    return this.personal.get(cellId)?.delete(name) ?? false
  }

  /** Wipe all personal aliases for a cell (e.g., on cell disposal). */
  forgetCell(cellId: string): boolean {
    return this.personal.delete(cellId)
  }
}

/**
 * Left-side cell. Owns its cellId and a ref to ONE Namescope. Personal alias
 * methods scope to this cell; resolve walks personal → shared. Cells do not
 * know about each other.
 *
 * The `id` is stable within a Namescope — two cells with the same id share
 * the same personal alias space; use fresh ids (UUID / hash) when cells
 * should be isolated.
 */
export class NamescopeCell {
  constructor(
    public readonly id: string,
    private readonly ns: Namescope,
  ) {}

  /** Personal alias — visible only to this cell. */
  aliasLocal(name: string, hash: Hash): void {
    this.ns.setPersonalAlias(this.id, name, hash)
  }

  /** Shared alias — visible scope-wide. */
  aliasShared(name: string, hash: Hash): void {
    this.ns.setSharedAlias(name, hash)
  }

  /** Personal-first resolution. */
  resolve(name: string): Hash | undefined {
    return this.ns.resolve(name, this.id)
  }

  /** Resolve and hydrate to the full virtual type entry. */
  deref(name: string): VirtualTypeEntry | undefined {
    const hash = this.resolve(name)
    return hash ? this.ns.get(hash) : undefined
  }

  /* --- query delegation --- */

  filter(pred: (e: VirtualTypeEntry) => boolean): VirtualTypeEntry[] {
    return this.ns.filter(pred)
  }

  sort(cmp: (a: VirtualTypeEntry, b: VirtualTypeEntry) => number): VirtualTypeEntry[] {
    return this.ns.sort(cmp)
  }

  pick(pred: (e: VirtualTypeEntry) => boolean): VirtualTypeEntry | undefined {
    return this.ns.pick(pred)
  }

  /** Inspect this cell's personal alias list. */
  personalAliases(): Array<[string, Hash]> {
    return this.ns.personalAliasesFor(this.id)
  }

  /** Read shared aliases (same view for all cells). */
  sharedAliases(): Array<[string, Hash]> {
    return this.ns.sharedAliases()
  }

  removePersonalAlias(name: string): boolean {
    return this.ns.removePersonalAlias(this.id, name)
  }
}

/**
 * Convenience factory. Creates a fresh Namescope and returns a function
 * that produces cells bound to it.
 */
export function makeNamescope() {
  const ns = new Namescope()
  return {
    ns,
    cell(id: string) {
      return new NamescopeCell(id, ns)
    },
  }
}
