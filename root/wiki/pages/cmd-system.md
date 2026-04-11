# CMD System

## What is CMD

CMD = typed container with logic. Not just a command call, but an object carrying:
- **op**: what to do
- **input**: what was passed
- **user**: who
- **scope**: which terminal
- **context**: arbitrary fields via dot-notation

## Template Commands

Python files in `root/templates/{type}/commands/{name}.py`

Signature: `def execute(args, user, scope, ws) -> dict`

Resolution: current node type -> schema.inherits -> ... -> None

Hot-reload: mtime-based, cached in memory

## Generic Strategies

| Strategy | What it does | Example |
|---|---|---|
| set | write value | edit message content |
| toggle | exists->remove, not->add | reaction by author |
| increment | counter++ | reaction count |
| find_or_create | find by key or create slot | reaction emoji slot |
| append | add to end of list | post message |

## ConsoleScope

Named terminal instances with own cwd, log, redo stack.
- `CMD` scope for user actions
- `channel:*` for channels
- `agent:*` for agents
