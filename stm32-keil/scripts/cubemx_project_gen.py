"""
Generate a Keil MDK-ARM project using STM32CubeMX in headless mode.

Workflow:
  1. Resolve chip name to CubeMX Mcu.Name + Package
  2. Create a minimal .ioc file for the target chip
  3. Write a CubeMX headless script
  4. Execute CubeMX to generate the project
  5. Post-process the generated project (rename, clean, verify)

CubeMX headless invocation:
  STM32CubeMX.exe -q <script_file>

Script syntax:
  config load <project.ioc>
  project generate
  exit
"""
import os
import sys
import re
import shutil
import json
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cubemx_finder import find_cubemx, get_cubemx_or_ask
from cubemx_mcu_resolver import resolve_cubemx_mcu, parse_chip
from utils import ensure_dir, normalize_path


def generate_project(
    chip: str,
    name: str,
    path: str,
    cubemx_exe: Optional[str] = None,
    timeout: int = 300,
) -> Dict:
    """Generate a Keil MDK-ARM project using CubeMX.

    Args:
        chip: Chip model (e.g., STM32F407ZGT6)
        name: Project name
        path: Parent directory for the project
        cubemx_exe: Path to STM32CubeMX.exe (auto-detected if None)
        timeout: Max seconds to wait for CubeMX generation

    Returns:
        Dict with success, project_path, uvprojx_path, error, etc.
    """
    # 1. Find CubeMX
    if cubemx_exe is None:
        cubemx_exe = find_cubemx()
    if not cubemx_exe or not os.path.isfile(cubemx_exe):
        resp = get_cubemx_or_ask()
        if not resp:
            return {
                "success": False,
                "error": (
                    "STM32CubeMX not found. Please install from "
                    "https://www.st.com/stm32cubemx or set CUBEMX_PATH "
                    "environment variable to the installation directory."
                ),
                "needs_cubemx_path": True,
            }
        cubemx_exe = resp

    cubemx_dir = os.path.dirname(cubemx_exe)

    # 2. Resolve chip to CubeMX name
    mx_info = resolve_cubemx_mcu(chip, os.path.join(cubemx_dir, "db", "mcu"))
    if not mx_info:
        return {
            "success": False,
            "error": (
                f"Chip {chip} not found in CubeMX database. "
                "Please check chip name or update CubeMX."
            ),
        }

    cubemx_name = mx_info["cubemx_name"]
    cubemx_package = mx_info["cubemx_package"]
    family = mx_info["family"]

    # 3. Create output directory
    project_dir = os.path.join(path, name)
    if os.path.isdir(project_dir) and os.listdir(project_dir):
        return {
            "success": False,
            "error": f"Directory {project_dir} is not empty."
        }
    ensure_dir(project_dir)

    # 4. Generate minimal .ioc file
    ioc_path = os.path.join(project_dir, f"{name}.ioc")
    _generate_minimal_ioc(ioc_path, name, cubemx_name, cubemx_package, family)

    # 5. Write CubeMX headless script
    script_path = os.path.join(project_dir, "_cubemx_gen.script")
    _write_cubemx_script(script_path, ioc_path, project_dir)

    # 6. Run CubeMX
    print(f"Running CubeMX to generate project '{name}' for {chip}...")
    print(f"  CubeMX: {cubemx_exe}")
    print(f"  MCU: {cubemx_name} ({cubemx_package})")
    print(f"  Output: {project_dir}")

    rc, stdout, stderr = _run_cubemx(cubemx_exe, script_path, timeout)

    # 7. Clean up script
    try:
        os.remove(script_path)
    except OSError:
        pass

    if rc != 0:
        return {
            "success": False,
            "error": f"CubeMX generation failed (exit code {rc}):\n{stderr}\n{stdout}",
            "stdout": stdout,
            "stderr": stderr,
        }

    # 8. Verify output
    uvprojx_path = _find_generated_uvprojx(project_dir)
    if not uvprojx_path:
        listing = "\n".join(
            f"  {os.path.join(root, f)}"
            for root, _, files in os.walk(project_dir)
            for f in files[:30]
        )
        return {
            "success": False,
            "error": (
                f"Project generated but no .uvprojx found.\n"
                f"Files in output:\n{listing}"
            ),
        }

    # 9. Rename .uvprojx to match project name
    uvprojx_path = _rename_generated_uvprojx(uvprojx_path, name)

    # 10. Clean up build artifacts that CubeMX might have generated
    _clean_build_artifacts(project_dir)

    # 11. Generate README.md
    _generate_readme(project_dir, name, chip, family)

    return {
        "success": True,
        "project_path": normalize_path(project_dir),
        "uvprojx_path": normalize_path(uvprojx_path),
        "chip": chip,
        "family": family,
        "library": "HAL",
        "cubemx_name": cubemx_name,
        "cubemx_package": cubemx_package,
        "error": None,
    }


def _generate_minimal_ioc(
    ioc_path: str,
    name: str,
    cubemx_name: str,
    cubemx_package: str,
    family: str,
) -> None:
    """Create a minimal .ioc file for CubeMX project generation.

    The .ioc file uses an INI-like key=value format.
    This creates the absolute minimum needed: MCU identity, SWD debug pins,
    SysTick, and basic clock configuration using HSI.

    CubeMX fills in the remaining defaults during code generation.
    """
    # Debug pin signals — PA13/PA14 are universally SWD on Cortex-M STM32
    content = f"""#MicroXplorer Configuration settings - do not modify
File.Version=6
KeepUserPlacement=false
Mcu.Family={family}
Mcu.IP0=NVIC
Mcu.IP1=RCC
Mcu.IP2=SYS
Mcu.IPNb=3
Mcu.Name={cubemx_name}
Mcu.Package={cubemx_package}
Mcu.Pin0=PA13
Mcu.Pin1=PA14
Mcu.Pin2=VP_SYS_VS_Systick
Mcu.PinsNb=3
Mcu.UserConstants=
Mcu.UserName={cubemx_name}
MxCube.Version=6.14
MxDb.Version=DB.6.0.140
NVIC.BusFault_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.DebugMonitor_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.HardFault_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.MemoryManagement_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.NonMaskableInt_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.PendSV_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.PriorityGroup=NVIC_PRIORITYGROUP_4
NVIC.SVCall_IRQn=true\\:0\\:0\\:false\\:false\\:false
NVIC.SysTick_IRQn=true\\:0\\:0\\:false\\:false\\:true
NVIC.UsageFault_IRQn=true\\:0\\:0\\:false\\:false\\:false
PA13.GPIOParameters=GPIO_Label
PA13.GPIO_Label=TMS_SWDIO
PA13.Locked=true
PA13.Signal=SYS_JTMS-SWDIO
PA14.GPIOParameters=GPIO_Label
PA14.GPIO_Label=TCK_SWCLK
PA14.Locked=true
PA14.Signal=SYS_JTCK-SWCLK
PCC.Checker=false
PCC.Line=STM32{family[5:]}
PCC.MCU={cubemx_name}
PCC.MXVersion=6.14
PCC.PartNumber={cubemx_name}
PCC.Seq0=0
PCC.Series={family}
PCC.Temperature=25
PCC.Vdd=null
ProjectManager.AskForMigrate=true
ProjectManager.BackupPrevious=false
ProjectManager.CompilerOptimize=2
ProjectManager.ComputerToolchain=false
ProjectManager.CoupleFile=false
ProjectManager.DefaultFWLocation=true
ProjectManager.DeletePrevious=true
ProjectManager.DeviceId={cubemx_name}
ProjectManager.FreePins=false
ProjectManager.HalAssertFull=false
ProjectManager.HeapSize=0x200
ProjectManager.KeepUserCode=true
ProjectManager.LastFirmware=true
ProjectManager.LibraryCopy=0
ProjectManager.PreviousToolchain=
ProjectManager.ProjectBuild=false
ProjectManager.ProjectFileName={name}.ioc
ProjectManager.ProjectName={name}
ProjectManager.StackSize=0x400
ProjectManager.TargetToolchain=MDK-ARM V5
ProjectManager.ToolChainLocation=
ProjectManager.UnderRoot=false
ProjectManager.functionlistsort=1-MX_GPIO_Init-GPIO-false-HAL,2-SystemClock_Config-RCC-false-HAL
RCC.AHBFreq_Value=16000000
RCC.APB1CLKDivider=RCC_HCLK_DIV1
RCC.APB1Freq_Value=16000000
RCC.APB1TimFreq_Value=16000000
RCC.APB2Freq_Value=16000000
RCC.APB2TimFreq_Value=16000000
RCC.CortexFreq_Value=16000000
RCC.FCLKCortexFreq_Value=16000000
RCC.HCLKFreq_Value=16000000
RCC.HSE_VALUE=8000000
RCC.HSI_VALUE=16000000
RCC.I2SClocksFreq_Value=16000000
RCC.IPParameters=AHBFreq_Value,APB1CLKDivider,APB1Freq_Value,APB1TimFreq_Value,APB2Freq_Value,APB2TimFreq_Value,CortexFreq_Value,FCLKCortexFreq_Value,HCLKFreq_Value,HSE_VALUE,HSI_VALUE,I2SClocksFreq_Value,LSE_VALUE,LSI_VALUE,MCO2PinFreq_Value,PLLCLKFreq_Value,PLLM,PLLN,PLLP,PLLQ,PLLQCLKFreq_Value,PLLSource,PLLState,RTCFreq_Value,RTCHSEDivFreq_Value,SYSCLKFreq_VALUE,SYSCLKSource,VCOI2SOutputFreq_Value,VCOInputFreq_Value,VCOOutputFreq_Value,VcooutputI2S
RCC.LSE_VALUE=32768
RCC.LSI_VALUE=32000
RCC.MCO2PinFreq_Value=16000000
RCC.PLLCLKFreq_Value=16000000
RCC.PLLM=1
RCC.PLLN=8
RCC.PLLP=RCC_PLLP_DIV2
RCC.PLLQ=4
RCC.PLLQCLKFreq_Value=16000000
RCC.PLLSource=RCC_PLLSOURCE_HSI
RCC.PLLState=RCC_PLL_NONE
RCC.RTCFreq_Value=32000
RCC.RTCHSEDivFreq_Value=4000000
RCC.SYSCLKFreq_VALUE=16000000
RCC.SYSCLKSource=RCC_SYSCLKSOURCE_HSI
RCC.VCOI2SOutputFreq_Value=32000000
RCC.VCOInputFreq_Value=16000000
RCC.VCOOutputFreq_Value=32000000
RCC.VcooutputI2S=16000000
VP_SYS_VS_Systick.Mode=SysTick
VP_SYS_VS_Systick.Signal=SYS_VS_Systick
"""
    with open(ioc_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)


def _write_cubemx_script(script_path: str, ioc_path: str, output_dir: str) -> None:
    """Write the CubeMX headless script file.

    Script format (simple command sequence):
      config load <ioc_file>
      project generate
      exit

    CubeMX preserves code between /* USER CODE BEGIN */ / /* USER CODE END */
    comment blocks during regeneration.
    """
    # Use forward slashes for CubeMX compatibility
    ioc_path_fwd = ioc_path.replace("\\", "/")
    output_dir_fwd = output_dir.replace("\\", "/")

    script = f'config load {ioc_path_fwd}\r\nproject generate\r\nexit\r\n'
    with open(script_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(script)


def _run_cubemx(
    cubemx_exe: str,
    script_path: str,
    timeout: int = 300,
) -> Tuple[int, str, str]:
    """Execute CubeMX in headless mode.

    Returns (returncode, stdout, stderr).
    """
    script_path_fwd = script_path.replace("\\", "/")

    # CubeMX can take a while especially on first run for a new chip family
    # (it may need to download firmware packages)
    cmd = [cubemx_exe, "-q", script_path_fwd]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.path.dirname(cubemx_exe),
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"CubeMX timed out after {timeout}s"
    except Exception as e:
        return -1, "", str(e)


def _find_generated_uvprojx(project_dir: str) -> Optional[str]:
    """Find the .uvprojx file in a CubeMX-generated project.

    CubeMX places it in the MDK-ARM/ subdirectory.
    """
    # Primary location: MDK-ARM/*.uvprojx
    mdk_dir = os.path.join(project_dir, "MDK-ARM")
    if os.path.isdir(mdk_dir):
        for fname in os.listdir(mdk_dir):
            if fname.endswith(".uvprojx"):
                return os.path.join(mdk_dir, fname)

    # Fallback: search entire tree
    for root, _, files in os.walk(project_dir):
        for fname in files:
            if fname.endswith(".uvprojx"):
                return os.path.join(root, fname)

    return None


def _rename_generated_uvprojx(uvprojx_path: str, name: str) -> str:
    """Rename the generated .uvprojx (and .uvoptx) to match the project name.

    Also renames any .uvoptx alongside it.
    Updates the <TargetName> in both files.
    """
    import xml.etree.ElementTree as ET

    proj_dir = os.path.dirname(uvprojx_path)
    old_name_no_ext = os.path.splitext(os.path.basename(uvprojx_path))[0]
    new_uvprojx = os.path.join(proj_dir, f"{name}.uvprojx")

    # Rename .uvprojx if names differ
    if old_name_no_ext != name:
        if os.path.exists(new_uvprojx):
            os.remove(new_uvprojx)
        try:
            os.rename(uvprojx_path, new_uvprojx)
        except OSError:
            pass  # Keep old name if rename fails
    uvprojx_path = new_uvprojx

    # Rename .uvoptx
    old_uvoptx = os.path.join(proj_dir, f"{old_name_no_ext}.uvoptx")
    new_uvoptx = os.path.join(proj_dir, f"{name}.uvoptx")
    if os.path.isfile(old_uvoptx) and old_name_no_ext != name:
        if os.path.exists(new_uvoptx):
            os.remove(new_uvoptx)
        try:
            os.rename(old_uvoptx, new_uvoptx)
        except OSError:
            pass

    # Update TargetName in .uvprojx
    _update_target_name(uvprojx_path, name)
    if os.path.isfile(new_uvoptx):
        _update_target_name(new_uvoptx, name)

    # Clean up *.uvguix.* files (per-user GUI state)
    for fname in os.listdir(proj_dir):
        if ".uvguix." in fname or fname.endswith(".uvguix"):
            try:
                os.remove(os.path.join(proj_dir, fname))
            except OSError:
                pass

    return uvprojx_path


def _update_target_name(xml_path: str, name: str) -> None:
    """Update <TargetName> in a .uvprojx or .uvoptx XML file."""
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        for tn in root.iter("TargetName"):
            tn.text = name
        tree.write(xml_path, encoding="UTF-8", xml_declaration=True)
    except Exception:
        pass


def _clean_build_artifacts(project_dir: str) -> None:
    """Remove build artifacts that CubeMX may have left behind."""
    for root, dirs, files in os.walk(project_dir, topdown=True):
        # Skip Drivers directory (keep library intact)
        if "Drivers" in Path(root).parts:
            continue

        for d in list(dirs):
            if d in ("RTE", "DebugConfig", "Objects", "Listings"):
                full = os.path.join(root, d)
                try:
                    shutil.rmtree(full, ignore_errors=True)
                    dirs.remove(d)
                except Exception:
                    pass

        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in (".o", ".d", ".crf", ".axf", ".hex", ".bin",
                       ".iex", ".bak", ".dep", ".htm", ".lnp", ".sct"):
                try:
                    os.remove(os.path.join(root, fname))
                except OSError:
                    pass


def _generate_readme(
    project_dir: str, name: str, chip: str, family: str
) -> None:
    """Generate a README.md for the CubeMX-generated project."""
    uvprojx_rel = f"MDK-ARM/{name}.uvprojx"
    content = f"""# {name}

## 芯片信息
- **型号**: {chip}
- **系列**: {family}
- **库**: HAL (由 STM32CubeMX 生成)

## 引脚分配
> 由 stm32-keil skill 在确认引脚后填入。

| 外设 | 引脚 | 端口 | 说明 |
|------|------|------|------|
| _待填_ | | | |

## 工程结构
```
{name}/
├── {name}.ioc             # CubeMX 配置文件
├── Inc/                   # 头文件
├── Src/                   # 源文件 (main.c, stm32xx_it.c, ...)
├── Drivers/               # HAL 库 + CMSIS
│   ├── CMSIS/
│   └── STM32xx_HAL_Driver/
└── MDK-ARM/               # Keil 工程文件
    └── {name}.uvprojx
```

## 编译与烧录

### 编译
在 Keil MDK-ARM v5 中打开 `{uvprojx_rel}`，按 **F7** 编译。

### 烧录
通过 ST-Link / J-Link / DFU 烧录。在 Keil 中按 **F8**。

### 重新配置
如需修改外设/引脚/时钟，用 STM32CubeMX 打开 `{name}.ioc`，修改后重新生成代码。
CubeMX 会保留 `/* USER CODE BEGIN */` / `/* USER CODE END */` 之间的用户代码。

## 自动生成
此工程由 **stm32-keil skill** 通过 **STM32CubeMX** 自动生成。
"""
    readme_path = os.path.join(project_dir, "README.md")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a Keil project using CubeMX")
    parser.add_argument("--chip", required=True,
                        help="Chip model (e.g., STM32F407ZGT6)")
    parser.add_argument("--name", required=True,
                        help="Project name")
    parser.add_argument("--path", required=True,
                        help="Parent directory for the project")
    parser.add_argument("--cubemx", default=None,
                        help="Path to STM32CubeMX.exe (auto-detected if omitted)")
    parser.add_argument("--timeout", type=int, default=300,
                        help="CubeMX timeout in seconds")
    parser.add_argument("--smoke-build", action="store_true",
                        help="Run a compilation after generation")

    args = parser.parse_args()

    result = generate_project(
        args.chip, args.name, args.path,
        cubemx_exe=args.cubemx, timeout=args.timeout,
    )

    if result["success"]:
        print(f"Project created: {result['project_path']}")
        print(f"Keil project: {result['uvprojx_path']}")
        print(f"Chip: {result['chip']} ({result['family']}/HAL)")
        if args.smoke_build:
            try:
                from keil_builder import compile_project, get_build_summary
                print("\nRunning smoke build...")
                br = compile_project(result["uvprojx_path"], rebuild=False,
                                     timeout=180)
                print(get_build_summary(br))
                if not br.success:
                    print("\nSmoke build failed.")
                    sys.exit(2)
            except Exception as e:
                print(f"Smoke build skipped: {e}")
    else:
        print(f"Error: {result['error']}")
        sys.exit(1)
