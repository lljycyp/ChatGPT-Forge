[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$Source,
  [Parameter(Mandatory = $true)][string]$Target,
  [Parameter(Mandatory = $true)][string]$Marker
)

$ErrorActionPreference = "Stop"
$sourcePath = [System.IO.Path]::GetFullPath($Source).TrimEnd('\')
$targetPath = [System.IO.Path]::GetFullPath($Target).TrimEnd('\')
$markerPath = [System.IO.Path]::GetFullPath($Marker)

foreach ($path in @($sourcePath, $targetPath, $markerPath)) {
  if ($path -eq [System.IO.Path]::GetPathRoot($path)) {
    throw "拒绝使用磁盘根目录: $path"
  }
}

while ($true) {
  $running = Get-CimInstance Win32_Process -Filter "Name='ChatGPT.exe'" | Where-Object {
    $_.ExecutablePath -and $_.ExecutablePath.StartsWith(
      $sourcePath + '\',
      [System.StringComparison]::OrdinalIgnoreCase
    )
  }
  if (!$running) {
    break
  }
  Start-Sleep -Seconds 2
}

if (Test-Path -LiteralPath $targetPath) {
  $targetItem = Get-Item -LiteralPath $targetPath -Force
  if ($targetItem.LinkType -ne "Junction") {
    throw "便携客户端目标不是预期的临时 Junction: $targetPath"
  }
  [System.IO.Directory]::Delete($targetPath)
}

if (!(Test-Path -LiteralPath $sourcePath)) {
  throw "便携客户端源目录不存在: $sourcePath"
}

Move-Item -LiteralPath $sourcePath -Destination $targetPath
if (!(Test-Path -LiteralPath (Join-Path $targetPath "ChatGPT.exe"))) {
  throw "便携客户端迁移后入口不存在: $targetPath"
}

"completedAt=$((Get-Date).ToString('o'))" | Set-Content -LiteralPath $markerPath -Encoding utf8
