/**
 * Widget registry for canvas notebook cells.
 *
 * Widgets live in cell.metadata.atom.widget = {type, props?, wiredTo?}. Our
 * viewer resolves widget.type through this registry and renders the mapped
 * Vue component. Standard Jupyter ignores the metadata and falls back to
 * cell.source as plain text (which we populate with a human-readable
 * `widget: <type>` stub).
 *
 * Parallels container registry in mount.ts, specialized for inline cell
 * rendering (no floating cell management — widget lives inside its hosting
 * canvas cell).
 */

import type { Component } from 'vue'

interface WidgetEntry {
  component: Component
  label: string
}

const registry = new Map<string, WidgetEntry>()

export function registerWidget(type: string, component: Component, label: string = type) {
  registry.set(type, { component, label })
}

export function getWidget(type: string): WidgetEntry | undefined {
  return registry.get(type)
}

export function listWidgets(): Array<{ type: string; label: string }> {
  return [...registry.entries()].map(([type, e]) => ({ type, label: e.label }))
}
