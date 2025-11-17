# dev.ps1 - Development tools wrapper for Windows

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet('format', 'check', 'mypy', 'lint', 'clean', 'install', 'install-dev', 'help')]
    [string]$Command
)

function Show-Help {
    Write-Host "Available commands:" -ForegroundColor Cyan
    Write-Host "  .\dev.ps1 install       - Install production dependencies"
    Write-Host "  .\dev.ps1 install-dev   - Install development dependencies"
    Write-Host "  .\dev.ps1 format        - Format code with black"
    Write-Host "  .\dev.ps1 check         - Check code formatting"
    Write-Host "  .\dev.ps1 mypy          - Run mypy type checker"
    Write-Host "  .\dev.ps1 lint          - Run all linters"
    Write-Host "  .\dev.ps1 clean         - Remove cache files"
}

function Install-Deps {
    Write-Host "Installing production dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
}

function Install-DevDeps {
    Write-Host "Installing all dependencies..." -ForegroundColor Green
    pip install -r requirements.txt
    pip install -r requirements-dev.txt
}

function Format-Code {
    Write-Host "Formatting code with black..." -ForegroundColor Green
    black fx_translator/ main.py
}

function Check-Format {
    Write-Host "Checking code formatting..." -ForegroundColor Green
    black --check fx_translator/ main.py
}

function Run-Mypy {
    Write-Host "Running mypy type checker..." -ForegroundColor Green
    mypy --explicit-package-bases fx_translator/ main.py
}

function Run-Lint {
    Write-Host "Running all linters..." -ForegroundColor Green
    Check-Format
    if ($LASTEXITCODE -eq 0) {
        Run-Mypy
        if ($LASTEXITCODE -eq 0) {
            Write-Host "All checks passed!" -ForegroundColor Green
        }
    }
}

function Clean-Cache {
    Write-Host "Cleaning cache files..." -ForegroundColor Green
    Get-ChildItem -Recurse -Filter '__pycache__' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Filter '.mypy_cache' | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Recurse -Filter '*.pyc' | Remove-Item -Force -ErrorAction SilentlyContinue
    Write-Host "Cache cleaned!" -ForegroundColor Green
}

switch ($Command) {
    'install'     { Install-Deps }
    'install-dev' { Install-DevDeps }
    'format'      { Format-Code }
    'check'       { Check-Format }
    'mypy'        { Run-Mypy }
    'lint'        { Run-Lint }
    'clean'       { Clean-Cache }
    'help'        { Show-Help }
}
