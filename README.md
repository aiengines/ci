# ci



# Windows environment setup

Get AMI id:

```
aws ssm get-parameter --name /aws/service/ami-windows-latest/Windows_Server-2019-English-Full-Base
```

In a powershell prompt execute

```
Set-ExecutionPolicy Bypass -Scope Process -Force
./setup.ps1
```



CUDA 10.2:
http://developer.download.nvidia.com/compute/cuda/10.2/Prod/network_installers/cuda_10.2.89_win10_network.exe


## User data

```

<powershell>
$progressPreference = 'silentlyContinue'
cd c:\Users\Administrator
Invoke-WebRequest -Uri https://windows-post-install.s3-us-west-2.amazonaws.com/windows.zip -OutFile windows.zip
Expand-Archive -LiteralPath .\windows.zip
Invoke-WebRequest -Uri "https://download.mozilla.org/?product=firefox-latest-ssl&os=win64&lang=en-US" -OutFile ffox.exe
.\ffox.exe /n /s
Invoke-WebRequest -Uri https://cygwin.com/setup-x86_64.exe -OutFile setup-x86_64.exe
.\setup-x86_64.exe --site http://cygwin.mirror.constant.com --quiet-mode --root "C:\cygwin64" --local-package-dir "C:\Users\Administrator" --verbose --prune-install --packages openssh,git,rsync,vim,python3
</powershell>

```



