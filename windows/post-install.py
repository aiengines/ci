"""Dependency installer for Windwos"""
import argparse
import errno
import logging
import os
import psutil
import requests
import shutil
import subprocess
import stat
import tempfile
import zipfile
from time import sleep

# PATHs for dependencies
# C:\Program Files (x86)\Microsoft Visual Studio 14.0
# C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v9.2
# C:\Program Files\OpenBLAS-v0.2.19
# C:\Program Files (x86)\IntelSWTools
# C:\Program Files\OpenCV-v3.4.1
# C:\Program Files\CMake\bin
# C:\Program Files\Git\bin

# Takes url and downloads it to the dest_path directory on Windows.
def download_file(url, dest_path):
    file_name = url.split('/')[-1]
    full_path = "{}\\{}".format(dest_path, file_name)
    logging.info("Downloading: {}".format(full_path))
    r = requests.get(url, stream=True)
    if r.status_code == 404:
        return r.status_code
    elif r.status_code != 200:
        logging.error("{} returned status code {}".format(url, r.status_code))
    with open(full_path, 'wb') as f:
        for chunk in r.iter_content(chunk_size=1024):
            if chunk: # filter out keep-alive new chunks
                f.write(chunk)
    return full_path

# Takes arguments and runs command on host.  Shell is disabled by default.
# TODO: Move timeout to args
def run_command(args, shell=False):
    try:
        logging.info("Issuing command: {}".format(args))
        res = subprocess.check_output(args, shell=shell, timeout=1800).decode("utf-8").replace("\r\n", "")
        logging.info("Output: {}".format(res))
    except subprocess.CalledProcessError as e:
        raise RuntimeError("command '{}' return with error (code {}): {}".format(e.cmd, e.returncode, e.output))
    return res

# Copies source directory recursively to destination.
def copy(src, dest):
    try:
        shutil.copytree(src, dest)
        logging.info("Moved {} to {}".format(src, dest))
    except OSError as e:
        # If the error was caused because the source wasn't a directory
        if e.errno == errno.ENOTDIR:
            shutil.copy(src, dest)
            logging.info("Moved {} to {}".format(src, dest))
        else:
            raise RuntimeError("copy return with error: {}".format(e))

# Workaround for windows readonly attribute error
def on_rm_error( func, path, exc_info):
    # path contains the path of the file that couldn't be removed
    # let's just assume that it's read-only and unlink it.
    os.chmod( path, stat.S_IWRITE )
    os.unlink( path )

def main():
    logging.getLogger().setLevel(logging.DEBUG)

    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-g', '--gpu',
                        help='GPU install',
                        default=False,
                        type=bool)
    group.add_argument('-c', '--cpu',
                        help='CPU install',
                        default=False,
                        type=bool)
    args = parser.parse_args()

    # Visual Studio CE 2017
    # Path: C:\Program Files (x86)\Microsoft Visual Studio 14.0
    # Components: https://docs.microsoft.com/en-us/visualstudio/install/workload-component-id-vs-community?view=vs-2017#visual-studio-core-editor-included-with-visual-studio-community-2017
    logging.info("Installing Visual Studio CE 2017...")
    with tempfile.TemporaryDirectory() as tmpdir:
        vs_file_path = download_file('https://aka.ms/eac464', tmpdir)
        run_command("PowerShell Rename-Item -Path {} -NewName \"{}.exe\"".format(vs_file_path, vs_file_path.split('\\')[-1]), shell=True)
        vs_file_path = vs_file_path + '.exe'
        run_command(vs_file_path \
        + ' --add Microsoft.VisualStudio.Workload.ManagedDesktop' \
        + ' --add Microsoft.VisualStudio.Workload.NetCoreTools' \
        + ' --add Microsoft.VisualStudio.Workload.NetWeb' \
        + ' --add Microsoft.VisualStudio.Workload.Node' \
        + ' --add Microsoft.VisualStudio.Workload.Office' \
        + ' --add Microsoft.VisualStudio.Component.TypeScript.2.0' \
        + ' --add Microsoft.VisualStudio.Component.TestTools.WebLoadTest' \
        + ' --add Component.GitHub.VisualStudio' \
        + ' --add Microsoft.VisualStudio.ComponentGroup.NativeDesktop.Core' \
        + ' --add Microsoft.VisualStudio.Component.Static.Analysis.Tools' \
        + ' --add Microsoft.VisualStudio.Component.VC.CMake.Project' \
        + ' --add Microsoft.VisualStudio.Component.VC.140' \
        + ' --add Microsoft.VisualStudio.Component.Windows10SDK.15063.Desktop' \
        + ' --add Microsoft.VisualStudio.Component.Windows10SDK.15063.UWP' \
        + ' --add Microsoft.VisualStudio.Component.Windows10SDK.15063.UWP.Native' \
        + ' --add Microsoft.VisualStudio.ComponentGroup.Windows10SDK.15063' \
        + ' --wait' \
        + ' --passive' \
        + ' --norestart'
        )
        # Workaround for --wait sometimes ignoring the subprocesses doing component installs
        timer = 0
        while {'vs_installer.exe', 'vs_installershell.exe', 'vs_setup_bootstrapper.exe'} & set(map(lambda process: process.name(), psutil.process_iter())):
            if timer % 60 == 0:
                logging.info("Waiting for Visual Studio to install for the last {} seconds".format(str(timer)))
            timer += 1

    # CUDA 9.2 and patches
    logging.info("Installing CUDA 9.2 and Patches...")
    with tempfile.TemporaryDirectory() as tmpdir:
        cuda_9_2_file_path = download_file('https://developer.nvidia.com/compute/cuda/9.2/Prod2/network_installers2/cuda_9.2.148_win10_network', tmpdir)
        run_command("PowerShell Rename-Item -Path {} -NewName \"{}.exe\"".format(cuda_9_2_file_path, cuda_9_2_file_path.split('\\')[-1]), shell=True)
        cuda_9_2_file_path = cuda_9_2_file_path + '.exe'
        run_command(cuda_9_2_file_path \
        + ' -s nvcc_9.2' \
        + ' cuobjdump_9.2' \
        + ' nvprune_9.2' \
        + ' cupti_9.2' \
        + ' gpu_library_advisor_9.2' \
        + ' memcheck_9.2' \
        + ' nvdisasm_9.2' \
        + ' nvprof_9.2' \
        + ' visual_profiler_9.2' \
        + ' visual_studio_integration_9.2' \
        + ' demo_suite_9.2' \
        + ' documentation_9.2' \
        + ' cublas_9.2' \
        + ' cublas_dev_9.2' \
        + ' cudart_9.2' \
        + ' cufft_9.2' \
        + ' cufft_dev_9.2' \
        + ' curand_9.2' \
        + ' curand_dev_9.2' \
        + ' cusolver_9.2' \
        + ' cusolver_dev_9.2' \
        + ' cusparse_9.2' \
        + ' cusparse_dev_9.2' \
        + ' nvgraph_9.2' \
        + ' nvgraph_dev_9.2' \
        + ' npp_9.2' \
        + ' npp_dev_9.2' \
        + ' nvrtc_9.2' \
        + ' nvrtc_dev_9.2' \
        + ' nvml_dev_9.2' \
        + ' occupancy_calculator_9.2'
        )
        # Download patches and assume less than 100 patches exist
        for patch_number in range(1, 100):
            if patch_number == 100:
                raise Exception('Probable patch loop: CUDA patch downloader is downloading at least 100 patches!')
            cuda_9_2_patch_file_path = download_file("https://developer.nvidia.com/compute/cuda/9.2/Prod2/patches/{0}/cuda_9.2.148.{0}_windows".format(patch_number), tmpdir)
            if cuda_9_2_patch_file_path == 404:
                break
            run_command("PowerShell Rename-Item -Path {} -NewName \"{}.exe\"".format(cuda_9_2_patch_file_path, cuda_9_2_patch_file_path.split('\\')[-1]), shell=True)
            cuda_9_2_patch_file_path = cuda_9_2_patch_file_path + '.exe'
            run_command("{} -s".format(cuda_9_2_patch_file_path))

    # CMAKE 3.11
    logging.info("Installing CMAKE 3.11...")
    with tempfile.TemporaryDirectory() as tmpdir:
        cmake_file_path = download_file('https://cmake.org/files/v3.11/cmake-3.11.4-win64-x64.msi', tmpdir)
        run_command("msiexec /i {} /quiet /norestart ADD_CMAKE_TO_PATH=System".format(cmake_file_path))

    # OpenBLAS
    logging.info("Installing OpenBLAS 0.2.19...")
    with zipfile.ZipFile("C:\\OpenBLAS-windows-v0_2_19.zip", 'r') as zip:
        zip.extractall("C:\\Program Files")
    os.remove("C:\\OpenBLAS-windows-v0_2_19.zip")
    run_command("PowerShell Set-ItemProperty -path 'hklm:\\system\\currentcontrolset\\control\\session manager\\environment' -Name OpenBLAS_HOME -Value 'C:\\Program Files\\OpenBLAS-windows-v0_2_19'")

    # MKL
    logging.info("Installing MKL 2019.3.203...")
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = download_file(
            "http://registrationcenter-download.intel.com/akdlm/irc_nas/tec/15247/w_mkl_2019.3.203.exe", tmpdir)
        run_command(
            "{} --silent --remove-extracted-files yes --a install -output=C:\mkl-install-log.txt -eula=accept".format(file_path))

    # OpenCV
    logging.info("Installing OpenCV 3.4.1...")
    with zipfile.ZipFile("C:\\OpenCV-windows-v3_4_1-vc14.zip", 'r') as zip:
        zip.extractall("C:\\Program Files")
    os.remove("C:\\OpenCV-windows-v3_4_1-vc14.zip")
    run_command("PowerShell Set-ItemProperty -path 'hklm:\\system\\currentcontrolset\\control\\session manager\\environment' -Name OpenCV_DIR -Value 'C:\\Program Files\\OpenCV-windows-v3_4_1-vc14'")

    # Update Path
    # TODO: Add python paths (python -> C:\\Python37\\python.exe, python2 -> C:\\Python27\\python.exe)
    logging.info("Adding Windows Kits to PATH...")
    current_path = run_command("PowerShell (Get-Itemproperty -path 'hklm:\\system\\currentcontrolset\\control\\session manager\\environment' -Name Path).Path")
    logging.debug("current_path: {}".format(current_path))
    new_path = current_path + ";C:\\Program Files (x86)\\Windows Kits\\10\\bin\\10.0.16299.0\\x86;C:\\Program Files\\OpenBLAS-windows-v0_2_19\\bin"
    logging.debug("new_path: {}".format(new_path))
    run_command("PowerShell Set-ItemProperty -path 'hklm:\\system\\currentcontrolset\\control\\session manager\\environment' -Name Path -Value '" + new_path + "'")

    # cuDNN
    logging.info("Installing cuDNN 9.2...")
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile("C:\\cudnn-9.2-windows10-x64-v7.4.2.24.zip", 'r') as zip:
            zip.extractall(tmpdir)
        copy(tmpdir+"\\cuda\\bin\\cudnn64_7.dll","C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v9.2\\bin")
        copy(tmpdir+"\\cuda\\include\\cudnn.h","C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v9.2\\include")
        copy(tmpdir+"\\cuda\\lib\\x64\\cudnn.lib","C:\\Program Files\\NVIDIA GPU Computing Toolkit\\CUDA\\v9.2\\lib\\x64")
    os.remove("C:\\cudnn-9.2-windows10-x64-v7.4.2.24.zip")

    # Install Nvidia display drivers for GPU
    if args.gpu:
        logging.info("Installing Nvidia Display Drivers...")
        with tempfile.TemporaryDirectory() as tmpdir:
            with zipfile.ZipFile("C:\\nvidia_display_drivers_398.75_server2016.zip", 'r') as zip:
                zip.extractall(tmpdir)
            run_command(tmpdir + "\\setup.exe /n /s /noeula /nofinish")
        os.remove("C:\\nvidia_display_drivers_398.75_server2016.zip")

    # TODO: Add checks for existence of pathnames?

    # TODO: Unsigned driver workaround
    # run_command(['PowerShell','reg', 'add', '\"HKCU\\Software\\Policies\\Microsoft\\Windows NT\\Driver Signing\"', '/v', 'BehaviorOnFailedVerify', '/t', 'reg_dword', '/d', '00000000', '/f'], shell=True)

if __name__ == "__main__":
    exit (main())
