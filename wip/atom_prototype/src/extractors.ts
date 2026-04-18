/**
 * Extractors — named projections from structured data to string output.
 *
 * Directly inspired by IntelliJ's com.intellij.database/data/extractors/*.groovy
 * pattern: each extractor is a pure function from row-list → formatted string,
 * registered in a catalog, picked by the user from a context menu.
 *
 * Our pattern addition: extractors are ordinary atoms with `kind: 'projection'`
 * from the AtomRegistry point of view. They can be wrapped (logged, cached,
 * bridged) exactly like any other atom op.
 */

import type { Atom, OpSpec } from './atom'

/** Minimum row shape extractors operate on. */
export type Row = Record<string, unknown>

export interface Extractor {
  /** Unique id in the catalog. */
  id: string
  /** Human label shown in UIs (right-click menu, list). */
  label: string
  /** Free-form category. In IntelliJ: extractors / aggregators / schema / schema.layouts */
  category: 'extractor' | 'aggregator' | 'schema' | 'layout'
  /** Mime / format hint. */
  format: string
  /** Optional short description. */
  description?: string
  /** The projection itself — pure, deterministic. */
  run: (rows: Row[]) => string
}

const catalog = new Map<string, Extractor>()

export function registerExtractor(x: Extractor) {
  catalog.set(x.id, x)
}

export function getExtractor(id: string) {
  return catalog.get(id)
}

export function listExtractors(category?: Extractor['category']) {
  const all = [...catalog.values()]
  return category ? all.filter((x) => x.category === category) : all
}

export function runExtractor(id: string, rows: Row[]): string {
  const x = catalog.get(id)
  if (!x) throw new Error(`no extractor "${id}"`)
  return x.run(rows)
}

/* ---------- built-in extractors (same roles as IntelliJ's *.groovy) ---------- */

registerExtractor({
  id: 'csv',
  label: 'CSV',
  category: 'extractor',
  format: 'text/csv',
  description: 'Comma-separated values with header row',
  run: (rows) => {
    if (rows.length === 0) return ''
    const cols = columnsOf(rows)
    const escape = (v: unknown) => {
      const s = v == null ? '' : String(v)
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }
    const lines = [cols.join(',')]
    for (const r of rows) lines.push(cols.map((c) => escape(r[c])).join(','))
    return lines.join('\n')
  },
})

registerExtractor({
  id: 'json',
  label: 'JSON',
  category: 'extractor',
  format: 'application/json',
  description: 'Pretty JSON array of row objects',
  run: (rows) => JSON.stringify(rows, null, 2),
})

registerExtractor({
  id: 'markdown',
  label: 'Markdown table',
  category: 'extractor',
  format: 'text/markdown',
  description: 'GitHub-flavored markdown table',
  run: (rows) => {
    if (rows.length === 0) return '_no rows_'
    const cols = columnsOf(rows)
    const row = (cells: string[]) => `| ${cells.join(' | ')} |`
    const out = [row(cols), row(cols.map(() => '---'))]
    for (const r of rows) out.push(row(cols.map((c) => String(r[c] ?? ''))))
    return out.join('\n')
  },
})

registerExtractor({
  id: 'sql-insert',
  label: 'SQL INSERT (multi-row)',
  category: 'extractor',
  format: 'application/sql',
  description: 'Single multi-row INSERT statement',
  run: (rows) => {
    if (rows.length === 0) return '-- no rows'
    const cols = columnsOf(rows)
    const valLit = (v: unknown) => {
      if (v == null) return 'NULL'
      if (typeof v === 'number' || typeof v === 'boolean') return String(v)
      return `'${String(v).replace(/'/g, "''")}'`
    }
    const values = rows.map((r) => `  (${cols.map((c) => valLit(r[c])).join(', ')})`).join(',\n')
    return `INSERT INTO t (${cols.join(', ')}) VALUES\n${values};`
  },
})

registerExtractor({
  id: 'python-df',
  label: 'Python DataFrame',
  category: 'extractor',
  format: 'text/x-python',
  description: 'pandas DataFrame literal',
  run: (rows) => {
    const repr = JSON.stringify(rows, null, 2).replace(/"([^"]+)":/g, '"$1":')
    return `import pandas as pd\n\ndf = pd.DataFrame(${repr})\n`
  },
})

registerExtractor({
  id: 'ipynb',
  label: 'Jupyter Notebook (.ipynb)',
  category: 'extractor',
  format: 'application/x-ipynb+json',
  description: 'Valid Jupyter notebook with markdown + code cells containing the data',
  run: (rows) => {
    const cols = columnsOf(rows)
    const mdHeader = `# Dataset\n\nExtracted ${rows.length} row(s) with columns: ${cols.map((c) => '`' + c + '`').join(', ')}.`
    const mdTable = (() => {
      if (rows.length === 0) return '_no rows_'
      const row = (cells: string[]) => `| ${cells.join(' | ')} |`
      const out = [row(cols), row(cols.map(() => '---'))]
      for (const r of rows) out.push(row(cols.map((c) => String(r[c] ?? ''))))
      return out.join('\n')
    })()
    const pyCode = `import pandas as pd\n\ndf = pd.DataFrame(${JSON.stringify(rows, null, 2)})\ndf\n`

    const notebook = {
      nbformat: 4,
      nbformat_minor: 5,
      metadata: {
        kernelspec: { display_name: 'Python 3', language: 'python', name: 'python3' },
        language_info: { name: 'python', version: '3.x' },
      },
      cells: [
        { cell_type: 'markdown', id: 'cell-intro', metadata: {}, source: splitLines(mdHeader) },
        { cell_type: 'markdown', id: 'cell-table', metadata: {}, source: splitLines(mdTable) },
        { cell_type: 'code', id: 'cell-df', metadata: {}, source: splitLines(pyCode), outputs: [], execution_count: null },
      ],
    }
    return JSON.stringify(notebook, null, 2)
  },
})

registerExtractor({
  id: 'pretty',
  label: 'Pretty text',
  category: 'extractor',
  format: 'text/plain',
  description: 'Fixed-width columns, readable output',
  run: (rows) => {
    if (rows.length === 0) return '(empty)'
    const cols = columnsOf(rows)
    const widths = cols.map((c) => Math.max(c.length, ...rows.map((r) => String(r[c] ?? '').length)))
    const pad = (s: string, w: number) => s + ' '.repeat(Math.max(0, w - s.length))
    const header = cols.map((c, i) => pad(c, widths[i])).join('  ')
    const sep = cols.map((_, i) => '-'.repeat(widths[i])).join('  ')
    const body = rows.map((r) => cols.map((c, i) => pad(String(r[c] ?? ''), widths[i])).join('  '))
    return [header, sep, ...body].join('\n')
  },
})

/* ---------- built-in aggregators ---------- */

registerExtractor({
  id: 'count',
  label: 'COUNT',
  category: 'aggregator',
  format: 'text/plain',
  description: 'Total row count',
  run: (rows) => String(rows.length),
})

registerExtractor({
  id: 'sum',
  label: 'SUM (per column)',
  category: 'aggregator',
  format: 'text/plain',
  description: 'Sum of numeric values per column',
  run: (rows) => {
    if (rows.length === 0) return '(no rows)'
    const cols = columnsOf(rows)
    const sums: Record<string, number> = {}
    for (const c of cols) sums[c] = 0
    for (const r of rows) {
      for (const c of cols) {
        const v = r[c]
        if (typeof v === 'number') sums[c] += v
      }
    }
    return cols.map((c) => `${c}: ${sums[c]}`).join('\n')
  },
})

registerExtractor({
  id: 'avg',
  label: 'AVG (per column)',
  category: 'aggregator',
  format: 'text/plain',
  description: 'Mean of numeric values per column',
  run: (rows) => {
    if (rows.length === 0) return '(no rows)'
    const cols = columnsOf(rows)
    const out: string[] = []
    for (const c of cols) {
      const nums = rows.map((r) => r[c]).filter((v): v is number => typeof v === 'number')
      if (nums.length === 0) out.push(`${c}: (no numeric)`)
      else out.push(`${c}: ${(nums.reduce((a, b) => a + b, 0) / nums.length).toFixed(3)}`)
    }
    return out.join('\n')
  },
})

/* ---------- single-item identity projections ---------- */

/**
 * Named representations of a SINGLE row. Parallel to IntelliJ's "Copy" submenu
 * (Absolute Path / File Name / Toolbox URL / Relative Path / ...): same item,
 * N projections picked by name.
 *
 * Distinct from extractors: extractors serialize a collection to a single
 * output; identity projections present one atom in N canonical views.
 */
export interface IdentityProjection {
  id: string
  label: string
  format: string
  description?: string
  run: (row: Row, context?: { rowIndex?: number; tableName?: string }) => string
}

const identityCatalog = new Map<string, IdentityProjection>()

export function registerIdentityProjection(p: IdentityProjection) {
  identityCatalog.set(p.id, p)
}

export function listIdentityProjections() {
  return [...identityCatalog.values()]
}

export function runIdentityProjection(id: string, row: Row, context?: { rowIndex?: number; tableName?: string }): string {
  const p = identityCatalog.get(id)
  if (!p) throw new Error(`no identity projection "${id}"`)
  return p.run(row, context)
}

registerIdentityProjection({
  id: 'json',
  label: 'JSON',
  format: 'application/json',
  description: 'Compact JSON of this single row',
  run: (row) => JSON.stringify(row),
})

registerIdentityProjection({
  id: 'json-pretty',
  label: 'JSON (pretty)',
  format: 'application/json',
  run: (row) => JSON.stringify(row, null, 2),
})

registerIdentityProjection({
  id: 'csv-line',
  label: 'CSV line',
  format: 'text/csv',
  description: 'Comma-separated values, no header',
  run: (row) => {
    const cols = Object.keys(row)
    return cols.map((c) => {
      const v = row[c]
      const s = v == null ? '' : String(v)
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
    }).join(',')
  },
})

registerIdentityProjection({
  id: 'key-value',
  label: 'Key=Value pairs',
  format: 'text/plain',
  run: (row) => Object.entries(row).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join('  '),
})

registerIdentityProjection({
  id: 'sql-insert-single',
  label: 'SQL INSERT (this row)',
  format: 'application/sql',
  run: (row, context) => {
    const cols = Object.keys(row)
    const litOf = (v: unknown) => {
      if (v == null) return 'NULL'
      if (typeof v === 'number' || typeof v === 'boolean') return String(v)
      return `'${String(v).replace(/'/g, "''")}'`
    }
    const table = context?.tableName ?? 't'
    return `INSERT INTO ${table} (${cols.join(', ')}) VALUES (${cols.map((c) => litOf(row[c])).join(', ')});`
  },
})

registerIdentityProjection({
  id: 'primary-key',
  label: 'Primary key only',
  format: 'text/plain',
  description: 'Just the value of column "id" if present',
  run: (row) => String(row.id ?? '(no id)'),
})

registerIdentityProjection({
  id: 'atom-uri',
  label: 'Atom URI',
  format: 'text/uri',
  description: 'Scope-prefixed URI (our atom://... format — parallel to Toolbox URL)',
  run: (row, context) => {
    const table = context?.tableName ?? 'rows'
    const id = String(row.id ?? context?.rowIndex ?? '?')
    return `atom://${table}/${id}`
  },
})

registerIdentityProjection({
  id: 'row-index',
  label: 'Row index',
  format: 'text/plain',
  description: 'Positional index in the source table',
  run: (_row, context) => String(context?.rowIndex ?? '(no index)'),
})

registerIdentityProjection({
  id: 'mimebundle',
  label: 'MIME bundle (Jupyter-style)',
  format: 'application/json',
  description: 'Multiple named representations at once — matches IPython `_repr_mimebundle_()` protocol',
  run: (row, context) => {
    const cols = Object.keys(row)
    const html =
      '<table><thead><tr>' +
      cols.map((c) => `<th>${escapeHtml(c)}</th>`).join('') +
      '</tr></thead><tbody><tr>' +
      cols.map((c) => `<td>${escapeHtml(String(row[c] ?? ''))}</td>`).join('') +
      '</tr></tbody></table>'
    const bundle: Record<string, string> = {
      'application/json': JSON.stringify(row),
      'text/html': html,
      'text/markdown': `**row**: ` + cols.map((c) => `\`${c}=${String(row[c] ?? '')}\``).join(' · '),
      'text/plain': cols.map((c) => `${c}=${JSON.stringify(row[c])}`).join('  '),
      'text/uri-list': `atom://${context?.tableName ?? 'rows'}/${row.id ?? context?.rowIndex ?? '?'}`,
    }
    return JSON.stringify(bundle, null, 2)
  },
})

/* ---------- helpers ---------- */

function columnsOf(rows: Row[]): string[] {
  const set = new Set<string>()
  for (const r of rows) for (const k of Object.keys(r)) set.add(k)
  return [...set]
}

function splitLines(s: string): string[] {
  // Jupyter's nbformat stores cell.source as an array of lines ending with \n
  // (except possibly the last). This matches notebook files written by hand.
  const lines = s.split('\n')
  return lines.map((l, i) => (i === lines.length - 1 ? l : l + '\n'))
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

/**
 * Convert an extractor into an Atom so it plugs into AtomRegistry and the
 * wrapper chain (logging, caching, etc.) uniformly. Input ref = rows source.
 */
export function extractorToAtom(x: Extractor, inputRef: string, outputRef: string): Atom {
  const op: OpSpec = {
    type: 'lambda',
    fn: (rows) => x.run((rows as Row[] | null) ?? []),
  }
  return {
    id: `extract:${x.id}`,
    kind: 'projection',
    inScope: [inputRef],
    op,
    outScope: [outputRef],
    tags: ['extractor', x.category, x.format],
    wrappers: [],
  }
}
