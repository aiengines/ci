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
    $lastexitcode = 0
    & @ScriptBlock
    if (($lastexitcode -ne 0)) {
    Write-Error "Execution failed with $lastexitcode"
        exit $lastexitcode
    }
}
Set-ExecutionPolicy Bypass -Scope Process -Force


Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0	
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0	
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force	
Install-Module -Force OpenSSHUtils -Scope AllUsers	
Set-Service -Name ssh-agent -StartupType 'Automatic'	
Set-Service -Name sshd -StartupType 'Automatic'	
Start-Service ssh-agent	
Start-Service sshd	
Check-Call { cd C:\Users\Administrator }
$progressPreference = 'silentlyContinue'
Invoke-WebRequest -Uri https://cygwin.com/setup-x86_64.exe -OutFile setup-x86_64.exe
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/setup.ps1 -OutFile setup.ps1
Check-Call { .\setup-x86_64.exe --site http://cygwin.mirror.constant.com --quiet-mode --root "C:\cygwin64" --local-package-dir "C:\Users\Administrator" --verbose --prune-install --packages openssh,git,rsync,vim,python3 }
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/windows_deps_headless_installer.py -OutFile windows_deps_headless_installer.py
Invoke-WebRequest -Uri https://windows-post-install.s3-us-west-2.amazonaws.com/windows.zip -OutFile windows.zip
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/requirements.txt -OutFile requirements.txt
Expand-Archive -LiteralPath .\windows.zip	Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/jenkins_slave.ps1 -OutFile jenkins_slave.ps1
Invoke-WebRequest -Uri "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US" -OutFile ffox.exe	
Check-Call { .\ffox.exe /n /s }
