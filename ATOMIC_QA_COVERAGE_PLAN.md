# Atomic QA Coverage Plan

## Goal

List which artifacts in the current example should eventually be produced from:

- deterministic parsing
- atomic QA prompts with only `yes/no` or one-word answers

The rule is:

- LLM fills tiny fields
- local code assembles structure

## Coverage Targets

### Can Be Mostly Deterministic

- source text storage
- token index
- sentence splitting
- enumerated condition extraction
- basic fragment splitting by obvious markers
- initial bucket dispatch by regex/keyword rules
- object/relation/claim id generation
- JSON assembly

### Should Be Produced By Atomic QA

- does this fragment contain ordering? `yes/no`
- which ordering marker? `after|before|earlier|later|none`
- does this fragment contain adjacency? `yes/no`
- does this fragment contain negation? `yes/no`
- does this fragment contain either/or choice? `yes/no`
- is this fragment structural? `yes/no`
- is this fragment an observation? `yes/no`
- is this fragment direct text or interpretation? `direct|light|strong`
- is this phrase a role mention? `yes/no`
- what role type is it? `author|visitor|unknown`
- does this object belong to this group? `yes/no`
- is this crosscheck wrong? `yes/no`

### Should Stay In Code, Not In LLM

- id assignment
- crossref wiring
- source_ref assembly
- merge of multiple QA answers
- anomaly list generation
- conflict aggregation
- deduplication

## Current Example Files And Intended Production Mode

- `source_text.md` -> deterministic
- `source_tokens_v0.json` -> deterministic
- `sentences_v0.json` -> deterministic first, QA refinement later
- `fragments_v0.json` -> deterministic first, QA refinement later
- `raw_claims.json` -> mixed
- `relation_buckets_v0.md` -> deterministic first, QA refinement later
- `objects/*.json` -> deterministic skeleton + QA enrichment
- `relations/*.json` -> deterministic skeleton + QA confirmation
- `claims/*.json` -> deterministic assembly
- `roles_v0.json` -> QA-assisted
- `questions_v0.json` -> deterministic + templated negative generation
- `crosschecks_v0.json` -> deterministic question generation, QA answers
- `anomalies_v0.json` -> code-generated from contradictions and warnings

## Minimal Atomic QA Sets

### Set A: Relation Detection

- `has_ordering`
- `has_adjacency`
- `has_choice`
- `has_negation`
- `has_structural`
- `has_observation`
- `has_role_mention`

### Set B: Tiny Labels

- `ordering_marker`
- `role_type`
- `observation_or_constraint`
- `interpretation_level`

### Set C: Crosschecks

- `member_of?`
- `includes_member?`
- `count_of?`
- `same_chunk?`

## MVP Recommendation

First build the deterministic parser.

Then layer only the smallest QA set on top:

1. `same_chunk`
2. `has_ordering`
3. `has_adjacency`
4. `has_choice`
5. `has_negation`
6. `has_structural`
7. `has_role_mention`
8. `interpretation_level`

That is enough to start turning example data into reproducible structured outputs.
