import { describe, expect, it } from 'vitest'
import {
  atomic,
  groupByClass,
  toAtomicList,
  spanProjections,
  makeLangScope,
  LangScope,
  type AnnotatedDocument,
  type LangExtractSpan,
} from './langextract'

const sampleDoc: AnnotatedDocument = {
  document_id: 'doc-1',
  text: 'See the docs at https://example.com/docs (ref: RFC-1234). Lilith and Morgana are demonesses.',
  extractions: [
    {
      extraction_class: 'link',
      extraction_text: 'https://example.com/docs',
      char_interval: { start_pos: 16, end_pos: 40 },
      attributes: { href: 'https://example.com/docs' },
    },
    {
      extraction_class: 'ref',
      extraction_text: 'RFC-1234',
      char_interval: { start_pos: 47, end_pos: 55 },
      attributes: { citation: 'RFC-1234' },
    },
    {
      extraction_class: 'ent',
      extraction_text: 'Lilith',
      char_interval: { start_pos: 58, end_pos: 64 },
      attributes: { role: 'demoness' },
    },
    {
      extraction_class: 'ent',
      extraction_text: 'Morgana',
      char_interval: { start_pos: 69, end_pos: 76 },
      attributes: { role: 'demoness' },
    },
  ],
}

describe('atomic() — single span → Atom', () => {
  it('produces a projection atom with tags', () => {
    const a = atomic(sampleDoc.extractions[0], 'doc-1')
    expect(a.kind).toBe('projection')
    expect(a.tags).toContain('langextract')
    expect(a.tags).toContain('span')
    expect(a.tags).toContain('link')
    expect(a.id).toMatch(/^langext:link:/)
    expect(a.inScope).toEqual([])
    expect(a.outScope.length).toBe(1)
  })

  it('id is stable per span content', () => {
    const a1 = atomic(sampleDoc.extractions[0])
    const a2 = atomic(sampleDoc.extractions[0])
    expect(a1.id).toBe(a2.id)
  })
})

describe('groupByClass() — detached per-class lists', () => {
  it('one list per class, nested list each', () => {
    const groups = groupByClass(sampleDoc)
    expect(Object.keys(groups).sort()).toEqual(['ent', 'link', 'ref'])
    expect(groups.ent.size).toBe(2)
    expect(groups.link.size).toBe(1)
    expect(groups.ref.size).toBe(1)
  })

  it('lists are detached (independent) — modifying one does not touch another', () => {
    const groups = groupByClass(sampleDoc)
    groups.ent.clear()
    expect(groups.ent.size).toBe(0)
    expect(groups.link.size).toBe(1)
  })
})

describe('toAtomicList() — all spans in one nested list', () => {
  it('dedup across classes: structurally-identical spans collapse', () => {
    const list = toAtomicList(sampleDoc)
    expect(list.size).toBe(4) // all four unique
    const duplicateDoc: AnnotatedDocument = {
      ...sampleDoc,
      extractions: [...sampleDoc.extractions, sampleDoc.extractions[0]],
    }
    const listDup = toAtomicList(duplicateDoc)
    expect(listDup.size).toBe(4) // duplicate collapsed
  })
})

describe('spanProjections — virtual projections per span', () => {
  const span = sampleDoc.extractions[0]

  it('text, range, klass, attrs', () => {
    expect(spanProjections.text(span)).toBe('https://example.com/docs')
    expect(spanProjections.range(span)).toEqual([16, 40])
    expect(spanProjections.klass(span)).toBe('link')
    expect(spanProjections.attrs(span)).toEqual({ href: 'https://example.com/docs' })
  })

  it('withContext renders [[match]] with surrounding chars', () => {
    const out = spanProjections.withContext(span, sampleDoc, 10)
    expect(out).toContain('[[https://example.com/docs]]')
    expect(out.length).toBeGreaterThan(span.extraction_text.length)
  })

  it('uri encodes class + range, scope-prefixed', () => {
    expect(spanProjections.uri(span, 'scope-1')).toBe('langext://scope-1/link/16-40')
  })

  it('empty attrs fall back to {}', () => {
    const s: LangExtractSpan = { ...span, attributes: undefined }
    expect(spanProjections.attrs(s)).toEqual({})
  })
})

describe('LangScope — hierarchical scope', () => {
  it('instantiates with detached lists + namescope registering each span', () => {
    const scope = makeLangScope('s-1', sampleDoc)
    expect(scope.classes().sort()).toEqual(['ent', 'link', 'ref'])
    expect(scope.summary()).toEqual({ ent: 2, link: 1, ref: 1 })

    // Each span registered as a virtual type in the namescope.
    expect(scope.namescope.size()).toBe(4)

    // first:<class> shared aliases created for each distinct class.
    const resolved = scope.namescope.resolve('first:link')
    expect(resolved).toBeDefined()
    expect(scope.namescope.resolve('first:ent')).toBeDefined()
    expect(scope.namescope.resolve('first:ref')).toBeDefined()
  })

  it('chain() walks parent chain', () => {
    const outer = makeLangScope('outer', sampleDoc)
    const inner = outer.childScope('inner', sampleDoc)
    expect(inner.chain().map((s) => s.id)).toEqual(['inner', 'outer'])
    expect(outer.chain().map((s) => s.id)).toEqual(['outer'])
  })

  it('lookupAlias walks up parent chain', () => {
    const outerDoc: AnnotatedDocument = {
      document_id: 'outer-doc',
      text: 'Project Alpha kickoff.',
      extractions: [
        {
          extraction_class: 'project',
          extraction_text: 'Project Alpha',
          char_interval: { start_pos: 0, end_pos: 13 },
        },
      ],
    }
    const innerDoc: AnnotatedDocument = {
      document_id: 'inner-doc',
      text: 'Inner notes.',
      extractions: [],
    }
    const outer = makeLangScope('outer', outerDoc)
    const inner = outer.childScope('inner', innerDoc)

    // Inner has no project alias; should walk up and find outer's.
    const hit = inner.lookupAlias('first:project')
    expect(hit).not.toBeNull()
    expect(hit!.extraction_text).toBe('Project Alpha')
  })

  it('toAtoms produces one atom per span', () => {
    const scope = makeLangScope('s-1', sampleDoc)
    const atoms = scope.toAtoms()
    expect(atoms).toHaveLength(4)
    expect(atoms.every((a) => a.tags.includes('langextract'))).toBe(true)
  })

  it('metadata merges timestamp with user-provided fields', () => {
    const before = Date.now()
    const scope = makeLangScope('s-1', sampleDoc, { metadata: { model: 'stub-v0', runId: 'r-42' } })
    expect(scope.metadata.model).toBe('stub-v0')
    expect(scope.metadata.runId).toBe('r-42')
    expect(typeof scope.metadata.timestamp).toBe('number')
    expect(scope.metadata.timestamp!).toBeGreaterThanOrEqual(before)
  })

  it('parent is null by default, set when childScope is used', () => {
    const outer = makeLangScope('outer', sampleDoc)
    expect(outer.parent).toBeNull()
    const inner = outer.childScope('inner', sampleDoc)
    expect(inner.parent).toBe(outer)
  })
})

describe('hierarchical scope integration invariants', () => {
  it('child scope has its own lists and namescope — independent from parent', () => {
    const outer = makeLangScope('outer', sampleDoc)
    const inner = outer.childScope('inner', sampleDoc)

    // Lists are freshly built per scope.
    expect(inner.lists).not.toBe(outer.lists)
    // Namescopes independent.
    expect(inner.namescope).not.toBe(outer.namescope)
    // But both derive from the same doc structure, so same span count.
    expect(inner.summary()).toEqual(outer.summary())
  })

  it('LangScope instance class-check passes for built instances', () => {
    const s = makeLangScope('s-1', sampleDoc)
    expect(s).toBeInstanceOf(LangScope)
  })
})
