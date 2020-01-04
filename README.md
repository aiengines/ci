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
