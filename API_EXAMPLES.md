# API Examples

Текущие примеры для локального API `kobold-sandbox`.

Предполагается, что сервер поднят так:

```powershell
kobold-sandbox serve --host 127.0.0.1 --port 8060
```

## MCP-like Initialize

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 1
  method = "initialize"
  params = @{}
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/api/mcp" `
  -ContentType "application/json" `
  -Body $body
```

## MCP-like Tools List

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 2
  method = "tools/list"
  params = @{}
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/api/mcp" `
  -ContentType "application/json" `
  -Body $body
```

## MCP-like Tool Call: Create Node

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 3
  method = "tools/call"
  params = @{
    name = "sandbox.create_node"
    arguments = @{
      parent_id = "root"
      title = "Japan report"
      summary = "Need structured facts for a report"
      tags = @("report", "japan")
    }
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/api/mcp" `
  -ContentType "application/json" `
  -Body $body
```

## MCP-like Tool Call: Update Notes

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 4
  method = "tools/call"
  params = @{
    name = "sandbox.update_notes"
    arguments = @{
      node_id = "japan-report"
      content = "# Japan report`n`n## Goal`n`nCollect concise facts."
    }
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/api/mcp" `
  -ContentType "application/json" `
  -Body $body
```

## MCP-like Tool Call: Evaluate Atom

```powershell
$body = @{
  jsonrpc = "2.0"
  id = 5
  method = "tools/call"
  params = @{
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
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/api/mcp" `
  -ContentType "application/json" `
  -Body $body
```

## Health

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8060/health"
```

## Graph

```powershell
Invoke-RestMethod `
  -Method Get `
  -Uri "http://127.0.0.1:8060/graph"
```

## Create Node

```powershell
$body = @{
  parent_id = "root"
  title = "house-1-red-hypothesis"
  summary = "Check whether the first house is red"
  tags = @("einstein", "color", "hypothesis")
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/nodes" `
  -ContentType "application/json" `
  -Body $body
```

## Run Node Task

```powershell
$body = @{
  task = "Check the hypothesis and list contradictions"
  model = $null
  commit = $false
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/nodes/house-1-red-hypothesis/run" `
  -ContentType "application/json" `
  -Body $body
```

## Evaluate Single Atom

Пример атомарной проверки гипотезы `house-1:red=yes`.

```powershell
$body = @{
  atom_id = "house-1-red-yes"
  expression = "assert einstein_color_cell['house-1:red'] == 'yes'"
  variables = @("einstein_color_cell")
  source_claim_id = "house-1__red__yes"
  context = @{
    einstein_color_cell = @{
      "house-1:red" = "yes"
    }
  }
} | ConvertTo-Json -Depth 6

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/atoms/evaluate" `
  -ContentType "application/json" `
  -Body $body
```

Пример ответа:

```json
{
  "atom_id": "house-1-red-yes",
  "passed": true,
  "variables": ["einstein_color_cell"],
  "source_claim_id": "house-1__red__yes",
  "error": null
}
```

## Evaluate Batch

Пример пачки атомов для одной таблицы.

```powershell
$body = @{
  atoms = @(
    @{
      atom_id = "house-1-red-yes"
      expression = "assert einstein_color_cell['house-1:red'] == 'yes'"
      variables = @("einstein_color_cell")
      source_claim_id = "house-1__red__yes"
    },
    @{
      atom_id = "house-1-blue-no"
      expression = "assert einstein_color_cell['house-1:blue'] == 'no'"
      variables = @("einstein_color_cell")
      source_claim_id = "house-1__blue__no"
    }
  )
  context = @{
    einstein_color_cell = @{
      "house-1:red" = "yes"
      "house-1:blue" = "no"
    }
  }
} | ConvertTo-Json -Depth 8

Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8060/atoms/evaluate-batch" `
  -ContentType "application/json" `
  -Body $body
```

## Reactive Step Pattern

Рекомендуемый цикл на один шаг:

1. UI или скрипт меняет одну или несколько ячеек-кандидатов в локальном контексте.
2. Вызывает `/atoms/evaluate-batch` для связанных атомов.
3. Собирает:
   - `passed`
   - `failed`
   - новые `fixed` значения
4. Если достигнута saturation и появились новые фиксированные значения:
   - записывает изменения в таблицы/notes
   - делает git commit в текущей ветке
5. После этого запускается следующий шаг рассуждения или новая гипотеза.

## Notes

- Сейчас API проверяет атомы по переданному `context`.
- Это runtime для быстрой локальной валидации без полного solver pass.
- Следующий естественный слой: dependency graph + propagation.
