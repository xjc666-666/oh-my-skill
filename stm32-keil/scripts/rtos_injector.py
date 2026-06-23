import os
import sys
import shutil
import urllib.request
import zipfile
import tempfile
import argparse
import xml.etree.ElementTree as ET
import re
from pathlib import Path

# Fix path to load utils
sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils import load_chip_db

SKILL_DIR = Path(__file__).resolve().parent.parent
FREERTOS_TAG = "V11.3.0"
FREERTOS_MIRRORS = [
    f"https://github.com/FreeRTOS/FreeRTOS-Kernel/archive/refs/tags/{FREERTOS_TAG}.zip",
    f"https://gitee.com/mirrors/FreeRTOS-Kernel/repository/archive/{FREERTOS_TAG}.zip"
]
FREERTOS_ZIP_PATH = SKILL_DIR / "skeleton" / "freertos.zip"
FREERTOS_SRC_PATH = SKILL_DIR / "skeleton" / "freertos" / "Source"
FREERTOS_CONFIG_PATH = SKILL_DIR / "skeleton" / "freertos" / "FreeRTOSConfig.h"

def download_freertos():
    print(f"Downloading FreeRTOS {FREERTOS_TAG} kernel...")
    tmp_dir = SKILL_DIR / "skeleton" / "freertos" / "tmp"
    success = False
    for url in FREERTOS_MIRRORS:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=60) as response, open(FREERTOS_ZIP_PATH, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            print("Extracting...")
            with zipfile.ZipFile(FREERTOS_ZIP_PATH, 'r') as zip_ref:
                zip_ref.extractall(tmp_dir)
            
            extracted_dir = tmp_dir / f"FreeRTOS-Kernel-{FREERTOS_TAG.lstrip('V')}"
            if extracted_dir.exists():
                if FREERTOS_SRC_PATH.exists():
                    shutil.rmtree(FREERTOS_SRC_PATH)
                shutil.move(str(extracted_dir), str(FREERTOS_SRC_PATH))
            success = True
            break
        except Exception as e:
            print(f"Failed to download from {url}: {e}")
            if FREERTOS_ZIP_PATH.exists():
                os.remove(FREERTOS_ZIP_PATH)
            if tmp_dir.exists():
                shutil.rmtree(tmp_dir)
                
    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    if FREERTOS_ZIP_PATH.exists():
        os.remove(FREERTOS_ZIP_PATH)
        
    if not success:
        raise RuntimeError("Failed to download FreeRTOS from all mirrors.")
    print("FreeRTOS downloaded and prepared.")

def prepare_freertos():
    if not FREERTOS_SRC_PATH.exists():
        download_freertos()

def get_port_dir(chip_name):
    db = load_chip_db()
    chip_info = db.get(chip_name, {})
    core = chip_info.get("core", "Cortex-M4").lower()
    has_fpu = chip_info.get("has_fpu", False)
    
    if "m0" in core:
        return "ARM_CM0"
    elif "m3" in core:
        return "ARM_CM3"
    elif "m4" in core:
        return "ARM_CM4F" if has_fpu else "ARM_CM4F" # Default to CM4F, Keil usually compiles fine
    elif "m7" in core:
        return "ARM_CM7"
    return "ARM_CM4F"

def inject_rtos(project_dir, chip_name):
    print(f"Injecting FreeRTOS into {project_dir}...")
    
    proj_dir_path = Path(project_dir)
    
    # 0. Check for .uvprojx first
    uvprojx_files = list(proj_dir_path.glob("*.uvprojx"))
    if not uvprojx_files:
        uvprojx_files = list((proj_dir_path / "Project").glob("*.uvprojx"))
    if not uvprojx_files:
        uvprojx_files = list(proj_dir_path.rglob("*.uvprojx"))
    if not uvprojx_files:
        print("No .uvprojx file found anywhere in the project tree.")
        return False
        
    uvprojx_path = uvprojx_files[0]
    
    prepare_freertos()
    
    target_freertos_dir = proj_dir_path / "FreeRTOS"
    
    # 1. Copy Files
    if target_freertos_dir.exists():
        print("FreeRTOS directory already exists in project, skipping copy.")
    else:
        shutil.copytree(FREERTOS_SRC_PATH, target_freertos_dir / "Source")
        shutil.copy(FREERTOS_CONFIG_PATH, target_freertos_dir / "FreeRTOSConfig.h")
        print("FreeRTOS files copied.")

    # 2. Update .uvprojx
    port_name = get_port_dir(chip_name)
    
    tree = ET.parse(uvprojx_path)
    root = tree.getroot()
    
    # Add Include Paths
    target_info = root.find(".//TargetOption/TargetArmAds/Cads/VariousControls/IncludePath")
    if target_info is not None:
        inc_paths = target_info.text or ""
        paths_to_add = [
            "..\\FreeRTOS",
            "..\\FreeRTOS\\Source\\include",
            f"..\\FreeRTOS\\Source\\portable\\RVDS\\{port_name}"
        ]
        for p in paths_to_add:
            if p not in inc_paths:
                inc_paths += f";{p}" if inc_paths else p
        target_info.text = inc_paths
    
    # Add Group
    groups = root.find(".//Groups")
    if groups is not None:
        # Check if FreeRTOS group exists
        rtos_group = None
        for group in groups.findall("Group"):
            if group.find("GroupName").text == "FreeRTOS":
                rtos_group = group
                break
        
        if rtos_group is None:
            rtos_group = ET.SubElement(groups, "Group")
            ET.SubElement(rtos_group, "GroupName").text = "FreeRTOS"
            files_node = ET.SubElement(rtos_group, "Files")
            
            rtos_files = [
                ("c.c", f"..\\FreeRTOS\\Source\\croutine.c"),
                ("e.c", f"..\\FreeRTOS\\Source\\event_groups.c"),
                ("l.c", f"..\\FreeRTOS\\Source\\list.c"),
                ("q.c", f"..\\FreeRTOS\\Source\\queue.c"),
                ("s.c", f"..\\FreeRTOS\\Source\\stream_buffer.c"),
                ("t.c", f"..\\FreeRTOS\\Source\\tasks.c"),
                ("tm.c", f"..\\FreeRTOS\\Source\\timers.c"),
                ("port.c", f"..\\FreeRTOS\\Source\\portable\\RVDS\\{port_name}\\port.c"),
                ("heap.c", f"..\\FreeRTOS\\Source\\portable\\MemMang\\heap_4.c"),
            ]
            for name, path in rtos_files:
                file_node = ET.SubElement(files_node, "File")
                ET.SubElement(file_node, "FileName").text = path.split("\\")[-1]
                ET.SubElement(file_node, "FileType").text = "1"
                ET.SubElement(file_node, "FilePath").text = path

    tree.write(uvprojx_path, encoding="utf-8", xml_declaration=True)
    print("Updated .uvprojx with FreeRTOS files and include paths.")

    # 3. Update main.c
    main_c_path = proj_dir_path / "User" / "main.c"
    if main_c_path.exists():
        with open(main_c_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        if "FreeRTOS.h" not in content:
            # Add includes
            inc_str = '#include "FreeRTOS.h"\n#include "task.h"\n\n'
            if '#include "main.h"' in content:
                content = re.sub(r'(#include "main\.h")', r'\1\n' + inc_str, content)
            else:
                content = re.sub(r'(#include\s+[<"][^>"]+[>"].*\n)(?!#include)', r'\1' + inc_str, content, count=1)
            
            # Add a default task
            task_str = "void vTask1(void *pvParameters) {\n    while(1) {\n        vTaskDelay(pdMS_TO_TICKS(1000));\n    }\n}\n\n"
            content = re.sub(r'(int\s+main\s*\(\s*void\s*\))', task_str + r'\1', content)
            
            # Start scheduler before while(1)
            init_str = "    xTaskCreate(vTask1, \"Task1\", 128, NULL, 1, NULL);\n    vTaskStartScheduler();\n\n"
            content = re.sub(r'(\s*while\s*\(\s*1\s*\))', init_str + r'\1', content, count=1)
            
            with open(main_c_path, "w", encoding="utf-8") as f:
                f.write(content)
            print("Updated main.c with FreeRTOS skeleton.")
    
    # 4. Remove SysTick_Handler from stm32xxx_it.c to avoid collision
    it_files = list((proj_dir_path / "User").glob("*_it.c"))
    if it_files:
        it_file = it_files[0]
        with open(it_file, "r", encoding="utf-8") as f:
            it_content = f.read()
        
        if "SysTick_Handler(void)" in it_content and "xPortSysTickHandler" not in it_content:
            from utils import _extract_brace_block
            match = re.search(r'void\s+SysTick_Handler\s*\(\s*void\s*\)\s*\{', it_content)
            if match:
                start_idx = match.start()
                brace_start = it_content.find('{', start_idx)
                block, end_idx = _extract_brace_block(it_content, brace_start)
                if block:
                    it_content = it_content[:start_idx] + "/*\n" + it_content[start_idx:end_idx] + "\n*/" + it_content[end_idx:]
                    with open(it_file, "w", encoding="utf-8") as f:
                        f.write(it_content)
                    print("Commented out SysTick_Handler in *_it.c to prevent collision.")
        
    print("FreeRTOS injection complete!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, help="Project directory path")
    parser.add_argument("--chip", required=True, help="Chip name (e.g. STM32F407ZGT6)")
    args = parser.parse_args()
    inject_rtos(args.project, args.chip)
