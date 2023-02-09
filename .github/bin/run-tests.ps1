./emsdk.ps1 activate latest
Set-Location emscripten
Invoke-Expression "$env:EMSDK_PYTHON .\test\runner.py ${args[0]} --failfast"
