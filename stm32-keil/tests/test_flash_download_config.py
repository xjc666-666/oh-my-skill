import sys
import xml.etree.ElementTree as ET
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from uvprojx_modifier import ensure_flash_download_config


def test_flash_config_populates_blank_stlink_entry(tmp_path):
    project = tmp_path / "Test.uvprojx"
    options = tmp_path / "Test.uvoptx"

    project.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<Project>
  <Targets>
    <Target>
      <TargetName>Test</TargetName>
      <TargetOption>
        <TargetCommonOption>
          <Device>STM32F407ZGTx</Device>
          <FlashDriverDll></FlashDriverDll>
        </TargetCommonOption>
      </TargetOption>
    </Target>
  </Targets>
</Project>
""",
        encoding="utf-8",
    )

    options.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<ProjectOpt>
  <Target>
    <TargetName>Test</TargetName>
    <TargetOption>
      <DebugOpt>
        <pMon>STLink\\ST-LINKIII-KEIL_SWO.dll</pMon>
      </DebugOpt>
      <TargetDriverDllRegistry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>ST-LINKIII-KEIL_SWO</Key>
          <Name />
        </SetRegEntry>
        <SetRegEntry>
          <Number>0</Number>
          <Key>UL2CM3</Key>
          <Name />
        </SetRegEntry>
      </TargetDriverDllRegistry>
    </TargetOption>
  </Target>
</ProjectOpt>
""",
        encoding="utf-8",
    )

    assert ensure_flash_download_config(str(project), "STM32F407ZGT6")

    opt_root = ET.parse(options).getroot()
    names_by_key = {}
    for entry in opt_root.iter("SetRegEntry"):
        key = entry.findtext("Key")
        names_by_key[key] = entry.findtext("Name", "")

    stlink = names_by_key["ST-LINKIII-KEIL_SWO"]
    ul2 = names_by_key["UL2CM3"]

    for text in (stlink, ul2):
        assert "-FN2" in text
        assert "-FF0STM32F4xx_1024" in text
        assert "-FS08000000" in text
        assert "-FL00100000" in text
        assert r"-FP0($$Device:STM32F407ZGTx$CMSIS\Flash\STM32F4xx_1024.FLM)" in text

    assert "-R1" in stlink
