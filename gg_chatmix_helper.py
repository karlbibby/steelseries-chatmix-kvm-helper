"""User-mode ChatMix workaround; no driver install or startup registration."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
GG = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'SteelSeries/GG/SteelSeriesGG.exe'
GG_HOST = GG.with_name('SteelSeriesGGEZ.exe')
RECOVERY_INTERVAL = 30
K = C.WinDLL('kernel32', use_last_error=True)
K.CreateMutexW.argtypes = [C.c_void_p, W.BOOL, W.LPCWSTR]
K.CreateMutexW.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.CreateToolhelp32Snapshot.argtypes = [W.DWORD, W.DWORD]
K.CreateToolhelp32Snapshot.restype = W.HANDLE

class PROCESSENTRY32W(C.Structure):
    _fields_ = [('dwSize', W.DWORD), ('cntUsage', W.DWORD),
                ('th32ProcessID', W.DWORD), ('th32DefaultHeapID', C.c_size_t),
                ('th32ModuleID', W.DWORD), ('cntThreads', W.DWORD),
                ('th32ParentProcessID', W.DWORD), ('pcPriClassBase', W.LONG),
                ('dwFlags', W.DWORD), ('szExeFile', W.WCHAR * 260)]

K.Process32FirstW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]
K.Process32NextW.argtypes = [W.HANDLE, C.POINTER(PROCESSENTRY32W)]

def gg_processes():
    snapshot = K.CreateToolhelp32Snapshot(2, 0)
    if snapshot == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        item = PROCESSENTRY32W()
        item.dwSize = C.sizeof(item)
        found = []
        ok = K.Process32FirstW(snapshot, C.byref(item))
        while ok:
            if item.szExeFile.lower() in ('steelseriesgg.exe', 'steelseriesengine.exe'):
                found.append((item.szExeFile.lower(), item.th32ProcessID))
            ok = K.Process32NextW(snapshot, C.byref(item))
        return tuple(sorted(found))
    finally:
        K.CloseHandle(snapshot)

def probe(enable=False):
    args = [sys.executable, str(ROOT / 'probe_headset.py'), 'helper', '--no-save']
    if enable:
        args.append('--enable-only')
    result = subprocess.run(args, capture_output=True, text=True, timeout=10,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f'Probe exited {result.returncode}')
    devices = json.loads(result.stdout)['devices']
    targets = [d for d in devices if d.get('caps', {}).get('UsagePage') == 0xFFC0]
    if len(targets) > 1:
        raise RuntimeError('Multiple matching base stations: no automatic selection')
    return targets

def apply():
    targets = probe(enable=True)
    if not targets:
        logging.info('Base station not connected')
        return False
    commands = targets[0].get('chatmix_enable', [])
    success = len(commands) == 2 and all(c['ok'] for c in commands)
    logging.info('ChatMix enable %s: %s', 'submitted' if success else 'FAILED', commands)
    return success

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--once', action='store_true', help='Apply once without opening GG')
    parser.add_argument('--check', action='store_true', help='Inspect only; send no commands')
    parser.add_argument('--startup', action='store_true', help='Start GG in its normal background startup mode')
    args = parser.parse_args()
    handler = RotatingFileHandler(ROOT / 'gg-chatmix-helper.log', maxBytes=200000, backupCount=2)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[handler])
    if args.check:
        print(json.dumps({'processes': gg_processes(), 'base_station_found': bool(probe())}))
        return 0
    if args.once:
        return 0 if apply() else 1
    if not GG.is_file():
        raise FileNotFoundError(GG)
    # Preserve GG's original host/auto startup mode at Windows login.
    if args.startup:
        if not gg_processes():
            data_path = Path(os.environ.get('ProgramData', r'C:\ProgramData')) / 'SteelSeries/GG'
            subprocess.Popen([str(GG_HOST), f'-dataPath={data_path}',
                              '-dbEnv=production', '-auto=true'],
                             creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        subprocess.Popen([str(GG)], creationflags=subprocess.CREATE_NO_WINDOW)
    mutex = K.CreateMutexW(None, False, 'Local\\NovaProKvmChatMixHelper')
    already_running = C.get_last_error() == 183
    if not mutex:
        raise C.WinError(C.get_last_error())
    try:
        if already_running:
            return 0
        logging.info('Helper started; periodic recovery every %s seconds; startup=%s', RECOVERY_INTERVAL, args.startup)
        previous = None
        pending = []
        last_gg = time.monotonic()
        last_apply = None
        while True:
            now = time.monotonic()
            processes = gg_processes()
            if processes:
                last_gg = now
            elif now - last_gg > 60:
                logging.info('GG closed; helper exiting')
                return 0
            try:
                targets = probe()
                path = targets[0]['path'] if targets else None
                identity = (processes, path)
                if identity != previous:
                    previous = identity
                    # Bounded retries allow GG's initial device setup to settle.
                    pending = [now + delay for delay in (2, 10, 25)] if processes and path else []
                    logging.info('GG/device connection changed; %s', 'enable scheduled' if pending else 'waiting')
                initial_due = bool(pending and now >= pending[0])
                recovery_due = bool(processes and path and not pending and
                                    (last_apply is None or now - last_apply >= RECOVERY_INTERVAL))
                if initial_due or recovery_due:
                    if initial_due:
                        pending.pop(0)
                    logging.info('Applying %s recovery', 'connection/startup' if initial_due else 'periodic')
                    apply()
                    last_apply = time.monotonic()
            except (RuntimeError, subprocess.TimeoutExpired, ValueError, OSError) as error:
                logging.warning('Diagnostic error: %s', error)
            time.sleep(2)
    finally:
        K.CloseHandle(mutex)

if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        logging.exception('Helper stopped unexpectedly')
        raise
