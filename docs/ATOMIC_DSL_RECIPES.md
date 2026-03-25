# Atomic DSL Recipes

## Staged Continue + Derived Table Header

Flow:
- start with a user prompt
- seed assistant prefill
- continue until the answer is complete
- derive table columns from parsed constraints
- append the generated markdown header into the same assistant turn
- continue again with low temperature and a stop condition

```pipeline
@chat = "session"

set_text(@chat, user, $config.prompt)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")

@draft = generate(
  @chat,
  mode:continue,
  continue:true,
  temperature:0.6,
  max_tokens:2048
)

@claims = generate(
  $config.prompt_claims,
  worker:analyzer,
  input:$config.prompt,
  think:true
)

@constraints = parse_sections(
  @claims,
  entities:"ENTITIES:",
  axioms:"AXIOMS:",
  hypotheses:"HYPOTHESES:"
)

@cols = concat(@constraints.entities, @constraints.axioms)
@cols1 = prepend(@cols, "#")
@header = join(@cols1, sep:" | ", prefix:"| ", suffix:" |")
@n = len(@cols1)
@sep_cells = repeat("---", count:@n)
@sep = join(@sep_cells, sep:"|", prefix:"|", suffix:"|")
@table_head = lines(@header, @sep)

append_text(@chat, assistant, @draft.answer)
append_text(@chat, assistant, "\n\n")
append_text(@chat, assistant, @table_head)
append_text(@chat, assistant, "\n| 1 |")

@table = generate(
  @chat,
  mode:continue,
  continue:false,
  temperature:0.1,
  max_tokens:1024,
  stop:"\n\n\n"
)
```

## Chunk 2x2 Output

```pipeline
@answers = split(@draft.answer)
@answers_2x2 = chunk(@answers, size:2)

@checks = chunk(@constraints.hypotheses, size:2)
```

Sugar form:

```pipeline
@answers_2x2 = reshape_grid(@draft.answer, cols:2)
@checks_2x2 = reshape_grid(@constraints.hypotheses, cols:2)
```

## Probe After Draft

```pipeline
@chat = "session"
set_text(@chat, user, $config.prompt)
set_text(@chat, assistant, "<think>\n\n</think>\n\n")

@draft = generate(@chat, mode:continue, continue:true)

append_text(@chat, assistant, @draft.answer)
append_text(@chat, assistant, "\n\nCheck whether all looks are really distinct. Answer yes/no.")

@probe = generate(
  @chat,
  mode:probe_continue,
  continue:false,
  temperature:0.1,
  max_tokens:16,
  stop:"\n",
  capture:"yes|no"
)
```

## Accepted And Rejected

```pipeline
@parsed = parse_table(@table)
@rows = row_count(@parsed)
@labels = get_column(@parsed, "prompt")
@row_items = split_rows(@parsed, "prompt")

@accepted = accepted_list(@table, checks:@constraints.axioms)
@accepted_rows = filter_rows(@table, where:all_yes, checks:@constraints.axioms)
@rejected = reject_reasons(@table, checks:@constraints.axioms)
```

## Continue Until Row Target

```pipeline
@parsed = parse_table(@table)
@rows = row_count(@parsed)
@need_more = lt(@rows, $config.target_rows)

loop(while:@need_more, max_iters:4) {
  append_text(@chat, assistant, @table.answer)
  @table = generate(
    @chat,
    mode:continue,
    continue:false,
    temperature:0.1,
    max_tokens:1024,
    stop:"\n\n\n"
  )
  @parsed = parse_table(@table)
  @rows = row_count(@parsed)
  @need_more = lt(@rows, $config.target_rows)
}
```

## Parallel Answer + Constraints Verdict

Recommended config seeds:
- `$config.prompt_answer_table_rows`
- `$config.prompt_constraints_strict`
- `$config.target_rows`
- `$config.max_table_iters`
- `$config.hypothesis_cols`

Seeded macro:

```text
/run_macro(parallel_answer_constraints_verdict)
```

What it does:
- starts answer generation and analyzer constraints in parallel
- waits for constraints before building the markdown answer table header
- continues the answer table until `row_count(@parsed) >= $config.target_rows` or loop limit
- derives `accepted`, `accepted_rows`, and `rejected`

Main outputs:
- `@constraints`
- `@table_text`
- `@parsed`
- `@accepted`
- `@accepted_rows`
- `@rejected`

## Hypothesis Verdict Table

Seeded macro:

```text
/run_macro(hypothesis_verdict_table)
```

What it does:
- generates strict constraints first
- builds a separate markdown table from `@constraints.hypotheses`
- continues until the hypothesis table has 2 rows or loop limit

Main outputs:
- `@constraints`
- `@hyp_table_text`
- `@hyp_parsed`
- `@hyp_rows`

## Notes

- `set_text` replaces one message field
- `append_text` mutates the same message history
- `mode:continue` is for normal continuation
- `mode:probe_continue` is for short probes, captures, and gated checks
- pure transforms let you build headers, separators, small grids, and accepted/rejected summaries without bespoke tools
