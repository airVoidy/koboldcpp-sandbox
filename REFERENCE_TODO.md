# Reference Todo

## Pine / Python References To Study

Keep these as external references for later design work around:

- Pine-like ASTs
- strategy/script conversion
- mathematical execution models already solved in open source
- serialization and replay-friendly scripting layers

### 1. pinescript-to-python

Reference:

- `github.com/loponly/pinescript-to-python`

Why keep it:

- Pine Script to Python conversion
- useful for understanding how existing projects map Pine semantics into Python runtime structures
- potentially useful for AST, execution semantics, and translation-layer design

### 2. pyine

Reference:

- `pypi.org/project/pyine/`

Why keep it:

- Pine Script conversion into Python scripts
- useful as a lightweight reference for partial conversion flows and representation choices

### 3. Pine to Python Converter

Reference:

- external/open-source converter tooling for Pine indicator logic to Python

Why keep it:

- likely useful for studying how indicator logic, transforms, and execution flow are represented outside TradingView

### 4. PyneCore

Reference:

- `https://github.com/PyneSys/pynecore`
- local checkout: `C:\llm\KoboldCPP agentic sandbox\pynecore`
- docs: `C:\llm\KoboldCPP agentic sandbox\pynecore\docs\overview\core-concepts.md`

Why keep it:

- likely best candidate runtime substrate for the first MVP
- already has AST transformation at import time
- already has Pine-style tick/bar execution semantics
- already has `Series`, `Persistent`, and function isolation
- already has rendering/output concepts that may be reusable

Important notes:

- license: Apache-2.0
- probably safe to adopt whole as a temporary base and refactor later
- our use case is simpler in one important way:
  - we do not need rich in-run dataflow between freshly produced values
  - we mostly need repeated structural casts plus serialized output fragments

Potential reuse:

- import hook / AST transformation shell
- tick execution substrate
- series/persistent machinery where useful
- renderer/output integration

Potential non-goals:

- most assignment-heavy Pine semantics
- trading-specific builtins
- complex in-run recalculation paths we do not need

## Why These Matter For This Project

Although our runtime is not a financial charting engine, these projects are relevant because they already solved parts of the problem space we care about:

- repeated tick execution
- script representation
- conversion from domain-specific language into Python/runtime form
- math-heavy logic in a compact scripting surface

So they are worth reviewing for:

- AST ideas
- runtime layout
- execution model simplifications
- serialization/logging patterns

## Future Review Questions

When reviewing these references, check:

1. How their AST or IR is shaped.
2. How much of Pine semantics they model explicitly.
3. What they assume about tick execution order.
4. How they serialize or expose intermediate states.
5. Whether any of their patterns can be reused for our mediator/DSL layer.
6. Which parts are Pine-specific and which parts are reusable as general execution math.
7. Which `pynecore` modules can be reused unchanged for MVP.
8. Which `pynecore` features should be bypassed rather than removed initially.
