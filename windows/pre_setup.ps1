# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.



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

Check-Call { Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 }
Check-Call { Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0. }
Check-Call { Install-Module -Force OpenSSHUtils -Scope AllUsers }
Check-Call { Set-Service -Name ssh-agent -StartupType ‘Automatic’ }
Check-Call { Set-Service -Name sshd -StartupType ‘Automatic’ }
Check-Call { Start-Service ssh-agent }
Check-Call { Start-Service sshd }
Check-Call { cd C:\Users\Administrator }
Check-Call { $progressPreference = 'silentlyContinue' }
Check-Call { Invoke-WebRequest -Uri https://cygwin.com/setup-x86_64.exe -OutFile setup-x86_64.exe }
Check-Call { .\setup-x86_64.exe --site http://cygwin.mirror.constant.com --quiet-mode --root "C:\cygwin64" --local-package-dir "C:\Users\Administrator" --verbose --prune-install --packages openssh,git,rsync,vim,python3 }
Check-Call { Invoke-WebRequest -Uri https://windows-post-install.s3-us-west-2.amazonaws.com/windows.zip -OutFile windows.zip }
Check-Call { Expand-Archive -LiteralPath .\windows.zip }
Check-Call { Invoke-WebRequest -Uri "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US" -OutFile ffox.exe }
Check-Call { .\ffox.exe /n /s }
Check-Call { reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced /v HideFileExt /t REG_DWORD /d 0 /f }
Write-Output "All Done"
