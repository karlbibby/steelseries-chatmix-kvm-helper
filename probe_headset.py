"""Windows HID inventory and narrowly scoped Nova Pro Wireless commands.

Default: inventory only. --enable-only sends two transient mode enables and
never reads input reports. --query is an explicit diagnostic status request.
Uses only the Python standard library and built-in Windows APIs.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import json
import sys
import time
from pathlib import Path

class GUID(C.Structure):
    _fields_ = [('a', W.DWORD), ('b', W.WORD), ('c', W.WORD), ('d', C.c_ubyte * 8)]

class INTERFACE(C.Structure):
    _fields_ = [('size', W.DWORD), ('guid', GUID), ('flags', W.DWORD), ('reserved', C.c_size_t)]

class CAPS(C.Structure):
    _fields_ = [('Usage', W.WORD), ('UsagePage', W.WORD),
                ('InputReportByteLength', W.WORD), ('OutputReportByteLength', W.WORD),
                ('FeatureReportByteLength', W.WORD), ('Reserved', W.WORD * 17),
                ('counts', W.WORD * 10)]

class OVERLAPPED(C.Structure):
    _fields_ = [('Internal', C.c_size_t), ('InternalHigh', C.c_size_t),
                ('Offset', W.DWORD), ('OffsetHigh', W.DWORD), ('hEvent', W.HANDLE)]

def bind_apis():
    if sys.platform != 'win32':
        raise RuntimeError('This helper supports Windows only')
    k = C.WinDLL('kernel32', use_last_error=True)
    s = C.WinDLL('setupapi', use_last_error=True)
    h = C.WinDLL('hid', use_last_error=True)
    declarations = [
        (k.CreateFileW, [W.LPCWSTR,W.DWORD,W.DWORD,C.c_void_p,W.DWORD,W.DWORD,W.HANDLE], W.HANDLE),
        (k.CloseHandle, [W.HANDLE], W.BOOL),
        (k.CreateEventW, [C.c_void_p,W.BOOL,W.BOOL,W.LPCWSTR], W.HANDLE),
        (k.WaitForSingleObject, [W.HANDLE,W.DWORD], W.DWORD),
        (k.CancelIoEx, [W.HANDLE,C.POINTER(OVERLAPPED)], W.BOOL),
        (k.GetOverlappedResult, [W.HANDLE,C.POINTER(OVERLAPPED),C.POINTER(W.DWORD),W.BOOL], W.BOOL),
        (k.ReadFile, [W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)], W.BOOL),
        (k.WriteFile, [W.HANDLE,C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.POINTER(OVERLAPPED)], W.BOOL),
        (h.HidD_GetHidGuid, [C.POINTER(GUID)], None),
        (h.HidD_GetPreparsedData, [W.HANDLE,C.POINTER(C.c_void_p)], C.c_ubyte),
        (h.HidD_FreePreparsedData, [C.c_void_p], C.c_ubyte),
        (h.HidP_GetCaps, [C.c_void_p,C.POINTER(CAPS)], W.LONG),
        (h.HidD_SetOutputReport, [W.HANDLE,C.c_void_p,W.DWORD], C.c_ubyte),
        (s.SetupDiGetClassDevsW, [C.POINTER(GUID),W.LPCWSTR,W.HWND,W.DWORD], W.HANDLE),
        (s.SetupDiEnumDeviceInterfaces, [W.HANDLE,C.c_void_p,C.POINTER(GUID),W.DWORD,C.POINTER(INTERFACE)], W.BOOL),
        (s.SetupDiGetDeviceInterfaceDetailW, [W.HANDLE,C.POINTER(INTERFACE),C.c_void_p,W.DWORD,C.POINTER(W.DWORD),C.c_void_p], W.BOOL),
        (s.SetupDiDestroyDeviceInfoList, [W.HANDLE], W.BOOL),
    ]
    for function, arguments, result in declarations:
        function.argtypes = arguments
        function.restype = result
    return k, s, h

INVALID = C.c_void_p(-1).value

def inventory(apis):
    k, s, h = apis
    guid = GUID()
    h.HidD_GetHidGuid(C.byref(guid))
    devices = s.SetupDiGetClassDevsW(C.byref(guid), None, None, 0x12)
    if devices == INVALID:
        raise C.WinError(C.get_last_error())
    results = []
    try:
        for index in range(512):
            interface = INTERFACE()
            interface.size = C.sizeof(interface)
            if not s.SetupDiEnumDeviceInterfaces(devices, None, C.byref(guid), index, C.byref(interface)):
                error = C.get_last_error()
                if error != 259:
                    raise C.WinError(error)
                break
            needed = W.DWORD()
            s.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), None, 0, C.byref(needed), None)
            if not needed.value:
                raise C.WinError(C.get_last_error())
            detail = C.create_string_buffer(needed.value)
            C.cast(detail, C.POINTER(W.DWORD))[0] = 8 if C.sizeof(C.c_void_p) == 8 else 6
            if not s.SetupDiGetDeviceInterfaceDetailW(devices, C.byref(interface), detail, needed.value, None, None):
                raise C.WinError(C.get_last_error())
            path = C.wstring_at(C.addressof(detail) + 4)
            if 'vid_1038&pid_12e0' not in path.lower():
                continue
            result = {'path': path}
            results.append(result)
            handle = k.CreateFileW(path, 0, 3, None, 3, 0, None)
            if handle == INVALID:
                result['metadata_open_error'] = C.get_last_error()
                continue
            try:
                data = C.c_void_p()
                if h.HidD_GetPreparsedData(handle, C.byref(data)):
                    try:
                        caps = CAPS()
                        status = h.HidP_GetCaps(data, C.byref(caps))
                        if status != 0x110000:
                            raise RuntimeError(f'HidP_GetCaps failed: {status:#x}')
                        result['caps'] = {field: getattr(caps, field) for field in
                            ('Usage','UsagePage','InputReportByteLength','OutputReportByteLength','FeatureReportByteLength')}
                    finally:
                        h.HidD_FreePreparsedData(data)
            finally:
                k.CloseHandle(handle)
    finally:
        s.SetupDiDestroyDeviceInfoList(devices)
    return results

def select_target(devices):
    matches = [d for d in devices if 'mi_04&col01' in d['path'].lower()
               and d.get('caps', {}).get('UsagePage') == 0xFFC0
               and d['caps'].get('OutputReportByteLength') == 64
               and d['caps'].get('InputReportByteLength') == 64]
    if len(matches) > 1:
        raise RuntimeError('Multiple matching base stations; no commands were sent')
    return matches[0] if matches else None

def overlapped_io(k, handle, write, payload):
    buffer = C.create_string_buffer(payload) if isinstance(payload, int) else C.create_string_buffer(payload, len(payload))
    count = W.DWORD()
    operation = OVERLAPPED()
    operation.hEvent = k.CreateEventW(None, True, False, None)
    if not operation.hEvent:
        raise C.WinError(C.get_last_error())
    started = time.perf_counter()
    try:
        function = k.WriteFile if write else k.ReadFile
        ok = function(handle, buffer, len(buffer), C.byref(count), C.byref(operation))
        error = C.get_last_error() if not ok else 0
        if not ok and error == 997:
            if k.WaitForSingleObject(operation.hEvent, 1500) == 258:
                k.CancelIoEx(handle, C.byref(operation))
                k.GetOverlappedResult(handle, C.byref(operation), C.byref(count), True)
                return {'ok': False, 'error': 'timeout', 'ms': round((time.perf_counter()-started)*1000,2)}
            ok = k.GetOverlappedResult(handle, C.byref(operation), C.byref(count), False)
            error = C.get_last_error() if not ok else 0
        result = {'ok': bool(ok), 'error': error, 'bytes': count.value,
                  'ms': round((time.perf_counter()-started)*1000,2)}
        if not write and ok:
            result['hex'] = buffer.raw[:count.value].hex(' ')
        return result
    finally:
        k.CloseHandle(operation.hEvent)

def control_report(h, handle, command):
    # Only exact protocol commands known to this helper are accepted.
    if command not in (b'\x06\x49\x01', b'\x06\x8d\x01', b'\x06\xb0'):
        raise ValueError('Command is not in the diagnostic allowlist')
    packet = command + bytes(64-len(command))
    buffer = C.create_string_buffer(packet, len(packet))
    started = time.perf_counter()
    ok = h.HidD_SetOutputReport(handle, buffer, len(packet))
    return {'command': command.hex(' '), 'ok': bool(ok), 'error': 0 if ok else C.get_last_error(),
            'ms': round((time.perf_counter()-started)*1000,2)}

def run(apis, enable=False, query=False, control=False):
    k, _, h = apis
    devices = inventory(apis)
    target = select_target(devices)  # Validate uniqueness BEFORE any commands.
    if target and (enable or query):
        handle = k.CreateFileW(target['path'], 0xC0000000, 3, None, 3, 0x40000000, None)
        if handle == INVALID:
            target['rw_open_error'] = C.get_last_error()
            return devices
        try:
            if enable:
                target['chatmix_enable'] = [control_report(h, handle, command)
                    for command in (b'\x06\x49\x01', b'\x06\x8d\x01')]
            if query:
                target['status_write'] = (control_report(h, handle, b'\x06\xb0') if control else
                    overlapped_io(k, handle, True, b'\x06\xb0' + bytes(62)))
                if target['status_write']['ok']:
                    target['status_reads'] = []
                    for _ in range(3):
                        reply = overlapped_io(k, handle, False, 64)
                        target['status_reads'].append(reply)
                        if not reply['ok'] or reply.get('hex','').startswith('06 b0'):
                            break
        finally:
            k.CloseHandle(handle)
    return devices

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label', nargs='?', default='inventory')
    parser.add_argument('--enable-only', action='store_true', help='Submit two temporary ChatMix enables; no input reads')
    parser.add_argument('--query', action='store_true', help='Send status query and read its reply (diagnostic only)')
    parser.add_argument('--control', action='store_true', help='Send status query using HidD_SetOutputReport')
    parser.add_argument('--no-save', action='store_true')
    args = parser.parse_args()
    if args.enable_only and args.query:
        parser.error('--enable-only and --query cannot be combined')
    if not args.label or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_' for c in args.label):
        parser.error('Label must contain only letters, digits, hyphens or underscores')
    result = {'time': time.strftime('%Y-%m-%d %H:%M:%S'), 'label': args.label,
              'devices': run(bind_apis(), args.enable_only, args.query, args.control)}
    if not args.no_save:
        (Path(__file__).parent / (args.label + '.json')).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()
