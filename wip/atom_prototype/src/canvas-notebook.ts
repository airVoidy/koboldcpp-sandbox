/**
 * Canvas notebook — Jupyter-compatible format, 2D-positioned cells.
 *
 * Reverse of default Jupyter: cells live at arbitrary (x, y) with overlap
 * allowed. Positioning stored as text in `cell.metadata.atom.pos` / `.size`
 * (e.g. `"120,240"` / `"320,200"`). Standard Jupyter readers ignore the
 * extra metadata and render cells linearly — the file is valid nbformat 4.5
 * either way. Round-trip via this module preserves positions.
 *
 * Text coords chosen over structured `{x:120, y:240}`:
 *   - human-readable in raw .ipynb JSON
 *   - minimal metadata footprint
 *   - matches our "canonical path is a projection" axiom (textual address)
 */

export type JCellType = 'markdown' | 'code' | 'raw'

/**
 * Named projection of a cell. "source" is reserved for the canonical
 * Jupyter source; additional faces live in cell.metadata.atom.faces and
 * roundtrip through .ipynb. Standard Jupyter ignores them; our viewer
 * surfaces them as tabs/flip targets on the card.
 */
export interface CellFace {
  content: string
  format?: string  // e.g. "text/markdown", "application/json", "text/langextract+annotations"
}

export interface CanvasCell {
  id: string
  cell_type: JCellType
  source: string
  pos: { x: number; y: number }
  size: { w: number; h: number }
  z: number
  /**
   * Named faces other than the canonical `source`. Each is a named projection
   * of this card (shadow layer, alternate view, derived output, annotation).
   * Keys: face names (e.g. "notes", "annotations", "sql-compiled").
   */
  faces?: Record<string, CellFace>
  /** Currently visible face name; defaults to "source" when unset. */
  activeFace?: string
  /**
   * When set, cell renders as an interactive widget instead of a textarea.
   * Widget type resolves through the widget registry; props pass through.
   * Raw ipynb cell_type typically set to 'raw' so standard Jupyter renders
   * readable fallback (widget type + props as raw text).
   */
  widgetType?: string
  widgetProps?: Record<string, unknown>
  /** Optional wiring: id of another cell this widget controls or observes. */
  wiredTo?: string
  /** For code cells. Optional. */
  outputs?: unknown[]
  execution_count?: number | null
}

export interface JupyterCell {
  cell_type: JCellType
  source: string | string[]
  metadata: Record<string, unknown> & {
    atom?: {
      pos?: string
      size?: string
      z?: number
      /**
       * Additional named projections of this cell — shadow-layer faces.
       * Each value: { content: string, format?: string }. Content stored as
       * string (not line array) to keep metadata terse; format is a MIME-ish
       * hint so readers know how to render.
       */
      faces?: Record<string, { content: string; format?: string }>
      activeFace?: string
      /**
       * Widget marker. When present, our canvas viewer renders the cell as
       * an interactive widget. Standard Jupyter ignores this and renders
       * the cell body verbatim (typically raw-cell text fallback).
       */
      widget?: {
        type: string
        props?: Record<string, unknown>
        wiredTo?: string
      }
    }
  }
  outputs?: unknown[]
  execution_count?: number | null
  id?: string
}

export interface JupyterNotebook {
  nbformat: number
  nbformat_minor: number
  metadata: Record<string, unknown>
  cells: JupyterCell[]
}

/** Parse "x,y" → {x, y}. Accepts whitespace. Returns null on failure. */
export function parseCoord(s: string | undefined): { x: number; y: number } | null {
  if (!s) return null
  const [xs, ys] = s.split(',').map((p) => p.trim())
  const x = Number(xs)
  const y = Number(ys)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null
  return { x, y }
}

export function encodeCoord(x: number, y: number): string {
  return `${Math.round(x)},${Math.round(y)}`
}

/** Jupyter's convention: source is array of lines, each ending in \n (except possibly last). */
function linesToText(source: string | string[]): string {
  return Array.isArray(source) ? source.join('') : source
}

function textToLines(s: string): string[] {
  const lines = s.split('\n')
  return lines.map((l, i) => (i === lines.length - 1 ? l : l + '\n'))
}

/**
 * Import: JupyterNotebook → CanvasCell[]. Cells without atom.pos get auto-laid-out
 * in a simple grid so they're visible.
 */
export function loadCanvasCells(nb: JupyterNotebook): CanvasCell[] {
  let autoX = 20
  let autoY = 20
  const cells: CanvasCell[] = []
  nb.cells.forEach((raw, i) => {
    const atomMeta = (raw.metadata?.atom ?? {}) as {
      pos?: string
      size?: string
      z?: number
      faces?: Record<string, CellFace>
      activeFace?: string
      widget?: { type: string; props?: Record<string, unknown>; wiredTo?: string }
    }
    const pos = parseCoord(atomMeta.pos) ?? { x: autoX, y: autoY }
    const size = parseCoord(atomMeta.size) ?? { x: 320, y: 160 } // "w,h" reuses parser
    const id = raw.id ?? `cell-${i}-${Math.random().toString(36).slice(2, 8)}`

    cells.push({
      id,
      cell_type: raw.cell_type,
      source: linesToText(raw.source),
      pos,
      size: { w: size.x, h: size.y },
      z: atomMeta.z ?? i + 1,
      faces: atomMeta.faces,
      activeFace: atomMeta.activeFace,
      widgetType: atomMeta.widget?.type,
      widgetProps: atomMeta.widget?.props,
      wiredTo: atomMeta.widget?.wiredTo,
      outputs: raw.outputs,
      execution_count: raw.execution_count ?? null,
    })

    if (!atomMeta.pos) {
      autoX += 340
      if (autoX > 900) {
        autoX = 20
        autoY += 180
      }
    }
  })
  return cells
}

/** Export: CanvasCell[] → JupyterNotebook (valid nbformat 4.5). */
export function saveCanvasCells(cells: CanvasCell[]): JupyterNotebook {
  return {
    nbformat: 4,
    nbformat_minor: 5,
    metadata: {
      kernelspec: { display_name: 'Python 3', language: 'python', name: 'python3' },
      language_info: { name: 'python', version: '3.x' },
      'atom.canvas': { version: 1, layout: 'freeform' },
    },
    cells: cells.map((c) => {
      const atomMeta: JupyterCell['metadata']['atom'] = {
        pos: encodeCoord(c.pos.x, c.pos.y),
        size: encodeCoord(c.size.w, c.size.h),
        z: c.z,
      }
      if (c.faces && Object.keys(c.faces).length > 0) {
        atomMeta.faces = c.faces
      }
      if (c.activeFace && c.activeFace !== 'source') {
        atomMeta.activeFace = c.activeFace
      }
      if (c.widgetType) {
        atomMeta.widget = { type: c.widgetType }
        if (c.widgetProps && Object.keys(c.widgetProps).length > 0) {
          atomMeta.widget.props = c.widgetProps
        }
        if (c.wiredTo) {
          atomMeta.widget.wiredTo = c.wiredTo
        }
      }
      const out: JupyterCell = {
        cell_type: c.cell_type,
        source: textToLines(c.source),
        metadata: { atom: atomMeta },
        id: c.id,
      }
      if (c.cell_type === 'code') {
        out.outputs = c.outputs ?? []
        out.execution_count = c.execution_count ?? null
      }
      return out
    }),
  }
}

/** Create a fresh cell at a given position. */
export function newCell(type: JCellType, x: number, y: number, z: number): CanvasCell {
  return {
    id: `cell-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    cell_type: type,
    source:
      type === 'markdown'
        ? '## New markdown card\n\nDrag to move, resize corner.'
        : type === 'code'
          ? 'print("hello from atom canvas")'
          : 'raw text',
    pos: { x, y },
    size: { w: 320, h: 180 },
    z,
    outputs: type === 'code' ? [] : undefined,
    execution_count: type === 'code' ? null : undefined,
  }
}

/** Default seed set — what user sees on first load. */
export function seedCells(): CanvasCell[] {
  const peopleRows = [
    { id: 1, name: 'Alice', role: 'eng', years: 5 },
    { id: 2, name: 'Bob', role: 'designer', years: 3 },
    { id: 3, name: 'Carol', role: 'pm', years: 7 },
    { id: 4, name: 'Dave', role: 'eng', years: 2 },
  ]
  return [
    {
      id: 'intro',
      cell_type: 'markdown',
      source:
        '# Canvas Notebook\n\nJupyter-compatible .ipynb with 2D cells + widget cells.\n\nDrag headers, resize corners. Widget cells render interactive components instead of text — but remain valid Jupyter raw cells for round-trip.',
      pos: { x: 40, y: 40 },
      size: { w: 420, h: 180 },
      z: 1,
    },
    {
      id: 'table-people',
      cell_type: 'raw',
      source: 'widget: table-view (see metadata.atom.widget for props)',
      pos: { x: 480, y: 40 },
      size: { w: 380, h: 200 },
      z: 2,
      widgetType: 'table-view',
      widgetProps: { rows: peopleRows },
    },
    {
      id: 'filter-role',
      cell_type: 'raw',
      source: 'widget: filter-select role',
      pos: { x: 40, y: 240 },
      size: { w: 280, h: 140 },
      z: 3,
      widgetType: 'filter-select',
      widgetProps: { label: 'role', options: ['eng', 'designer', 'pm'] },
      wiredTo: 'table-people',
    },
    {
      id: 'agg-count',
      cell_type: 'raw',
      source: 'widget: aggregator COUNT',
      pos: { x: 340, y: 240 },
      size: { w: 180, h: 140 },
      z: 4,
      widgetType: 'aggregator',
      widgetProps: { rows: peopleRows, mode: 'count' },
      wiredTo: 'table-people',
    },
    {
      id: 'agg-avg-years',
      cell_type: 'raw',
      source: 'widget: aggregator AVG(years)',
      pos: { x: 540, y: 240 },
      size: { w: 200, h: 140 },
      z: 5,
      widgetType: 'aggregator',
      widgetProps: { rows: peopleRows, mode: 'avg', column: 'years' },
      wiredTo: 'table-people',
    },
    {
      id: 'code-sample',
      cell_type: 'code',
      source: 'import pandas as pd\ndf = pd.DataFrame({"x":[1,2,3]})\ndf',
      pos: { x: 40, y: 400 },
      size: { w: 360, h: 160 },
      z: 6,
      outputs: [],
      execution_count: null,
    },
    {
      id: 'overlap-note',
      cell_type: 'markdown',
      source:
        '## Widgets coexist с text cells\n\nAll above cells round-trip through valid `.ipynb`. Standard Jupyter reads them as raw/markdown/code; our viewer surfaces widgets inline.',
      pos: { x: 420, y: 420 },
      size: { w: 360, h: 140 },
      z: 7,
    },
  ]
}
