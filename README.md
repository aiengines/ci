# ci

![codebuild](https://codebuild.us-west-2.amazonaws.com/badges?uuid=eyJlbmNyeXB0ZWREYXRhIjoiR1B3bFJzMDhiZjF1czRiUG5zM0xIYkxaS3pPMFQxRXNDWURJcWhocmFmNWxHc1BJK1paWElqK3BkQ0JkbXZGYjd5K0cwWGxOYjh1RGFTMnRSUzVTU0pVPSIsIml2UGFyYW1ldGVyU3BlYyI6ImVGRnJLN2QrQzdhR1Q1a08iLCJtYXRlcmlhbFNldFNlcmlhbCI6MX0%3D&branch=master)


# Windows environment setup
Steps undertaken for **_Windows CI AMI creation_**.
Pre-requisite - AWS CLI is installed and configured.

## Step 1 : Get AMI id

```
aws ssm get-parameter --name /aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base
```
## Step 2 : Instance Creation
#### Choose AMI
Use AMI ID from Step 1

#### Choose Instance Type
Nothing specific. Can choose P2 instance

#### Configure Instance
Add user data while creating instance (Configure Instance -> User Data) as follows

##### User data

```
<powershell>
cd C:\Users\Administrator
$progressPreference = 'silentlyContinue'
Invoke-WebRequest -Uri https://cygwin.com/setup-x86_64.exe -OutFile setup-x86_64.exe
.\setup-x86_64.exe --site http://cygwin.mirror.constant.com --quiet-mode --root "C:\cygwin64" --local-package-dir "C:\Users\Administrator" --verbose --prune-install --packages openssh,git,rsync,vim,python3
Invoke-WebRequest -Uri https://windows-post-install.s3-us-west-2.amazonaws.com/windows.zip -OutFile windows.zip
Expand-Archive -LiteralPath .\windows.zip
Invoke-WebRequest -Uri "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US" -OutFile ffox.exe
.\ffox.exe /n /s
reg add HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced /v HideFileExt /t REG_DWORD /d 0 /f
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Force
Install-Module -Force OpenSSHUtils -Scope AllUsers
Set-Service -Name ssh-agent -StartupType 'Automatic'
Set-Service -Name sshd -StartupType 'Automatic'
Start-Service ssh-agent
Start-Service sshd
</powershell>
```

#### Add storage
200Gig storage
#### Security Group
Select an existing security group
Choose both : AWS RDP and AWS SSH

## Step 3 : Instance steps
Using Microsoft Remote Desktop, connect to the remote instance.
In a powershell prompt execute

```
Set-ExecutionPolicy Bypass -Scope Process -Force
./setup.ps1
```

## Step 4 : Create AMI with base dependencies

Stop the instance.
Create Amazon Machine Image out of the instance (Windows GPU Updated Deps AMI)
Refer : https://docs.aws.amazon.com/toolkit-for-visual-studio/latest/user-guide/tkv-create-ami-from-instance.html

## Step 5 : Launch instance with Base AMI

Upon launching the p2 instance using the base AMI (username password same as 1 used for creating base AMI)
Clone the repo and build for windows :
```
git clone -b windows_builds --recursive https://github.com/larroy/mxnet.git
python .\ci\build_windows.py
```

## Step 6 : Create the Windows GPU Jenkins AMI
It differs from the previous AMI as it has base AMI + Jenkins Slave autoconnect.

Restart the stopped instance
```
./jenkins_slave.ps1
```
Create Amazon Machine Image (just like Step 4)

## Step 7 : Test
To Do: Add step to update the CI Infra on AWS to pick the updated AMI.
For testing, run a job (windows GPU in this case) on Jenkins CI Dev.

CUDA 10.2:
http://developer.download.nvidia.com/compute/cuda/10.2/Prod/network_installers/cuda_10.2.89_win10_network.exe
