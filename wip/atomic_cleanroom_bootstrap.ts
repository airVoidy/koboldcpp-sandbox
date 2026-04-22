export type JsonPrimitive = string | number | boolean | null
export type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue }

export type AtomicRef = {
  id: string
  cell?: JsonValue
}

export type AtomicObject = {
  id: string
  data: JsonValue
  out?: JsonValue
  refs?: AtomicRef[]
}

export type AtomicList = {
  id: string
  items: string[]
  mode?: 'ordered' | 'dedup' | 'scope'
  refs?: AtomicRef[]
}

export type AtomicRule = {
  id: string
  body: JsonValue
  refs?: AtomicRef[]
}

export type ProjectionSlotState =
  | 'declared'
  | 'resolving'
  | 'materialized'
  | 'shadow'
  | 'problem'

export type ProjectionSlot = {
  id: string
  owner: string
  vector: JsonValue
  ruleRefs?: string[]
  value?: JsonValue
  state: ProjectionSlotState
}

export type AtomicArtifact = {
  id: string
  source: string
  blob: string
  view?: JsonValue
}

export type AtomicSnapshot = {
  id: string
  target: string
  objectIds: string[]
  listIds: string[]
  ruleIds: string[]
  slotIds: string[]
  createdAt: number
}

export class AtomicStore {
  readonly objects = new Map<string, AtomicObject>()
  readonly lists = new Map<string, AtomicList>()
  readonly rules = new Map<string, AtomicRule>()
  readonly slots = new Map<string, ProjectionSlot>()
  readonly attachments = new Map<string, string[]>()

  putObject(object: AtomicObject): AtomicObject {
    this.objects.set(object.id, object)
    return object
  }

  putList(list: AtomicList): AtomicList {
    this.lists.set(list.id, list)
    return list
  }

  putRule(rule: AtomicRule): AtomicRule {
    this.rules.set(rule.id, rule)
    return rule
  }

  attachRule(targetId: string, rule: AtomicRule): void {
    this.putRule(rule)
    const attached = this.attachments.get(targetId) ?? []
    attached.push(rule.id)
    this.attachments.set(targetId, attached)
  }

  declareSlot(slot: ProjectionSlot): ProjectionSlot {
    this.slots.set(slot.id, slot)
    return slot
  }

  materializeSlot(slotId: string, value: JsonValue): ProjectionSlot {
    const slot = this.slots.get(slotId)
    if (!slot) {
      throw new Error(`slot ${slotId} not found`)
    }

    const next: ProjectionSlot = {
      ...slot,
      value,
      state: 'materialized',
    }
    this.slots.set(slotId, next)
    return next
  }

  markSlot(slotId: string, state: Exclude<ProjectionSlotState, 'materialized'>): ProjectionSlot {
    const slot = this.slots.get(slotId)
    if (!slot) {
      throw new Error(`slot ${slotId} not found`)
    }

    const next: ProjectionSlot = {
      ...slot,
      state,
    }
    this.slots.set(slotId, next)
    return next
  }

  getAttachedRules(targetId: string): AtomicRule[] {
    const ids = this.attachments.get(targetId) ?? []
    return ids.map((id) => this.rules.get(id)).filter((v): v is AtomicRule => Boolean(v))
  }

  snapshot(target: string): AtomicSnapshot {
    return {
      id: `snapshot:${target}:${Date.now()}`,
      target,
      objectIds: [...this.objects.keys()],
      listIds: [...this.lists.keys()],
      ruleIds: [...this.rules.keys()],
      slotIds: [...this.slots.keys()],
      createdAt: Date.now(),
    }
  }
}

export function createAtomicObject(
  id: string,
  data: JsonValue,
  extras: Partial<Omit<AtomicObject, 'id' | 'data'>> = {},
): AtomicObject {
  return {
    id,
    data,
    out: extras.out,
    refs: extras.refs ?? [],
  }
}

export function createAtomicList(
  id: string,
  items: string[] = [],
  mode: AtomicList['mode'] = 'scope',
): AtomicList {
  return {
    id,
    items,
    mode,
    refs: [],
  }
}

export function createAtomicRule(id: string, body: JsonValue): AtomicRule {
  return {
    id,
    body,
    refs: [],
  }
}

export function createProjectionSlot(
  id: string,
  owner: string,
  vector: JsonValue,
  ruleRefs: string[] = [],
): ProjectionSlot {
  return {
    id,
    owner,
    vector,
    ruleRefs,
    state: 'declared',
  }
}

export function createArtifact(source: string, blob: string, view?: JsonValue): AtomicArtifact {
  return {
    id: `artifact:${source}:${Date.now()}`,
    source,
    blob,
    view,
  }
}

// Minimal usage:
//
// const store = new AtomicStore()
// const obj = createAtomicObject('house', { blocks: [] })
// const list = createAtomicList('house.scope', ['house'])
// const rule = createAtomicRule('sort.blocks', { what: 'sort', by: 'category' })
// const slot = createProjectionSlot('slot:house.blocks.sorted', 'house', {
//   from: '@[0].house.blocks',
//   to: '@[+1].house.blocks.sorted',
// })
//
// store.putObject(obj)
// store.putList(list)
// store.attachRule(obj.id, rule)
// store.declareSlot(slot)
// store.materializeSlot(slot.id, ['b1', 'b2'])
