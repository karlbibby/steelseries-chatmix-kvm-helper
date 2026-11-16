# SteelSeries ChatMix KVM Helper

A small Windows helper that restores **Arctis Nova Pro Wireless ChatMix through a USB KVM** when SteelSeries GG can play audio but cannot enable the hardware ChatMix control.

It sends two temporary HID output reports through Windows' `HidD_SetOutputReport` API. No third-party Python packages, custom driver, GG binary patch, firmware flash, or persistent headset-settings write is required.

**Experimental, unofficial, and tested on one setup.** This is a workaround for a specific USB command-path failure, not a general SteelSeries repair utility. There is no affiliation with SteelSeries or UGREEN.

## Confirmed setup and results

- Windows 11, x64
- SteelSeries GG 123.0.0
- Arctis Nova Pro Wireless PC/PlayStation base station, USB **VID `1038`, PID `12E0`**
- UGREEN **AK704** KVM
- Tested using Python 3.15; source targets Python 3.10+ on Windows

Symptoms on that setup:

- Audio and normal volume control worked through the KVM.
- Pressing the dial did not switch to ChatMix.
- The Engine device-configuration window was blank.
- GG logged failures such as `SendCommand: 0x3f17fa11` while reading headset settings and firmware information.
- Direct connection to the PC restored normal behavior.

Direct probing produced these results for the same `06 B0` status request:

| Connection | Windows API | Observation |
| --- | --- | --- |
| Direct USB | `WriteFile` | Write completed in approximately 28 ms; valid status reply received |
| Through KVM | `WriteFile` | Repeatedly failed to complete within the 1.5-second diagnostic timeout |
| Through KVM | `HidD_SetOutputReport` | Completed in approximately 5–6 ms; valid status reply received |

Sending the two ChatMix-enable reports through the successful method restored dial operation and game/chat balancing, confirmed by the user. Initial and periodic submissions also succeeded in the background helper.

**What this establishes:** the control-report method can communicate with the base station through this KVM, while the normal write method fails on this setup.

**What it does not establish:** the exact cause inside the KVM, hub, host USB controller, or Windows driver. GG's own API calls were not instrumented, and no USB packet capture was taken. The direct and KVM paths used different controller topologies. Physical KVM-switch recovery is not yet verified. Other headsets and KVMs are untested.

### Startup correction

The initial version failed after reboot with Windows error 740 because it launched `SteelSeriesGGEZ.exe` using direct process creation. GGEZ's manifest requests `uiAccess="true"`; Windows' shell launch is required on the tested installation. The helper now uses `os.startfile` (ShellExecute), the installed host's working directory, and its background startup arguments. The helper itself stays unelevated. No scheduled task or custom elevation mechanism is installed. The corrected installed startup command was tested with all GG processes stopped: it started GGEZ, GG, Engine and Sonar, and successfully submitted both ChatMix commands. A subsequent complete Windows sign-in test is still outstanding.

## What the helper does

1. Starts GG, or starts its original GGEZ host in background mode when launched with `--startup`.
2. Checks for GG/Engine process changes and base-station reconnection every two seconds.
3. After a change, submits the enable commands after roughly 2, 10, and 25 seconds so GG can finish initializing.
4. Reapplies them every **30 seconds** while GG and the headset are present, to recover silent loss of ChatMix enablement.
5. Exits after GG/Engine have both been absent for one minute.

There is no reliable enabled-state check implemented here: periodic reapplication is preventive, not proof that ChatMix failed. A physical dial/audio test remains the functional check. The helper does **not** read dial input reports during normal operation, so GG/Sonar can keep receiving them. A Windows session mutex prevents duplicate watchers.

### Commands sent

Only these two commands are used during normal operation, padded to the advertised 64-byte output report length:

| Bytes | Purpose |
| --- | --- |
| `06 49 01` | Enable hardware ChatMix mode |
| `06 8D 01` | Enable the corresponding software/ChatMix indication |

The target must match interface 4, collection 1, usage page `FFC0`, and 64-byte input/output reports. Multiple matching base stations cause the probe to stop **before sending commands**. The NVRAM-save command (`06 09`) is never sent. The helper does not change balance, volume, EQ, firmware, ANC, or microphone routing.

## Quick try: no startup changes

Install Windows Python 3.10+ from [python.org](https://www.python.org/downloads/windows/), with `python.exe` available on PATH. Download or clone this repository, keep its files together, and run from its folder:

```powershell
python gg_chatmix_helper.py --check
python gg_chatmix_helper.py --once
```

`--check` only detects GG and the base station. `--once` submits the two enable commands once without starting GG or a watcher. Test the physical dial afterward.

To start GG and continuous recovery:

```powershell
python gg_chatmix_helper.py
```

To keep it running without a console window, use `pythonw.exe` from the same Python installation instead of `python.exe`.

The helper expects GG in the normal `%ProgramFiles%\SteelSeries\GG` location. Change `GG` in the helper if your installation is elsewhere. If GG is deliberately closed, the helper stops after one minute; launch the helper again when reopening GG.

## Install for Windows sign-in

Review the scripts before running them. Installation copies the files into:

```text
%LOCALAPPDATA%\GGChatMixHelper
```

It discovers your existing Python installation, writes a local `pythonw-path.txt`, and adds a per-user Windows Run entry named `SteelSeriesChatMixHelper`.

### Keep GG's existing startup entry

From PowerShell in the repository folder:

```powershell
.\Install.ps1
```

GG's existing startup remains untouched. The helper starts the GG host only when GG/Engine are not already running. GG's own host may also process its existing startup entry.

### Replace GG's existing startup entry

Open PowerShell **as administrator using your own account**, then run:

```powershell
.\Install.ps1 -ReplaceGGStartup
```

This backs up and removes existing `SteelSeriesGG` values in the machine/user Run keys, then uses the helper's per-user startup entry instead. The helper launches GGEZ using GG's original background/auto arguments. Removing a machine-wide Run value also affects other Windows users on the PC; use the default installation if you want to leave their startup unchanged.

The installer refuses unexpected GG startup commands. It does not change PowerShell execution policy. If your device policy blocks scripts, use the manual Python commands or your organization's approved process. The installation and its backup contain local paths and your account SID: **do not upload those generated files**.

Double-click **Launch GG with ChatMix.vbs** in the installed folder to start now, or sign in again. The VBS launcher requires Windows Script Host; the Python commands are an alternative where it is unavailable. Startup behavior should be checked on your own PC after the next sign-in.

Before updating, stop the running helper. Restore startup before switching between the two installation modes. The installer does not download software or Python packages.

## Stop, restore, or uninstall

1. End the `pythonw.exe`/`python.exe` process whose command line points to `gg_chatmix_helper.py` (Task Manager's Details tab can show Command line). Do not stop unrelated Python processes.
2. In the **installed folder**, run:

   ```powershell
   .\Restore-Startup.ps1
   ```

   Use an administrator PowerShell window if the original installation replaced a machine-wide GG startup entry. Run as the original installing account. The restore script uses `startup-backup.json` and refuses to overwrite startup commands that have changed unexpectedly.
3. After restoring startup and stopping the helper, remove the installed folder if desired.

Keep `startup-backup.json` until restoration is complete. Restoring startup does not itself stop an already-running helper.

## Logs and troubleshooting

`gg-chatmix-helper.log` is stored alongside the installed helper. Logs rotate at approximately 200 KB with two backups. Successful submission means Windows accepted the commands; it does not independently verify an audible balance change.

- **No base station:** check USB input selection and the supported PID. Xbox and other Nova variants are intentionally not targeted.
- **Multiple base stations:** disconnect the extra matching device; no automatic selection is made.
- **Access/error/timeout:** inspect the local log, compare direct USB, and check that the KVM is selected to this PC.
- **Still no balance change:** GG/Sonar must be running, and game/chat audio must be routed to the appropriate Sonar channels.
- **After a GG update:** verify startup is still as intended; the GG installer may recreate its own startup entry.
- **Old version fails at sign-in with error 740:** replace the installed `gg_chatmix_helper.py` with the current version while the helper is stopped. The corrected shell-launch path avoids the original direct-process-creation error. If Windows still refuses the shell launch, the watcher logs it and waits up to one minute for GG to be started manually.
- **Blank Engine settings or failed firmware reads:** these are not repaired by the helper. Connect directly for configuration and firmware updates.

Individual probe subprocesses are limited to ten seconds by the watcher. The standalone diagnostic probe has bounded overlapped I/O waits, but a malfunctioning driver may delay cancellation; run invasive diagnostics separately from normal operation.

## Optional diagnostics

```powershell
# Inventory only; writes inventory.json locally
python probe_headset.py

# Compare the two status-query methods, one at a time
python probe_headset.py normal-status --query
python probe_headset.py control-status --query --control
```

These query commands read status replies and should be used only for diagnosis. JSON captures include local device-instance paths. They and logs are excluded by `.gitignore`; review them before sharing. There is no network access, telemetry, or automatic upload in the helper.

Run the focused command-safety tests with:

```powershell
python -m unittest discover -s tests -v
```

## Protocol references

This implementation was written using Windows APIs and publicly documented protocol bytes. The linked projects are protocol references, not bundled dependencies:

- [Microsoft: sending HID reports](https://learn.microsoft.com/windows-hardware/drivers/hid/sending-hid-reports)
- [Microsoft: HidD_SetOutputReport](https://learn.microsoft.com/windows-hardware/drivers/ddi/hidsdi/nf-hidsdi-hidd_setoutputreport)
- [OpenChatMix: SteelSeries HID protocol table](https://github.com/Swiftlyx/OpenChatMix#readme)
- [HeadsetControl: Nova Pro Wireless status query](https://github.com/Sapd/HeadsetControl/blob/master/lib/devices/steelseries_arctis_nova_pro_wireless.hpp)

MIT licensed. Use at your own risk; compatibility with future Windows, GG, headset firmware, or KVM updates is not guaranteed.
