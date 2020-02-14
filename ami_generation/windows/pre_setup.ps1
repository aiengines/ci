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

Check-Call { cd C:\Users\Administrator }
$progressPreference = 'silentlyContinue'
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/setup.ps1 -OutFile setup.ps1
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/windows_deps_headless_installer.py -OutFile windows_deps_headless_installer.py
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/requirements.txt -OutFile requirements.txt
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/windows/jenkins_slave.ps1 -OutFile jenkins_slave.ps1
reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced /v HideFileExt /t REG_DWORD /d 0 /f
Write-Output "All Done"
