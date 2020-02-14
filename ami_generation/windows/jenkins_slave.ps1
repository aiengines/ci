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

# Adds the jenkins slave autoconnect script as a service


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
$AutoConnectScript = 'C:\run-auto-connect.bat'
$progressPreference = 'silentlyContinue'
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/ami_generation/windows/slave-autoconnect.py -OutFile C:\slave-autoconnect.py
Invoke-WebRequest -Uri https://raw.githubusercontent.com/aiengines/ci/master/ami_generation/windows/run-auto-connect.bat -OutFile $AutoConnectScript
$trigger = New-ScheduledTaskTrigger -AtStartup -RandomDelay 00:00:30
$action = New-ScheduledTaskAction -Execute $AutoConnectScript
$principal = New-ScheduledTaskPrincipal -UserID "NT AUTHORITY\SYSTEM" -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask "JenkinsAutoConnect" -Description "Connect to Jenkins at startup" -Action $action -Trigger $trigger -Principal $principal

# trigger userdata processing on next boot so jenkins slave settings get written
Check-Call { C:\ProgramData\Amazon\EC2-Windows\Launch\Scripts\InitializeInstance.ps1 -Schedule }
