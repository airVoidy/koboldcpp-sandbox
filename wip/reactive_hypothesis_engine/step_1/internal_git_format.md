# Internal Git Format

## Goal

Определить, как использовать внутренний git не как обычный code repo, а как history layer для гипотез, step snapshots и semantic assembly.

## Proposed model

### 1. Root branch

- `main`
- хранит наиболее стабильную принятую базу состояния
- не должен засоряться всеми атомарными пробами

### 2. Atomic hypothesis branches

Branch pattern:
- `hyp/<hypothesis-id>`

Examples:
- `hyp/house-1-red-yes`
- `hyp/norwegian-next-to-blue`

Meaning:
- одна ветка = одна атомарная гипотеза или узкая связная проверка
- внутри может быть много промежуточных коммитов
- это exploration history, а не accepted knowledge

### 3. Step branches or snapshot commits

Branch pattern candidates:
- `step/<step-id>`
- or commit-only on current working branch

Meaning:
- результат локального saturation
- фиксирует только stabilised knowledge
- может собираться из нескольких atomic branch outcomes

### 4. Semantic merge model

Важно:
- это не обычный `git merge`
- это semantic reconciliation

Pipeline:
1. atomic branches produce outcomes
2. reconciler reads outcomes
3. compatible effects are assembled
4. step snapshot is created
5. only then accepted state is committed

## Suggested node layout inside a branch

```text
nodes/<node>/
  notes.md
  tables/
  runs/
  analysis/
    outcome.json
    step-0001.json
    effects/
      <effect-id>.json
    worker_output.md
```

## Branch semantics

### Atomic branch should store

- local hypothesis
- intermediate reactive checks
- final branch outcome
- contradictions if found
- worker-facing summary

### Step snapshot should store

- accepted outcomes refs
- new fixed cells
- domain narrowings
- derived constraints
- worker-facing summary

## Commit policy

### Good

- commit after meaningful local saturation
- commit branch outcome
- commit step snapshot

### Avoid

- commit every tiny reactive evaluation
- merge atomic branches textually into `main`

## Status model for branches

Suggested statuses:
- `open`
- `active`
- `saturated`
- `contradicted`
- `selected`
- `rejected`
- `merged-semantic`

These statuses can live in:
- `analysis/outcome.json`
- node metadata later if needed

## Open design questions for next chat

1. Should `step/<id>` be a real git branch or just a commit convention?
2. Should accepted step snapshots land directly on `main`, or on an intermediate branch first?
3. Do we want one atomic branch per hypothesis only, or also per connected component check?
4. How should we represent semantic-merge lineage between outcomes and snapshots?

## Recommended next decision

In the next chat, finalize:
- branch naming conventions
- when to create a branch vs when to commit in place
- whether `step snapshots` deserve their own branches
- minimal metadata required in `outcome.json` for semantic reconciliation
