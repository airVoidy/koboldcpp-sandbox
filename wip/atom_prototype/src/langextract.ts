/**
 * langextract wrappers — repurposed as our atomic shadow-layer engine.
 *
 * langextract's native use (Google's Python lib) is LLM-based structured
 * extraction from text. We strip the LLM path and reuse only its data format
 * — `AnnotatedDocument` with `extractions[]` tagged by class + char-interval.
 *
 * This module wires that format into our architecture:
 *   - atomic(span)     → a single extraction as an Atom
 *   - groupByClass(doc)→ detached NestedAtomicLists, one per extraction class
 *   - LangScope        → hierarchical scope (parent chain) holding a doc +
 *                        its detached lists + a Namescope for cross-list
 *                        aliasing
 *
 * LangChain's scope concept (RunnableConfig, callbacks, nested runs) is
 * mirrored via `LangScope.parent` — scopes nest hierarchically, each holds
 * its own namescope, detached lists live under it, and queries can walk up
 * the parent chain.
 */

import type { Atom } from './atom'
import { mkAtom } from './atom'
import { NestedAtomicList, computeAtomicHash } from './atomic-list'
import { Namescope } from './namescope'

/* ---------- langextract data format (compatible with Google's tool) ---------- */

export interface CharInterval {
  start_pos: number
  end_pos: number
}

export interface LangExtractSpan {
  extraction_class: string
  extraction_text: string
  char_interval: CharInterval
  attributes?: Record<string, unknown>
}

export interface AnnotatedDocument {
  document_id: string
  text: string
  extractions: LangExtractSpan[]
}

/* ---------- atomic(span): one span → one Atom ---------- */

/**
 * Wrap a single langextract span as an Atom. The op is a pure projection
 * returning the span payload; inScope is empty (span carries its own payload);
 * outScope is a stable ref derived from the span's content hash.
 */
export function atomic(span: LangExtractSpan, docId?: string): Atom {
  const h = computeAtomicHash(span)
  const id = `langext:${span.extraction_class}:${h.full.slice(0, 32)}`
  const outRef = `value:${id}`
  return mkAtom(
    id,
    [],
    { type: 'lambda', fn: () => span },
    [outRef],
    {
      kind: 'projection',
      tags: ['langextract', 'span', span.extraction_class],
      payload: { docId, span },
    },
  )
}

/* ---------- list(doc): per-class detached lists ---------- */

/**
 * Split a document's extractions into detached NestedAtomicLists, one per
 * extraction_class. Each list is independent (matches our "detached virtual
 * lists" pattern); cross-list references go through the containing LangScope's
 * namescope.
 */
export function groupByClass(doc: AnnotatedDocument): Record<string, NestedAtomicList<LangExtractSpan>> {
  const out: Record<string, NestedAtomicList<LangExtractSpan>> = {}
  for (const span of doc.extractions) {
    if (!out[span.extraction_class]) {
      out[span.extraction_class] = new NestedAtomicList<LangExtractSpan>()
    }
    out[span.extraction_class].add(span)
  }
  return out
}

/**
 * All spans combined into one nested list (useful when you want dedup across
 * classes, e.g., same text tagged with multiple classes collapses to one slot).
 */
export function toAtomicList(doc: AnnotatedDocument): NestedAtomicList<LangExtractSpan> {
  const list = new NestedAtomicList<LangExtractSpan>()
  for (const span of doc.extractions) list.add(span)
  return list
}

/* ---------- Virtual projections per span ---------- */

export interface SpanProjection {
  /** Matched text fragment. */
  text(span: LangExtractSpan): string
  /** Char range [start, end). */
  range(span: LangExtractSpan): [number, number]
  /** Tag class. */
  klass(span: LangExtractSpan): string
  /** Attached metadata. */
  attrs(span: LangExtractSpan): Record<string, unknown>
  /** Text with ±N chars of surrounding context from the source document. */
  withContext(span: LangExtractSpan, doc: AnnotatedDocument, pad?: number): string
  /** URI-form: scope-prefixed address for cross-scope referencing. */
  uri(span: LangExtractSpan, scopeId: string): string
}

export const spanProjections: SpanProjection = {
  text: (s) => s.extraction_text,
  range: (s) => [s.char_interval.start_pos, s.char_interval.end_pos],
  klass: (s) => s.extraction_class,
  attrs: (s) => s.attributes ?? {},
  withContext: (s, doc, pad = 20) => {
    const start = Math.max(0, s.char_interval.start_pos - pad)
    const end = Math.min(doc.text.length, s.char_interval.end_pos + pad)
    const before = doc.text.slice(start, s.char_interval.start_pos)
    const match = doc.text.slice(s.char_interval.start_pos, s.char_interval.end_pos)
    const after = doc.text.slice(s.char_interval.end_pos, end)
    return `${before}[[${match}]]${after}`
  },
  uri: (s, scopeId) =>
    `langext://${scopeId}/${encodeURIComponent(s.extraction_class)}/${s.char_interval.start_pos}-${s.char_interval.end_pos}`,
}

/* ---------- LangScope: hierarchical scope ---------- */

/**
 * Scope for langextract results, hierarchical via parent linking.
 *
 * Mirrors LangChain's concept of nested runs: an outer chain's run has its own
 * scope with memory, callbacks, config; inner runs inherit context but have
 * their own scope too. Here each LangScope holds:
 *   - the source document
 *   - detached per-class lists of spans
 *   - a Namescope for naming individual spans across lists
 *   - optional parent for walking up the chain
 */
export class LangScope {
  readonly id: string
  readonly doc: AnnotatedDocument
  readonly parent: LangScope | null
  readonly namescope: Namescope
  readonly lists: Record<string, NestedAtomicList<LangExtractSpan>>
  readonly metadata: {
    model?: string
    runId?: string
    timestamp?: number
    [k: string]: unknown
  }

  constructor(
    id: string,
    doc: AnnotatedDocument,
    options: { parent?: LangScope; metadata?: LangScope['metadata'] } = {},
  ) {
    this.id = id
    this.doc = doc
    this.parent = options.parent ?? null
    this.metadata = { timestamp: Date.now(), ...options.metadata }
    this.lists = groupByClass(doc)
    this.namescope = new Namescope()

    // Register each span as a virtual type in the namescope; alias first
    // occurrence per class as a convenience name.
    const classFirstSeen = new Set<string>()
    for (const span of doc.extractions) {
      const h = computeAtomicHash(span)
      const hash = h.full
      this.namescope.registerType({
        hash,
        type: `langext:${span.extraction_class}`,
        payload: span,
        tags: ['langextract', span.extraction_class],
      })
      if (!classFirstSeen.has(span.extraction_class)) {
        classFirstSeen.add(span.extraction_class)
        // Shared alias `first:<class>` points to the first span of that class.
        this.namescope.setSharedAlias(`first:${span.extraction_class}`, hash)
      }
    }
  }

  /** Available extraction classes in this scope. */
  classes(): string[] {
    return Object.keys(this.lists)
  }

  /** Count of spans per class, useful for summaries. */
  summary(): Record<string, number> {
    const out: Record<string, number> = {}
    for (const [k, list] of Object.entries(this.lists)) out[k] = list.size
    return out
  }

  /** Walk up the parent chain. Returns [self, ...ancestors]. */
  chain(): LangScope[] {
    const out: LangScope[] = []
    let cur: LangScope | null = this
    while (cur) {
      out.push(cur)
      cur = cur.parent
    }
    return out
  }

  /**
   * Walk up the chain looking for a span by namescope alias. Returns the
   * first match from the closest scope. Parallels LangChain's variable lookup
   * up the run-tree.
   */
  lookupAlias(name: string): LangExtractSpan | null {
    for (const scope of this.chain()) {
      const hash = scope.namescope.resolve(name)
      if (hash) {
        const entry = scope.namescope.get(hash)
        if (entry && typeof entry.payload === 'object') {
          return entry.payload as LangExtractSpan
        }
      }
    }
    return null
  }

  /**
   * Convert all spans in this scope to Atoms (atomic() per span).
   * Useful when integrating with AtomRegistry.
   */
  toAtoms(): Atom[] {
    return this.doc.extractions.map((s) => atomic(s, this.doc.document_id))
  }

  /** Child scope factory — links parent automatically. */
  childScope(id: string, childDoc: AnnotatedDocument, metadata?: LangScope['metadata']): LangScope {
    return new LangScope(id, childDoc, { parent: this, metadata })
  }
}

/* ---------- factory ---------- */

export function makeLangScope(
  id: string,
  doc: AnnotatedDocument,
  options?: { parent?: LangScope; metadata?: LangScope['metadata'] },
): LangScope {
  return new LangScope(id, doc, options)
}
