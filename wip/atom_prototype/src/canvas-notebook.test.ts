import { describe, expect, it } from 'vitest'
import {
  encodeCoord,
  loadCanvasCells,
  newCell,
  parseCoord,
  saveCanvasCells,
  seedCells,
  type JupyterNotebook,
} from './canvas-notebook'

describe('coord parsing', () => {
  it('parseCoord: "x,y" → {x,y}', () => {
    expect(parseCoord('120,240')).toEqual({ x: 120, y: 240 })
    expect(parseCoord(' 50 , 60 ')).toEqual({ x: 50, y: 60 })
  })
  it('parseCoord: invalid or undefined → null', () => {
    expect(parseCoord(undefined)).toBeNull()
    expect(parseCoord('abc,10')).toBeNull()
    expect(parseCoord('')).toBeNull()
  })
  it('encodeCoord rounds to integer', () => {
    expect(encodeCoord(120.7, 240.3)).toBe('121,240')
  })
})

describe('loadCanvasCells — Jupyter → Canvas', () => {
  it('respects cell.metadata.atom.pos when present', () => {
    const nb: JupyterNotebook = {
      nbformat: 4,
      nbformat_minor: 5,
      metadata: {},
      cells: [
        {
          cell_type: 'markdown',
          source: ['# hi\n'],
          metadata: { atom: { pos: '100,200', size: '300,150' } },
        },
      ],
    }
    const cells = loadCanvasCells(nb)
    expect(cells[0].pos).toEqual({ x: 100, y: 200 })
    expect(cells[0].size).toEqual({ w: 300, h: 150 })
    expect(cells[0].source).toBe('# hi\n')
  })

  it('auto-lays-out cells without positions in a grid', () => {
    const nb: JupyterNotebook = {
      nbformat: 4,
      nbformat_minor: 5,
      metadata: {},
      cells: [
        { cell_type: 'markdown', source: 'a', metadata: {} },
        { cell_type: 'markdown', source: 'b', metadata: {} },
      ],
    }
    const cells = loadCanvasCells(nb)
    expect(cells[0].pos.x).toBe(20)
    expect(cells[0].pos.y).toBe(20)
    // Second cell offset by 340px
    expect(cells[1].pos.x).toBe(360)
    expect(cells[1].pos.y).toBe(20)
  })

  it('joins array-form source into a single string', () => {
    const nb: JupyterNotebook = {
      nbformat: 4,
      nbformat_minor: 5,
      metadata: {},
      cells: [{ cell_type: 'code', source: ['line1\n', 'line2'], metadata: {} }],
    }
    const cells = loadCanvasCells(nb)
    expect(cells[0].source).toBe('line1\nline2')
  })
})

describe('saveCanvasCells — Canvas → Jupyter', () => {
  it('produces valid nbformat 4.5 with atom metadata', () => {
    const nb = saveCanvasCells([
      {
        id: 'a',
        cell_type: 'markdown',
        source: '# x\n',
        pos: { x: 100, y: 200 },
        size: { w: 300, h: 150 },
        z: 1,
      },
    ])
    expect(nb.nbformat).toBe(4)
    expect(nb.nbformat_minor).toBe(5)
    expect(nb.metadata['atom.canvas']).toBeDefined()
    expect(nb.cells[0].metadata.atom).toEqual({
      pos: '100,200',
      size: '300,150',
      z: 1,
    })
  })

  it('stores source as line array (Jupyter convention)', () => {
    const nb = saveCanvasCells([
      {
        id: 'a',
        cell_type: 'markdown',
        source: 'line1\nline2\n',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
      },
    ])
    expect(Array.isArray(nb.cells[0].source)).toBe(true)
    expect(nb.cells[0].source).toEqual(['line1\n', 'line2\n', ''])
  })

  it('code cells get empty outputs + null execution_count', () => {
    const nb = saveCanvasCells([
      {
        id: 'a',
        cell_type: 'code',
        source: 'print(1)',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
      },
    ])
    expect(nb.cells[0].outputs).toEqual([])
    expect(nb.cells[0].execution_count).toBeNull()
  })

  it('markdown/raw cells omit outputs + execution_count', () => {
    const nb = saveCanvasCells([
      {
        id: 'a',
        cell_type: 'markdown',
        source: '# x',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
      },
      {
        id: 'b',
        cell_type: 'raw',
        source: 'raw',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 2,
      },
    ])
    expect(nb.cells[0].outputs).toBeUndefined()
    expect(nb.cells[1].outputs).toBeUndefined()
    expect(nb.cells[0].execution_count).toBeUndefined()
    expect(nb.cells[1].execution_count).toBeUndefined()
  })
})

describe('round-trip save → load preserves positioning', () => {
  it('positions, sizes, z, cell types, source all round-trip', () => {
    const input = seedCells()
    const saved = saveCanvasCells(input)
    const loaded = loadCanvasCells(saved)

    expect(loaded).toHaveLength(input.length)
    for (let i = 0; i < input.length; i++) {
      expect(loaded[i].cell_type).toBe(input[i].cell_type)
      expect(loaded[i].pos).toEqual(input[i].pos)
      expect(loaded[i].size).toEqual(input[i].size)
      expect(loaded[i].z).toBe(input[i].z)
      expect(loaded[i].source).toBe(input[i].source)
    }
  })
})

describe('newCell factory', () => {
  it('markdown cell shape', () => {
    const c = newCell('markdown', 10, 20, 1)
    expect(c.cell_type).toBe('markdown')
    expect(c.pos).toEqual({ x: 10, y: 20 })
    expect(c.source).toContain('New markdown card')
    expect(c.outputs).toBeUndefined()
  })
  it('code cell gets empty outputs', () => {
    const c = newCell('code', 0, 0, 1)
    expect(c.outputs).toEqual([])
    expect(c.execution_count).toBeNull()
  })
})

describe('multi-face cells — shadow/container projections', () => {
  it('faces + activeFace round-trip through .ipynb metadata', () => {
    const input = [
      {
        id: 'multi',
        cell_type: 'markdown' as const,
        source: '# front',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
        faces: {
          notes: { content: 'private notes on back', format: 'text/plain' },
          annotations: { content: '[{"start":0,"end":5,"klass":"link"}]', format: 'application/json' },
        },
        activeFace: 'notes',
      },
    ]
    const saved = saveCanvasCells(input)
    const loaded = loadCanvasCells(saved)

    expect(loaded[0].faces).toEqual(input[0].faces)
    expect(loaded[0].activeFace).toBe('notes')
  })

  it('cells without faces omit the faces key in metadata', () => {
    const nb = saveCanvasCells([
      {
        id: 'plain',
        cell_type: 'markdown',
        source: '# x',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
      },
    ])
    expect(nb.cells[0].metadata.atom?.faces).toBeUndefined()
    expect(nb.cells[0].metadata.atom?.activeFace).toBeUndefined()
  })

  it('activeFace = "source" is the default and not serialized', () => {
    const nb = saveCanvasCells([
      {
        id: 'default-face',
        cell_type: 'markdown',
        source: '# x',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
        activeFace: 'source',
      },
    ])
    expect(nb.cells[0].metadata.atom?.activeFace).toBeUndefined()
  })

  it('empty faces object is treated as absent', () => {
    const nb = saveCanvasCells([
      {
        id: 'empty',
        cell_type: 'markdown',
        source: '# x',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
        faces: {},
      },
    ])
    expect(nb.cells[0].metadata.atom?.faces).toBeUndefined()
  })
})

describe('widget cells — interactive cards round-trippable through .ipynb', () => {
  it('widgetType + widgetProps + wiredTo round-trip', () => {
    const input = [
      {
        id: 'table-1',
        cell_type: 'raw' as const,
        source: 'widget: table-view (props in metadata)',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
        widgetType: 'table-view',
        widgetProps: { rows: [{ a: 1 }, { a: 2 }], columns: ['a'] },
      },
      {
        id: 'filter-1',
        cell_type: 'raw' as const,
        source: 'widget: filter-select',
        pos: { x: 120, y: 0 },
        size: { w: 100, h: 100 },
        z: 2,
        widgetType: 'filter-select',
        wiredTo: 'table-1',
      },
    ]
    const saved = saveCanvasCells(input)
    const loaded = loadCanvasCells(saved)

    expect(loaded[0].widgetType).toBe('table-view')
    expect(loaded[0].widgetProps).toEqual({ rows: [{ a: 1 }, { a: 2 }], columns: ['a'] })
    expect(loaded[0].wiredTo).toBeUndefined()
    expect(loaded[1].widgetType).toBe('filter-select')
    expect(loaded[1].wiredTo).toBe('table-1')
  })

  it('non-widget cells omit the widget metadata entirely', () => {
    const nb = saveCanvasCells([
      {
        id: 'plain',
        cell_type: 'markdown',
        source: '# x',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
      },
    ])
    expect(nb.cells[0].metadata.atom?.widget).toBeUndefined()
  })

  it('empty widgetProps object is treated as absent', () => {
    const nb = saveCanvasCells([
      {
        id: 'w',
        cell_type: 'raw',
        source: '',
        pos: { x: 0, y: 0 },
        size: { w: 100, h: 100 },
        z: 1,
        widgetType: 'x',
        widgetProps: {},
      },
    ])
    expect(nb.cells[0].metadata.atom?.widget?.props).toBeUndefined()
    expect(nb.cells[0].metadata.atom?.widget?.type).toBe('x')
  })
})
