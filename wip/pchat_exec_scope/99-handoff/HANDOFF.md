# New Chat Handoff

## Goal

Continue the `pipeline-chat` rebuild from documentation first.

Do not keep repairing the old mixed implementation.

## Canonical Docs

Read in this order:

1. [README.md](C:\llm\KoboldCPP agentic sandbox\wip\pchat_exec_scope\README.md)
2. [ARCHITECTURE.md](C:\llm\KoboldCPP agentic sandbox\wip\pchat_exec_scope\01-foundation\ARCHITECTURE.md)
3. [DATA_MODEL.md](C:\llm\KoboldCPP agentic sandbox\wip\pchat_exec_scope\02-model\DATA_MODEL.md)
4. [COMMAND_MODEL.md](C:\llm\KoboldCPP agentic sandbox\wip\pchat_exec_scope\03-runtime\COMMAND_MODEL.md)
5. [IMPLEMENTATION_PLAN.md](C:\llm\KoboldCPP agentic sandbox\wip\pchat_exec_scope\99-handoff\IMPLEMENTATION_PLAN.md)

## What Was Learned

- current codebase is a mixed migration state
- template schemas already describe domain commands
- template command implementations are missing in places
- server hardcode was compensating for missing template logic
- that compensation made the system hard to reason about

## Hard Invariants

- one user action = one `exec()`
- `exec()` / `exec_batch()` are the only mutation boundaries
- no duplicated truth values
- server entities and client entities are separate layers
- projections are object-to-object
- no domain-specific mutation endpoints
- no `view/materialize` in the user action path

## Do Next

1. do not patch old `pipeline-chat` further unless strictly needed for reference
2. build new generic exec runtime in a separate path
3. make template-driven commands the only domain command layer
4. keep `server.py` generic
5. use refs and projections from the start

## Do Not Do

- do not add new chat-specific `cmd_*` handlers into `server.py`
- do not rebuild around legacy `current_channel_messages`
- do not mix client cache with truth
- do not use HTTP patch/view helpers as the main action path

## Legacy Branch Context

The old working-ish area was around `7f107e61`, but it was already mixed.

Useful only as reference:

- atomic patch patterns
- localStorage shape
- git/sandbox relation hints

Not safe as direct architecture source.
