import { describe, expect, it, vi } from 'vitest'
import { AtomRegistry, mkAtom, wrappers, type AtomRunResult } from './atom'

describe('AtomRegistry — basic primitive behavior', () => {
  it('runs a lambda op over inScope value and writes every outScope ref', async () => {
    const r = new AtomRegistry()
    r.setValue('x', 21)
    r.register(
      mkAtom(
        'double',
        ['x'],
        { type: 'lambda', fn: (n) => Number(n) * 2 },
        ['out-a', 'out-b'],
      ),
    )
    const out = await r.run('double')
    expect(out).toBe(42)
    expect(r.getValue('out-a')).toBe(42)
    expect(r.getValue('out-b')).toBe(42)
  })

  it('passes multiple inScope values as array when inScope has > 1 ref', async () => {
    const r = new AtomRegistry()
    r.setValue('a', 1)
    r.setValue('b', 2)
    r.register(
      mkAtom(
        'sum',
        ['a', 'b'],
        { type: 'lambda', fn: (inputs) => (inputs as number[]).reduce((s, v) => s + v, 0) },
        ['s'],
      ),
    )
    await r.run('sum')
    expect(r.getValue('s')).toBe(3)
  })

  it('noop op returns the inputs array', async () => {
    const r = new AtomRegistry()
    r.setValue('k', 'hello')
    r.register(mkAtom('pass', ['k'], { type: 'noop' }, ['o']))
    await r.run('pass')
    expect(r.getValue('o')).toEqual(['hello'])
  })

  it('throws on unregistered atom', async () => {
    const r = new AtomRegistry()
    await expect(r.run('ghost')).rejects.toThrow(/not registered/)
  })

  it('throws on named op (registry-dispatched, not implemented yet)', async () => {
    const r = new AtomRegistry()
    r.register(mkAtom('x', [], { type: 'named', name: 'foo' }, []))
    await expect(r.run('x')).rejects.toThrow(/named op/)
  })
})

describe('AtomRegistry — wrapper layer (L2 decoration)', () => {
  it('wraps with global (wraps: "*") wrapper, trace recorded', async () => {
    const r = new AtomRegistry()
    r.setValue('n', 7)
    r.register(
      mkAtom(
        'inc',
        ['n'],
        { type: 'lambda', fn: (x) => Number(x) + 1 },
        ['out'],
      ),
    )
    r.registerWrapper(wrappers.logging('logger'))

    const runs: AtomRunResult[] = []
    r.onRun((result) => runs.push(result))

    await r.run('inc')
    expect(runs).toHaveLength(1)
    expect(runs[0].trace).toBeDefined()
    const events = runs[0].trace!.map((t) => t.event)
    expect(events).toContain('before')
    expect(events).toContain('after')
  })

  it('caching wrapper avoids re-execution on identical input', async () => {
    const r = new AtomRegistry()
    const fn = vi.fn(async (input: unknown) => Number(input) * 10)
    r.register(
      mkAtom('pure', ['x'], { type: 'lambda', fn }, ['out']),
    )
    r.registerWrapper(wrappers.caching())

    r.setValue('x', 3)
    const first = await r.run('pure')
    const second = await r.run('pure')
    const third = await r.run('pure')

    expect(first).toBe(30)
    expect(second).toBe(30)
    expect(third).toBe(30)
    expect(fn).toHaveBeenCalledTimes(1) // cached runs skip the lambda
  })

  it('wrapper chain runs outermost-first, innermost-last', async () => {
    const r = new AtomRegistry()
    r.setValue('v', 0)
    r.register(
      mkAtom(
        'op',
        ['v'],
        { type: 'lambda', fn: () => 'core' },
        ['result'],
      ),
    )

    const order: string[] = []
    r.registerWrapper({
      id: 'outer',
      wraps: '*',
      fn: async (_ctx, next) => {
        order.push('outer:before')
        const out = await next()
        order.push('outer:after')
        return out
      },
    })
    r.registerWrapper({
      id: 'inner',
      wraps: '*',
      fn: async (_ctx, next) => {
        order.push('inner:before')
        const out = await next()
        order.push('inner:after')
        return out
      },
    })

    await r.run('op')
    expect(order).toEqual([
      'outer:before',
      'inner:before',
      'inner:after',
      'outer:after',
    ])
  })

  it('atom-specific wrapper targets only matching atom id', async () => {
    const r = new AtomRegistry()
    r.setValue('v', 1)
    r.register(mkAtom('target', ['v'], { type: 'lambda', fn: (x) => x }, ['t']))
    r.register(mkAtom('other', ['v'], { type: 'lambda', fn: (x) => x }, ['o']))

    const seen: string[] = []
    r.registerWrapper({
      id: 'specific',
      wraps: 'target',
      fn: async (ctx, next) => {
        seen.push(ctx.atom.id)
        return next()
      },
    })

    await r.run('target')
    await r.run('other')
    expect(seen).toEqual(['target']) // wrapper fired only on target
  })

  it('wrapper can short-circuit by returning without calling next()', async () => {
    const r = new AtomRegistry()
    r.setValue('v', 'should-not-run')
    const coreFn = vi.fn(() => 'from-core')
    r.register(mkAtom('op', ['v'], { type: 'lambda', fn: coreFn }, ['out']))

    r.registerWrapper({
      id: 'gate',
      wraps: '*',
      fn: async () => 'from-wrapper', // no next() called
    })

    const out = await r.run('op')
    expect(out).toBe('from-wrapper')
    expect(coreFn).not.toHaveBeenCalled()
  })
})
