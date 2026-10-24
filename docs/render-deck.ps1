# Renders every slide of a .pptx to PNG using the installed PowerPoint (COM) for visual QA.
#   pwsh docs/render-deck.ps1 docs/AwaazAlert-VecnaVerse.pptx
param([Parameter(Mandatory = $true)][string]$Deck)
$deck = (Resolve-Path $Deck).Path
$outDir = Join-Path (Split-Path $deck) 'deck-render'
New-Item -ItemType Directory -Force $outDir | Out-Null
Get-ChildItem $outDir -Filter '*.png' -ErrorAction SilentlyContinue | Remove-Item -Force
$pp = New-Object -ComObject PowerPoint.Application
$pp.Visible = -1   # msoTrue; some builds refuse to open invisibly
try {
  $pres = $pp.Presentations.Open($deck, -1, 0, -1)   # ReadOnly, Untitled=false, WithWindow
  $i = 1
  foreach ($slide in $pres.Slides) {
    $png = Join-Path $outDir ("slide-{0}.png" -f $i)
    $slide.Export($png, 'PNG', 1920, 1080)
    Write-Output $png
    $i++
  }
  $pres.Close()
} finally {
  $pp.Quit()
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($pp) | Out-Null
}
