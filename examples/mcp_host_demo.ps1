$baseUrl = "http://127.0.0.1:8060/api/mcp"

function Invoke-McpRpc {
  param(
    [string]$Method,
    [hashtable]$Params = @{},
    [int]$Id = 1
  )

  $body = @{
    jsonrpc = "2.0"
    id = $Id
    method = $Method
    params = $Params
  } | ConvertTo-Json -Depth 10

  Invoke-RestMethod `
    -Method Post `
    -Uri $baseUrl `
    -ContentType "application/json" `
    -Body $body
}

function Show-Json {
  param(
    [string]$Title,
    $Payload
  )

  Write-Host ""
  Write-Host "== $Title =="
  $Payload | ConvertTo-Json -Depth 10
}

$init = Invoke-McpRpc -Method "initialize" -Id 1
Show-Json -Title "initialize" -Payload $init

$tools = Invoke-McpRpc -Method "tools/list" -Id 2
Show-Json -Title "tools/list" -Payload $tools

$atom = Invoke-McpRpc -Method "tools/call" -Id 3 -Params @{
  name = "atoms.evaluate"
  arguments = @{
    atom_id = "a1"
    expression = "assert x == 2"
    variables = @("x")
    context = @{
      x = 2
    }
  }
}
Show-Json -Title "atoms.evaluate" -Payload $atom

$graph = Invoke-McpRpc -Method "tools/call" -Id 4 -Params @{
  name = "sandbox.graph"
  arguments = @{}
}
Show-Json -Title "sandbox.graph" -Payload $graph

$created = Invoke-McpRpc -Method "tools/call" -Id 5 -Params @{
  name = "sandbox.create_node"
  arguments = @{
    parent_id = "root"
    title = "Japan report"
    summary = "Need structured facts for the report"
    tags = @("report", "japan")
  }
}
Show-Json -Title "sandbox.create_node" -Payload $created

$nodeId = $created.result.structuredContent.id

$updated = Invoke-McpRpc -Method "tools/call" -Id 6 -Params @{
  name = "sandbox.update_notes"
  arguments = @{
    node_id = $nodeId
    content = "# Japan report`n`n## Goal`n`nCollect concise facts.`n"
  }
}
Show-Json -Title "sandbox.update_notes" -Payload $updated
