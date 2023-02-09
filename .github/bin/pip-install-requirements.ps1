./emsdk.ps1 activate latest
Set-Location emscripten
Invoke-Expression "$env:EMSDK_PYTHON -m pip install --upgrade pip"
Invoke-Expression "$env:EMSDK_PYTHON -m pip install -r requirements-dev.txt"
