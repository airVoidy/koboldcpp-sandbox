import { describe, expect, it } from 'vitest'
import {
  listExtractors,
  runExtractor,
  listIdentityProjections,
  runIdentityProjection,
} from './extractors'

const rows = [
  { id: 1, name: 'alice', n: 10 },
  { id: 2, name: 'bob', n: 20 },
]

describe('extractors catalog', () => {
  it('lists extractors and aggregators', () => {
    expect(listExtractors('extractor').map((e) => e.id)).toEqual(
      expect.arrayContaining(['csv', 'json', 'markdown', 'sql-insert', 'pretty', 'python-df']),
    )
    expect(listExtractors('aggregator').map((e) => e.id)).toEqual(
      expect.arrayContaining(['count', 'sum', 'avg']),
    )
  })

  it('CSV format: header + values, comma-separated', () => {
    const out = runExtractor('csv', rows)
    expect(out.split('\n')).toEqual(['id,name,n', '1,alice,10', '2,bob,20'])
  })

  it('CSV escapes embedded commas + quotes', () => {
    const out = runExtractor('csv', [{ k: 'a,b', q: 'has "quote"' }])
    expect(out.split('\n')[1]).toBe('"a,b","has ""quote"""')
  })

  it('JSON produces valid pretty array', () => {
    const out = runExtractor('json', rows)
    expect(JSON.parse(out)).toEqual(rows)
  })

  it('Markdown table has header, separator, body', () => {
    const out = runExtractor('markdown', rows).split('\n')
    expect(out[0]).toBe('| id | name | n |')
    expect(out[1]).toBe('| --- | --- | --- |')
    expect(out[2]).toBe('| 1 | alice | 10 |')
  })

  it('SQL-Insert: multi-row INSERT', () => {
    const out = runExtractor('sql-insert', rows)
    expect(out).toContain('INSERT INTO t (id, name, n) VALUES')
    expect(out).toContain("(1, 'alice', 10)")
    expect(out).toContain("(2, 'bob', 20)")
  })

  it('Python DataFrame: pandas literal', () => {
    const out = runExtractor('python-df', rows)
    expect(out).toContain('import pandas as pd')
    expect(out).toContain('pd.DataFrame(')
  })

  it('COUNT aggregator returns row count', () => {
    expect(runExtractor('count', rows)).toBe('2')
    expect(runExtractor('count', [])).toBe('0')
  })

  it('SUM aggregator sums numeric columns only', () => {
    const out = runExtractor('sum', rows)
    expect(out).toContain('id: 3')
    expect(out).toContain('n: 30')
    expect(out).toContain('name: 0') // non-numeric column, sum stays 0
  })

  it('AVG aggregator averages numeric columns', () => {
    const out = runExtractor('avg', rows)
    expect(out).toContain('id: 1.500')
    expect(out).toContain('n: 15.000')
    expect(out).toContain('name: (no numeric)')
  })

  it('throws for unknown extractor id', () => {
    expect(() => runExtractor('ghost', rows)).toThrow(/no extractor/)
  })

  it('empty rows produce sensible output per format', () => {
    expect(runExtractor('csv', [])).toBe('')
    expect(runExtractor('json', [])).toBe('[]')
    expect(runExtractor('markdown', [])).toBe('_no rows_')
    expect(runExtractor('sql-insert', [])).toBe('-- no rows')
    expect(runExtractor('pretty', [])).toBe('(empty)')
  })
})

describe('identity projections — single-row "Copy as" catalog', () => {
  const row = { id: 7, name: 'alice', active: true }

  it('lists the expected projections', () => {
    const ids = listIdentityProjections().map((p) => p.id)
    expect(ids).toEqual(
      expect.arrayContaining(['json', 'json-pretty', 'csv-line', 'key-value', 'sql-insert-single', 'primary-key', 'atom-uri', 'row-index']),
    )
  })

  it('json: compact, parseable', () => {
    expect(JSON.parse(runIdentityProjection('json', row))).toEqual(row)
  })

  it('csv-line: no header, just values', () => {
    expect(runIdentityProjection('csv-line', row)).toBe('7,alice,true')
  })

  it('key-value pairs', () => {
    const out = runIdentityProjection('key-value', row)
    expect(out).toContain('id=7')
    expect(out).toContain('name="alice"')
    expect(out).toContain('active=true')
  })

  it('sql-insert-single uses context.tableName if given', () => {
    expect(runIdentityProjection('sql-insert-single', row, { tableName: 'people' })).toBe(
      "INSERT INTO people (id, name, active) VALUES (7, 'alice', true);",
    )
  })

  it('primary-key extracts row.id', () => {
    expect(runIdentityProjection('primary-key', row)).toBe('7')
    expect(runIdentityProjection('primary-key', {})).toBe('(no id)')
  })

  it('atom-uri uses context for path shape', () => {
    expect(runIdentityProjection('atom-uri', row, { tableName: 'users', rowIndex: 3 })).toBe('atom://users/7')
    expect(runIdentityProjection('atom-uri', {}, { rowIndex: 3 })).toBe('atom://rows/3')
  })

  it('row-index falls back when no context', () => {
    expect(runIdentityProjection('row-index', row, { rowIndex: 42 })).toBe('42')
    expect(runIdentityProjection('row-index', row)).toBe('(no index)')
  })

  it('throws for unknown id', () => {
    expect(() => runIdentityProjection('ghost', row)).toThrow(/no identity projection/)
  })

  it('mimebundle: multiple MIME representations of a single row', () => {
    const out = runIdentityProjection('mimebundle', row, { tableName: 'people' })
    const bundle = JSON.parse(out) as Record<string, string>
    expect(bundle).toHaveProperty('application/json')
    expect(bundle).toHaveProperty('text/html')
    expect(bundle).toHaveProperty('text/markdown')
    expect(bundle).toHaveProperty('text/plain')
    expect(bundle).toHaveProperty('text/uri-list')
    expect(JSON.parse(bundle['application/json'])).toEqual(row)
    expect(bundle['text/html']).toContain('<table>')
    expect(bundle['text/uri-list']).toBe('atom://people/7')
  })
})

describe('ipynb extractor — Jupyter notebook format', () => {
  const rows = [
    { id: 1, name: 'alice', n: 10 },
    { id: 2, name: 'bob', n: 20 },
  ]

  it('produces valid nbformat 4 JSON', () => {
    const out = runExtractor('ipynb', rows)
    const nb = JSON.parse(out)
    expect(nb.nbformat).toBe(4)
    expect(nb.nbformat_minor).toBe(5)
    expect(nb.metadata.kernelspec.name).toBe('python3')
    expect(Array.isArray(nb.cells)).toBe(true)
    expect(nb.cells.length).toBe(3)
  })

  it('has markdown intro, markdown table, code cell', () => {
    const nb = JSON.parse(runExtractor('ipynb', rows))
    expect(nb.cells[0].cell_type).toBe('markdown')
    expect(nb.cells[1].cell_type).toBe('markdown')
    expect(nb.cells[2].cell_type).toBe('code')
    expect(nb.cells[2].outputs).toEqual([])
    expect(nb.cells[2].execution_count).toBe(null)
  })

  it('code cell contains pd.DataFrame literal', () => {
    const nb = JSON.parse(runExtractor('ipynb', rows))
    const codeSource = (nb.cells[2].source as string[]).join('')
    expect(codeSource).toContain('import pandas as pd')
    expect(codeSource).toContain('pd.DataFrame(')
    expect(codeSource).toContain('"alice"')
  })

  it('cell.source is line-split array (Jupyter convention)', () => {
    const nb = JSON.parse(runExtractor('ipynb', rows))
    for (const cell of nb.cells) {
      expect(Array.isArray(cell.source)).toBe(true)
    }
  })
})
