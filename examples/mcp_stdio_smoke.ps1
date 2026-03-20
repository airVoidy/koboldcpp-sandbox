$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = "python"
$psi.Arguments = "-m kobold_sandbox.cli mcp-stdio"
$psi.WorkingDirectory = (Get-Location).Path
$psi.UseShellExecute = $false
$psi.RedirectStandardInput = $true
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true

$process = New-Object System.Diagnostics.Process
$process.StartInfo = $psi
$process.Start() | Out-Null

try {
  $requests = @(
    @{
      jsonrpc = "2.0"
      id = 1
      method = "initialize"
      params = @{}
    },
    @{
      jsonrpc = "2.0"
      id = 2
      method = "tools/list"
      params = @{}
    },
    @{
      jsonrpc = "2.0"
      id = 3
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
    }
  )

  Write-Host ""
  Write-Host "== stdout =="

  foreach ($request in $requests) {
    $line = $request | ConvertTo-Json -Depth 10 -Compress
    $process.StandardInput.WriteLine($line)
    $process.StandardInput.Flush()
    $response = $process.StandardOutput.ReadLine()
    if ($null -ne $response) {
      Write-Host $response
    }
  }

  $process.StandardInput.Close()
  $process.WaitForExit()

  $stderr = $process.StandardError.ReadToEnd()
  if ($stderr) {
    Write-Host ""
    Write-Host "== stderr =="
    Write-Host $stderr
  }
}
finally {
  if (-not $process.HasExited) {
    $process.Kill()
  }
  $process.Dispose()
}
