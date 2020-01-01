$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
function Check-Call {
    param (
        [scriptblock]$ScriptBlock
    )
    Write-Host "Executing $ScriptBlock"
    & @ScriptBlock
    if (($lastexitcode -ne 0)) {
	Write-Error "Execution failed with $lastexitcode"
        exit $lastexitcode
    }
}
Set-ExecutionPolicy Bypass -Scope Process -Force
Invoke-WebRequest -Uri https://chocolatey.org/install.ps1 -OutFile install.ps1
./install.ps1
Check-Call { C:\ProgramData\chocolatey\choco install python2 -y }
Check-Call { C:\ProgramData\chocolatey\choco install python --version=3.7.0 --force -y }
Check-Call { C:\Python37\python -m pip install --upgrade pip  }
Check-Call { C:\Python37\python -m pip install -r requirements.txt  }
Check-Call { C:\Python27\python -m pip install --upgrade pip  }
Check-Call { C:\Python27\python -m pip install -r requirements.txt  }
# Deps
Check-Call { C:\Python37\python  windows_deps_headless_installer.py }
Write-Output "End"
