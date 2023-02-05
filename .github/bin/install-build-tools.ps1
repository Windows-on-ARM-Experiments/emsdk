Remove-Item -Force -Path .\vs_buildtools.exe -ErrorAction Ignore
Invoke-WebRequest -Uri https://aka.ms/vs/17/pre/vs_buildtools.exe -OutFile .\vs_buildtools.exe

$process = Start-Process -FilePath .\vs_buildtools.exe -ArgumentList "--update --quiet --wait --norestart --nocache" -NoNewWindow -PassThru -Wait
$exitCode = $process.ExitCode
if (($exitCode -ne 0) -and ($exitCode -ne 3010)) {
    Write-Output "Visual Studio installer exited with code $exitCode, which should be one of [0, 3010]."
    exit 1
}

Write-Output "Visual Studio Build Tools installer updated"

$process = Start-Process -FilePath .\vs_buildtools.exe -ArgumentList "update --quiet --wait --norestart --nocache --add Microsoft.Component.MSBuild --add Microsoft.VisualStudio.Component.VC.Tools.ARM64" -NoNewWindow -PassThru -Wait
$exitCode = $process.ExitCode
if (($exitCode -ne 0) -and ($exitCode -ne 3010)) {
    Write-Output "Visual Studio installer exited with code $exitCode, which should be one of [0, 3010]."
    exit 1
}

Write-Output "Visual Studio Build Tools installed"
