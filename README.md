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

