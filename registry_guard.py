# registry_guard.py
# ============================================================
# ImanAI Registry Guard - مدیریت شناسه ثابت سیستم
# نسخه 2.0 (Production-Ready)
# ============================================================
# تغییرات v2.0:
# ✅ اضافه شدن BIOS UUID (ضد جعل)
# ✅ اضافه شدن CPU ID (ضد جعل)
# ✅ Anti-Copy Protection (fingerprint check)
# ✅ HWID کوتاه برای تلفن
# ✅ ذخیره‌سازی دوگانه (ProgramData + Registry)
# ✅ Backup خودکار
# ✅ Logging حرفه‌ای
# ============================================================

import os
import sys
import json
import hashlib
import platform
import subprocess
import logging
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


# ============================================================
# ========== ثابت‌ها ==========
# ============================================================

APP_NAME = "ImanAI"
APP_VERSION = "2.0.0"

# مسیر ذخیره اصلی
PROGRAM_DATA_DIR = Path(os.environ.get('PROGRAMDATA', 'C:\\ProgramData'))
STORAGE_DIR = PROGRAM_DATA_DIR / APP_NAME
ID_FILE = STORAGE_DIR / "machine.id"
BACKUP_FILE = STORAGE_DIR / ".machine.bak"

# مسیر Registry (ویندوز)
REGISTRY_PATH = r"Software\ImanAI\System"
REGISTRY_KEY_MACHINE_ID = "MachineID"
REGISTRY_KEY_FINGERPRINT = "Fingerprint"

# ماژیک برای validation
MACHINE_ID_PREFIX = "IACC"
MACHINE_ID_LENGTH = 32  # بعد از prefix
SHORT_ID_LENGTH = 16   # برای نمایش کوتاه

# Subprocess flags (برای مخفی کردن پنجره)
if os.name == 'nt':
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
    STARTUPINFO = subprocess.STARTUPINFO()
    STARTUPINFO.dwFlags |= subprocess.STARTF_USESHOWWINDOW
else:
    CREATE_NO_WINDOW = 0
    STARTUPINFO = None


# ============================================================
# ========== توابع کمکی ==========
# ============================================================

def _run_wmic_command(args: list) -> str:
    """
    اجرای امن دستور wmic
    Returns: خروجی خط دوم (بعد از header)
    """
    if os.name != 'nt':
        return ""
    
    try:
        result = subprocess.run(
            ["wmic"] + args,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=CREATE_NO_WINDOW,
            startupinfo=STARTUPINFO
        )
        
        if result.returncode != 0:
            return ""
        
        lines = result.stdout.strip().split('\n')
        if len(lines) > 1:
            return lines[1].strip()
        return ""
    
    except subprocess.TimeoutExpired:
        logger.warning(f"⚠️ WMIC timeout: {args}")
        return ""
    except FileNotFoundError:
        logger.debug("WMIC not found (Windows without WMIC)")
        return ""
    except Exception as e:
        logger.debug(f"WMIC error: {e}")
        return ""


def _validate_hwid_format(hwid: str) -> bool:
    """اعتبارسنجی فرمت HWID"""
    if not hwid:
        return False
    
    if not hwid.startswith(f"{MACHINE_ID_PREFIX}-"):
        return False
    
    clean = hwid[len(MACHINE_ID_PREFIX) + 1:]
    
    if len(clean) != MACHINE_ID_LENGTH:
        return False
    
    # فقط hex characters
    if not all(c in '0123456789ABCDEF' for c in clean):
        return False
    
    return True


# ============================================================
# ========== MachineIDManager ==========
# ============================================================

class MachineIDManager:
    """
    مدیریت شناسه ثابت سیستم
    
    ویژگی‌ها:
    - تولید HWID قوی بر اساس چند منبع سخت‌افزاری
    - Anti-Copy Protection با fingerprint check
    - ذخیره در ProgramData + Registry (dual storage)
    - قابلیت بازیابی از backup
    """
    
    def __init__(self):
        self.storage_dir = STORAGE_DIR
        self.id_file = ID_FILE
        self.backup_file = BACKUP_FILE
        
        # اطمینان از وجود پوشه
        self._ensure_directory()
        
        # Cache
        self._cached_id: Optional[str] = None
        self._cached_fingerprint: Optional[str] = None
    
    # ============================================================
    # ========== مدیریت دایرکتوری ==========
    # ============================================================
    
    def _ensure_directory(self):
        """اطمینان از وجود پوشه"""
        try:
            self.storage_dir.mkdir(parents=True, exist_ok=True)
            
            # مخفی کردن پوشه در ویندوز
            if os.name == 'nt':
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(
                        str(self.storage_dir), 2  # FILE_ATTRIBUTE_HIDDEN
                    )
                except Exception:
                    pass
        
        except Exception as e:
            logger.error(f"❌ خطا در ایجاد پوشه: {e}")
    
    # ============================================================
    # ========== خواندن منابع سخت‌افزاری ==========
    # ============================================================
    
    def _get_motherboard_serial(self) -> str:
        """سریال مادربرد (قوی - تغییرش سخته)"""
        result = _run_wmic_command(["baseboard", "get", "serialnumber"])
        
        # فیلتر مقادیر نامعتبر
        if result and result.lower() not in ('to be filled by o.e.m.', 'none', 'default string', ''):
            return f"MB:{result}"
        return ""
    
    def _get_bios_uuid(self) -> str:
        """
        UUID بایوس (خیلی قوی - از سخت‌افزار میاد)
        این مهم‌ترین منبع شناسایی هست
        """
        result = _run_wmic_command(["csproduct", "get", "uuid"])
        
        if result:
            # بررسی UUID معتبر
            invalid_uuids = [
                'ffffffff-ffff-ffff-ffff-ffffffffffff',
                '00000000-0000-0000-0000-000000000000',
                '03000200-0400-0500-0006-000700080009',
            ]
            if result.lower() not in invalid_uuids:
                return f"BIOS:{result}"
        
        return ""
    
    def _get_cpu_id(self) -> str:
        """Processor ID (متوسط - معمولاً تغییر نمی‌کنه)"""
        result = _run_wmic_command(["cpu", "get", "ProcessorId"])
        
        if result and result.lower() not in ('none', ''):
            return f"CPU:{result}"
        return ""
    
    def _get_disk_serial(self) -> str:
        """سریال هارد دیسک اول"""
        result = _run_wmic_command(["diskdrive", "get", "serialnumber"])
        
        if result and result.lower() not in ('none', ''):
            return f"HDD:{result}"
        return ""
    
    def _get_mac_address(self) -> str:
        """
        MAC Address (ضعیف - قابل تغییره)
        فقط به عنوان fallback استفاده میشه
        """
        try:
            node = uuid.getnode()
            # بررسی randomized MAC
            if node >> 40 & 0x02:
                # Local administered bit set - احتمالاً randomized
                return ""
            
            mac = ':'.join(['{:02x}'.format((node >> i) & 0xff) for i in range(0, 48, 8)])
            return f"MAC:{mac}"
        except Exception:
            return ""
    
    # ============================================================
    # ========== محاسبه Fingerprint ============
    # ============================================================
    
    def _get_machine_fingerprint(self) -> str:
        """
        محاسبه fingerprint (اثر انگشت) سخت‌افزاری
        
        Returns: 32-char hex string
        """
        # جمع‌آوری منابع (به ترتیب اهمیت)
        components = [
            self._get_bios_uuid(),       # خیلی قوی
            self._get_motherboard_serial(),  # خیلی قوی
            self._get_cpu_id(),           # متوسط
            self._get_disk_serial(),      # متوسط
        ]
        
        # فیلتر خالی‌ها
        valid = [c for c in components if c]
        
        # اگه کمتر از ۲ منبع قوی داشتیم → fallback
        if len(valid) < 2:
            logger.warning("⚠️ منابع سخت‌افزاری کافی نیست - استفاده از MAC")
            mac = self._get_mac_address()
            if mac:
                valid.append(mac)
            
            # هنوز کمه؟
            if len(valid) < 2:
                logger.error("❌ حتی یک منبع معتبر هم پیدا نشد!")
                # Fallback: کامپیوتر name + username
                fallback = f"FALLBACK:{platform.node()}:{os.environ.get('USERNAME', '')}"
                valid = [fallback]
        
        # ساخت unique string
        unique_string = "|".join(valid)
        
        # Hash
        return hashlib.sha256(unique_string.encode('utf-8')).hexdigest()[:MACHINE_ID_LENGTH].upper()
    
    # ============================================================
    # ========== ذخیره و بارگذاری ==========
    # ============================================================
    
    def _save_to_file(self, machine_id: str, fingerprint: str) -> bool:
        """ذخیره در فایل ProgramData"""
        try:
            data = {
                'machine_id': machine_id,
                'fingerprint': fingerprint,
                'created_at': datetime.now().isoformat(),
                'version': APP_VERSION,
                'os': platform.system(),
                'hostname': platform.node(),
            }
            
            # Atomic write
            temp_file = self.id_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # جایگزینی امن
            if self.id_file.exists():
                self.id_file.unlink()
            temp_file.rename(self.id_file)
            
            # backup
            try:
                import shutil
                shutil.copy2(self.id_file, self.backup_file)
            except Exception:
                pass
            
            # مخفی کردن فایل
            if os.name == 'nt':
                try:
                    import ctypes
                    ctypes.windll.kernel32.SetFileAttributesW(str(self.id_file), 2)
                    ctypes.windll.kernel32.SetFileAttributesW(str(self.backup_file), 2)
                except Exception:
                    pass
            
            return True
        
        except Exception as e:
            logger.error(f"❌ خطا در ذخیره فایل: {e}")
            return False
    
    def _save_to_registry(self, machine_id: str, fingerprint: str) -> bool:
        """ذخیره در Registry (پشتیبان)"""
        if os.name != 'nt':
            return False
        
        try:
            import winreg
            
            key = winreg.CreateKeyEx(
                winreg.HKEY_LOCAL_MACHINE,
                REGISTRY_PATH,
                0,
                winreg.KEY_WRITE
            )
            
            winreg.SetValueEx(key, REGISTRY_KEY_MACHINE_ID, 0, winreg.REG_SZ, machine_id)
            winreg.SetValueEx(key, REGISTRY_KEY_FINGERPRINT, 0, winreg.REG_SZ, fingerprint)
            winreg.CloseKey(key)
            
            return True
        
        except PermissionError:
            # نیاز به admin → از HKCU استفاده کن
            try:
                import winreg
                key = winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER,
                    REGISTRY_PATH,
                    0,
                    winreg.KEY_WRITE
                )
                winreg.SetValueEx(key, REGISTRY_KEY_MACHINE_ID, 0, winreg.REG_SZ, machine_id)
                winreg.SetValueEx(key, REGISTRY_KEY_FINGERPRINT, 0, winreg.REG_SZ, fingerprint)
                winreg.CloseKey(key)
                return True
            except Exception:
                return False
        except Exception as e:
            logger.debug(f"Registry save error: {e}")
            return False
    
    def _load_from_file(self) -> Optional[dict]:
        """بارگذاری از فایل"""
        if not self.id_file.exists():
            return None
        
        try:
            with open(self.id_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"⚠️ خطا در خواندن فایل: {e}")
            
            # تلاش از backup
            if self.backup_file.exists():
                try:
                    with open(self.backup_file, 'r', encoding='utf-8') as f:
                        return json.load(f)
                except Exception:
                    pass
            
            return None
    
    def _load_from_registry(self) -> Optional[dict]:
        """بارگذاری از Registry"""
        if os.name != 'nt':
            return None
        
        for hive in (None, True):
            try:
                import winreg
                
                if hive is None:
                    key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, REGISTRY_PATH)
                else:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REGISTRY_PATH)
                
                machine_id, _ = winreg.QueryValueEx(key, REGISTRY_KEY_MACHINE_ID)
                
                try:
                    fingerprint, _ = winreg.QueryValueEx(key, REGISTRY_KEY_FINGERPRINT)
                except FileNotFoundError:
                    fingerprint = ""
                
                winreg.CloseKey(key)
                
                if machine_id:
                    return {
                        'machine_id': machine_id,
                        'fingerprint': fingerprint,
                    }
            
            except FileNotFoundError:
                continue
            except Exception:
                continue
        
        return None
    
    def save_machine_id(self, machine_id: str, fingerprint: str = None):
        """ذخیره HWID در همه منابع"""
        if fingerprint is None:
            fingerprint = self._get_machine_fingerprint()
        
        self._save_to_file(machine_id, fingerprint)
        self._save_to_registry(machine_id, fingerprint)
        
        # Cache
        self._cached_id = machine_id
        self._cached_fingerprint = fingerprint
        
        logger.info(f"✅ HWID ذخیره شد: {self._format_short(machine_id)}")
    
    # ============================================================
    # ========== متد اصلی ==========
    # ============================================================
    
    def get_or_create_machine_id(self) -> str:
        """
        دریافت HWID موجود یا ایجاد جدید
        
        با Anti-Copy Protection:
        - اگه fingerprint مطابقت نداشت → فایل کپی شده → HWID جدید
        """
        # Cache
        if self._cached_id:
            return self._cached_id
        
        current_fingerprint = self._get_machine_fingerprint()
        
        # ===== ۱. تلاش از فایل =====
        file_data = self._load_from_file()
        if file_data:
            stored_id = file_data.get('machine_id', '')
            stored_fingerprint = file_data.get('fingerprint', '')
            
            if stored_id and _validate_hwid_format(stored_id):
                # ✅ Anti-Copy Check
                if stored_fingerprint and stored_fingerprint != current_fingerprint:
                    logger.warning(
                        f"⚠️ HWID file copied! "
                        f"Stored: {stored_fingerprint[:8]}... "
                        f"Current: {current_fingerprint[:8]}..."
                    )
                    # فایل کپی شده → HWID جدید بساز
                    return self._create_new_machine_id(current_fingerprint)
                
                # Fingerprint خالی بود (نسخه قدیمی) → مهاجرت
                if not stored_fingerprint:
                    logger.info("🔄 مهاجرت HWID قدیمی به نسخه جدید")
                    self.save_machine_id(stored_id, current_fingerprint)
                
                # Cache و برگردان
                self._cached_id = stored_id
                self._cached_fingerprint = current_fingerprint
                return stored_id
        
        # ===== ۲. تلاش از Registry =====
        registry_data = self._load_from_registry()
        if registry_data:
            stored_id = registry_data.get('machine_id', '')
            stored_fingerprint = registry_data.get('fingerprint', '')
            
            if stored_id and _validate_hwid_format(stored_id):
                # Anti-Copy Check
                if stored_fingerprint and stored_fingerprint != current_fingerprint:
                    logger.warning("⚠️ Registry HWID mismatch - generating new")
                    return self._create_new_machine_id(current_fingerprint)
                
                # ذخیره مجدد در فایل (بازیابی)
                self.save_machine_id(stored_id, current_fingerprint)
                return stored_id
        
        # ===== ۳. HWID جدید =====
        return self._create_new_machine_id(current_fingerprint)
    
    def _create_new_machine_id(self, fingerprint: str) -> str:
        """ایجاد HWID جدید"""
        machine_id = f"{MACHINE_ID_PREFIX}-{fingerprint}"
        
        self.save_machine_id(machine_id, fingerprint)
        
        logger.info(f"🆕 HWID جدید ساخته شد: {self._format_short(machine_id)}")
        
        return machine_id
    
    # ============================================================
    # ========== فرمت‌دهی ==========
    # ============================================================
    
    @staticmethod
    def _format_short(machine_id: str) -> str:
        """فرمت کوتاه برای لاگ"""
        if not machine_id:
            return ""
        clean = machine_id.replace(f"{MACHINE_ID_PREFIX}-", "")
        return "-".join(clean[i:i+4] for i in range(0, min(SHORT_ID_LENGTH, len(clean)), 4))
    
    @staticmethod
    def format_short_hwid(machine_id: str) -> str:
        """
        فرمت HWID کوتاه و خوانا برای تلفن
        
        IACC-A3F5B8C9D2E1F4A7B6C5D8E9F1A2B3C4
        → A3F5-B8C9-D2E1-F4A7
        """
        if not machine_id:
            return ""
        
        clean = machine_id.replace(f"{MACHINE_ID_PREFIX}-", "")
        short = clean[:SHORT_ID_LENGTH]
        
        groups = [short[i:i+4] for i in range(0, len(short), 4)]
        return "-".join(groups).upper()
    
    @staticmethod
    def format_full_hwid(machine_id: str) -> str:
        """
        فرمت HWID کامل با خط تیره
        IACC-A3F5B8C9-D2E1F4A7-B6C5D8E9-F1A2B3C4
        """
        if not machine_id:
            return ""
        
        prefix = f"{MACHINE_ID_PREFIX}-"
        if machine_id.startswith(prefix):
            clean = machine_id[len(prefix):]
        else:
            clean = machine_id
        
        groups = [clean[i:i+8] for i in range(0, len(clean), 8)]
        return prefix + "-".join(groups).upper()
    
    # ============================================================
    # ========== API عمومی ==========
    # ============================================================
    
    def get_short_machine_id(self) -> str:
        """دریافت HWID کوتاه برای نمایش"""
        full = self.get_or_create_machine_id()
        return self.format_short_hwid(full)
    
    def get_full_machine_id(self) -> str:
        """دریافت HWID کامل فرمت‌شده"""
        full = self.get_or_create_machine_id()
        return self.format_full_hwid(full)
    
    def get_machine_id_file_path(self) -> str:
        """مسیر فایل HWID"""
        return str(self.id_file)
    
    def verify_machine_id(self, machine_id: str) -> bool:
        """بررسی تطابق HWID با سیستم فعلی"""
        stored_id = self.get_or_create_machine_id()
        return stored_id == machine_id
    
    def reset_machine_id(self) -> str:
        """بازنشانی HWID (برای تست)"""
        try:
            if self.id_file.exists():
                self.id_file.unlink()
            if self.backup_file.exists():
                self.backup_file.unlink()
        except Exception as e:
            logger.warning(f"⚠️ خطا در حذف فایل: {e}")
        
        # پاک کردن Registry
        if os.name == 'nt':
            try:
                import winreg
                for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    try:
                        winreg.DeleteKey(hive, REGISTRY_PATH)
                    except FileNotFoundError:
                        pass
            except Exception:
                pass
        
        # Cache
        self._cached_id = None
        self._cached_fingerprint = None
        
        # ساخت جدید
        return self.get_or_create_machine_id()
    
    def get_diagnostics(self) -> dict:
        """اطلاعات تشخیصی برای پشتیبانی"""
        return {
            'storage_path': str(self.id_file),
            'backup_path': str(self.backup_file),
            'file_exists': self.id_file.exists(),
            'backup_exists': self.backup_file.exists(),
            'machine_id': self.get_or_create_machine_id(),
            'short_id': self.get_short_machine_id(),
            'os': platform.system(),
            'hostname': platform.node(),
            'components': {
                'bios_uuid': bool(self._get_bios_uuid()),
                'motherboard': bool(self._get_motherboard_serial()),
                'cpu': bool(self._get_cpu_id()),
                'disk': bool(self._get_disk_serial()),
                'mac': bool(self._get_mac_address()),
            },
        }


# ============================================================
# ========== Singleton ==========
# ============================================================

_manager_instance: Optional[MachineIDManager] = None


def get_machine_id_manager() -> MachineIDManager:
    """دریافت نمونه Singleton"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = MachineIDManager()
    return _manager_instance


# ============================================================
# ========== API سطح بالاو ==========
# ============================================================

def get_machine_id() -> str:
    """دریافت HWID کامل (با prefix)"""
    return get_machine_id_manager().get_or_create_machine_id()


def get_short_machine_id() -> str:
    """دریافت HWID کوتاه (برای نمایش به کاربر)"""
    return get_machine_id_manager().get_short_machine_id()


def get_full_machine_id() -> str:
    """دریافت HWID کامل فرمت‌شده"""
    return get_machine_id_manager().get_full_machine_id()


# ============================================================
# ========== تست ==========
# ============================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)s | %(message)s'
    )
    
    print("=" * 60)
    print(f"🖥️  ImanAI Machine ID Manager v{APP_VERSION}")
    print("=" * 60)
    
    manager = get_machine_id_manager()
    
    print(f"\n📁 مسیر ذخیره: {manager.get_machine_id_file_path()}")
    
    print(f"\n🖥️  منابع سخت‌افزاری:")
    print(f"   • BIOS UUID: {bool(manager._get_bios_uuid())}")
    print(f"   • Motherboard: {bool(manager._get_motherboard_serial())}")
    print(f"   • CPU ID: {bool(manager._get_cpu_id())}")
    print(f"   • Disk Serial: {bool(manager._get_disk_serial())}")
    print(f"   • MAC Address: {bool(manager._get_mac_address())}")
    
    print(f"\n🔑 HWID:")
    print(f"   • Full:  {manager.get_or_create_machine_id()}")
    print(f"   • Short: {manager.get_short_machine_id()}")
    print(f"   • Format: {manager.get_full_machine_id()}")
    
    print(f"\n📊 Diagnostics:")
    diag = manager.get_diagnostics()
    for key, value in diag.items():
        if key != 'components':
            print(f"   • {key}: {value}")
    
    print("\n" + "=" * 60)
    print("✅ تست کامل شد")
    print("=" * 60)
