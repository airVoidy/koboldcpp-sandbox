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

## Notes

- `set_text` replaces one message field
- `append_text` mutates the same message history
- `mode:continue` is for normal continuation
- `mode:probe_continue` is for short probes, captures, and gated checks
- pure transforms let you build headers, separators, and small grids without bespoke tools
