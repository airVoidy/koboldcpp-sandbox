# MCP-like Interface For Agents

This project exposes a small MCP-like JSON-RPC endpoint on top of the existing FastAPI server.

Base URL:

```text
http://127.0.0.1:8060/api/mcp
```

Alternative transport:

```text
stdio
```

Server start:

```powershell
kobold-sandbox serve --host 127.0.0.1 --port 8060
```

Or run a line-based stdio bridge:

```powershell
kobold-sandbox mcp-stdio
```

## Protocol Shape

Requests use JSON-RPC 2.0 envelopes:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

Responses return either `result` or `error`.

In `stdio` mode, each request must be one JSON line and each response is returned as one JSON line.

Supported methods:

- `initialize`
- `ping`
- `tools/list`
- `tools/call`

## Initialization

Call this first:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {}
}
```

Typical response:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2025-03-26",
    "serverInfo": {
      "name": "kobold-sandbox",
      "version": "0.1.0"
    },
    "capabilities": {
      "tools": {
        "listChanged": false
      }
    }
  }
}
```

## Available Tools

Current tools:

- `sandbox.graph`
- `sandbox.create_node`
- `sandbox.update_notes`
- `atoms.evaluate`
- `hypotheses.evaluate_connected`

Fetch schemas via `tools/list`:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/list",
  "params": {}
}
```

## Tool Call Format

Tool calls use:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "tool.name",
    "arguments": {}
  }
}
```

Successful tool responses are wrapped like this:

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{ ... pretty-printed json ... }"
      }
    ],
    "structuredContent": {},
    "isError": false
  }
}
```

If a tool-level validation/runtime problem happens, the server still returns `result`, but `isError` becomes `true`.

## Agent Flow

Recommended order:

1. `initialize`
2. `tools/list`
3. `tools/call` as needed

If you need sandbox graph or node mutation, initialize the sandbox first with the CLI:

```powershell
kobold-sandbox init --kobold-url http://localhost:5001
```

## Examples

### Evaluate One Atom

```json
{
  "jsonrpc": "2.0",
  "id": 10,
  "method": "tools/call",
  "params": {
    "name": "atoms.evaluate",
    "arguments": {
      "atom_id": "a1",
      "expression": "assert x == 2",
      "variables": ["x"],
      "context": {
        "x": 2
      }
    }
  }
}
```

### Read Sandbox Graph

```json
{
  "jsonrpc": "2.0",
  "id": 11,
  "method": "tools/call",
  "params": {
    "name": "sandbox.graph",
    "arguments": {}
  }
}
```

### Create Node

```json
{
  "jsonrpc": "2.0",
  "id": 12,
  "method": "tools/call",
  "params": {
    "name": "sandbox.create_node",
    "arguments": {
      "parent_id": "root",
      "title": "Japan report",
      "summary": "Need structured facts for a report",
      "tags": ["report", "japan"]
    }
  }
}
```

### Update Notes

```json
{
  "jsonrpc": "2.0",
  "id": 13,
  "method": "tools/call",
  "params": {
    "name": "sandbox.update_notes",
    "arguments": {
      "node_id": "japan-report",
      "content": "# Japan report\n\n## Goal\n\nCollect concise facts.\n"
    }
  }
}
```

### Connected Hypothesis Evaluation

Use `hypotheses.evaluate_connected` when an agent has already built:

- a list of hypotheses
- attached atoms
- a concrete context object

This tool is for local consistency checks and propagation over the connected component rooted at `start_hypothesis_id`.

## Local Demo Script

Ready-made host example:

[examples/mcp_host_demo.py](/C:/llm/KoboldCPP%20agentic%20sandbox/examples/mcp_host_demo.py)
[examples/mcp_host_demo.ps1](/C:/llm/KoboldCPP%20agentic%20sandbox/examples/mcp_host_demo.ps1)
[examples/mcp_stdio_smoke.ps1](/C:/llm/KoboldCPP%20agentic%20sandbox/examples/mcp_stdio_smoke.ps1)

Run it after the server is up:

```powershell
python examples\mcp_host_demo.py
```

Or with PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File examples\mcp_host_demo.ps1
```

For a stdio host, launch:

```powershell
kobold-sandbox mcp-stdio
```
