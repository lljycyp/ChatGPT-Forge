param(
  [string]$OutputPath = (Join-Path $PSScriptRoot "..\assets\app.ico")
)

Add-Type -AssemblyName System.Drawing

$sourcePath = Join-Path $PSScriptRoot "..\src\renderer\src\assets\codex-forge-logo.png"
$source = [System.Drawing.Bitmap]::FromFile((Resolve-Path $sourcePath))
$sizes = @(16, 20, 24, 32, 40, 48, 64, 128, 256)
$crop = New-Object System.Drawing.RectangleF(127, 123, 1000, 1000)
$images = New-Object System.Collections.Generic.List[byte[]]

try {
  foreach ($size in $sizes) {
    $bitmap = New-Object System.Drawing.Bitmap(
      $size,
      $size,
      [System.Drawing.Imaging.PixelFormat]::Format32bppArgb
    )

    try {
      $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
      try {
        $graphics.Clear([System.Drawing.Color]::Transparent)
        $graphics.CompositingMode = [System.Drawing.Drawing2D.CompositingMode]::SourceCopy
        $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
        $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
        $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
        $graphics.DrawImage(
          $source,
          (New-Object System.Drawing.RectangleF(0, 0, $size, $size)),
          $crop,
          [System.Drawing.GraphicsUnit]::Pixel
        )
      }
      finally {
        $graphics.Dispose()
      }

      $stream = New-Object System.IO.MemoryStream
      try {
        $bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Png)
        $images.Add($stream.ToArray())
      }
      finally {
        $stream.Dispose()
      }
    }
    finally {
      $bitmap.Dispose()
    }
  }
}
finally {
  $source.Dispose()
}

$output = [System.IO.File]::Create([System.IO.Path]::GetFullPath($OutputPath))
$writer = New-Object System.IO.BinaryWriter($output)

try {
  $writer.Write([uint16]0)
  $writer.Write([uint16]1)
  $writer.Write([uint16]$sizes.Count)

  $offset = 6 + (16 * $sizes.Count)
  for ($index = 0; $index -lt $sizes.Count; $index++) {
    $size = $sizes[$index]
    $image = $images[$index]
    $iconSize = if ($size -eq 256) { 0 } else { $size }
    $writer.Write([byte]$iconSize)
    $writer.Write([byte]$iconSize)
    $writer.Write([byte]0)
    $writer.Write([byte]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]32)
    $writer.Write([uint32]$image.Length)
    $writer.Write([uint32]$offset)
    $offset += $image.Length
  }

  foreach ($image in $images) {
    $writer.Write($image)
  }
}
finally {
  $writer.Dispose()
  $output.Dispose()
}
