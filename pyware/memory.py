"""Process memory via native NT calls (ntdll), skipping the kernel32 wrapper layer."""
import ctypes
from struct import unpack

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

VM_READ, VM_WRITE, VM_OP, QUERY = 0x0010, 0x0020, 0x0008, 0x0400

_k32 = ctypes.windll.kernel32
_ntdll = ctypes.windll.ntdll


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_void_p),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("th32ModuleID", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("GlblcntUsage", ctypes.c_ulong),
        ("ProccntUsage", ctypes.c_ulong),
        ("modBaseAddr", ctypes.c_void_p),
        ("modBaseSize", ctypes.c_ulong),
        ("hModule", ctypes.c_void_p),
        ("szModule", ctypes.c_char * 256),
        ("szExePath", ctypes.c_wchar * 260),
    ]


class Memory:
    def __init__(self):
        self.handle = None
        self.pid = 0
        self.base = 0

    @staticmethod
    def is_valid(p):
        return isinstance(p, int) and 0x10000 < p <= 0x7FFFFFFEFFFF

    @property
    def attached(self):
        return self.handle not in (None, 0)

    # ---------- attach ----------
    def find_pid(self, name):
        if _HAS_PSUTIL:
            try:
                for proc in psutil.process_iter(["pid", "name"]):
                    try:
                        if (proc.info["name"] or "").lower() == name.lower():
                            return proc.info["pid"]
                    except Exception:
                        continue
            except Exception:
                pass
        try:
            snap = _k32.CreateToolhelp32Snapshot(0x2, 0)
            if snap == -1:
                return 0
            e = PROCESSENTRY32()
            e.dwSize = ctypes.sizeof(PROCESSENTRY32)
            if _k32.Process32FirstW(snap, ctypes.byref(e)):
                while True:
                    try:
                        if e.szExeFile.lower() == name.lower():
                            pid = e.th32ProcessID
                            _k32.CloseHandle(snap)
                            return pid
                    except Exception:
                        pass
                    if not _k32.Process32NextW(snap, ctypes.byref(e)):
                        break
            _k32.CloseHandle(snap)
        except Exception:
            pass
        return 0

    def open(self, pid):
        try:
            self.pid = pid
            self.handle = _k32.OpenProcess(VM_READ | VM_WRITE | VM_OP | QUERY, False, pid)
            return self.attached
        except Exception:
            return False

    def module_base(self, module="RobloxPlayerBeta.exe"):
        try:
            snap = _k32.CreateToolhelp32Snapshot(0x8 | 0x10, self.pid)
            if snap == -1:
                return 0
            e = MODULEENTRY32()
            e.dwSize = ctypes.sizeof(MODULEENTRY32)
            if _k32.Module32First(snap, ctypes.byref(e)):
                while True:
                    try:
                        if e.szModule.decode(errors="ignore").lower() == module.lower():
                            base = e.modBaseAddr
                            _k32.CloseHandle(snap)
                            return base
                    except Exception:
                        pass
                    if not _k32.Module32Next(snap, ctypes.byref(e)):
                        break
            _k32.CloseHandle(snap)
        except Exception:
            pass
        return 0

    def attach(self, name="RobloxPlayerBeta"):
        self.close()
        pid = self.find_pid(name + ".exe")
        if not pid or not self.open(pid):
            return False
        self.base = self.module_base()
        return self.base != 0

    def close(self):
        try:
            if self.attached:
                _k32.CloseHandle(self.handle)
        except Exception:
            pass
        self.handle = None
        self.pid = 0
        self.base = 0

    # ---------- read ----------
    def read(self, address, size):
        if not self.attached or not self.is_valid(address) or size <= 0 or size > 4096:
            return b"\x00" * size
        try:
            buf = (ctypes.c_byte * size)()
            nread = ctypes.c_ulong(0)
            st = _ntdll.NtReadVirtualMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(nread))
            if st != 0:
                return b"\x00" * size
            return bytes(buf)
        except Exception:
            return b"\x00" * size

    def u64(self, a):
        d = self.read(a, 8)
        return unpack("<Q", d)[0] if len(d) == 8 else 0

    def u32(self, a):
        d = self.read(a, 4)
        return unpack("<I", d)[0] if len(d) == 4 else 0

    def i32(self, a):
        d = self.read(a, 4)
        return unpack("<i", d)[0] if len(d) == 4 else 0

    def f32(self, a):
        import math
        d = self.read(a, 4)
        v = unpack("<f", d)[0] if len(d) == 4 else 0.0
        return v if math.isfinite(v) else 0.0

    def vec3(self, a):
        d = self.read(a, 12)
        if len(d) < 12:
            return (0.0, 0.0, 0.0)
        x, y, z = unpack("<fff", d)
        import math
        if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
            return (0.0, 0.0, 0.0)
        return (x, y, z)

    def mat16(self, a):
        d = self.read(a, 64)
        if len(d) < 64:
            return [0.0] * 16
        return list(unpack("<16f", d))

    def vec2(self, a):
        d = self.read(a, 8)
        if len(d) < 8:
            return (0.0, 0.0)
        return unpack("<ff", d)

    def ascii(self, address, n):
        if n <= 0 or n > 512 or not self.is_valid(address):
            return ""
        try:
            return self.read(address, n).split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def rbx_string(self, obj):
        """MSVC SSO string: len at +0x10, ptr at +0 if long else inline."""
        try:
            ln = self.i32(obj + 0x10)
            if ln <= 0 or ln > 255:
                return ""
            data = self.u64(obj) if ln >= 16 else obj
            if ln >= 16 and not self.is_valid(data):
                return ""
            return self.ascii(data, ln)
        except Exception:
            return ""

    # ---------- write ----------
    def write(self, address, data):
        if not self.attached or not self.is_valid(address):
            return False
        try:
            buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
            nwr = ctypes.c_ulong(0)
            st = _ntdll.NtWriteVirtualMemory(self.handle, ctypes.c_void_p(address), buf, len(data), ctypes.byref(nwr))
            return st == 0
        except Exception:
            return False

    def write_u64(self, a, v):
        from struct import pack
        return self.write(a, pack("<Q", v))

    def write_f32(self, a, v):
        from struct import pack
        return self.write(a, pack("<f", v))

    def write_vec3(self, a, v):
        from struct import pack
        return self.write(a, pack("<fff", v[0], v[1], v[2]))
