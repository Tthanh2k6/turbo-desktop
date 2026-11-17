# Rebuild the test fixtures (needs .NET Framework csc.exe, present on every Windows 10/11)
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
Set-Location $PSScriptRoot
foreach ($n in "fixture","editor","canvas") {
  & $csc /nologo /target:winexe /out:"turbo_$n.exe" /r:System.Windows.Forms.dll /r:System.Drawing.dll "$n.cs"
}
