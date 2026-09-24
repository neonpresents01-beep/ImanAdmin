# license_core.py
# ============================================================
# سیستم لایسنس ImanAccount - v4.0 (Product-Ready)
# ============================================================

import os
import sys
import json
import base64
import hashlib
import platform
import struct
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidSignature

# ========== Import Registry Guard ==========
try:
    from registry_guard import get_machine_id as _get_machine_id_from_registry
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False
    print("⚠️ registry_guard یافت نشد!")


# ============================================================
# ========== مسیرهای امن ==========
# ============================================================

def _get_secure_dir() -> Path:
    """مسیر امن برای ذخیره کلیدها (فقط توسعه‌دهنده)"""
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / "ImanAccount" / ".keys" if appdata else Path.home() / ".imanaccount" / ".keys"
    else:
        base = Path.home() / ".config" / "imanaccount" / ".keys"
    
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_user_data_dir() -> Path:
    """مسیر اطلاعات کاربر (license, trial)"""
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / "ImanAccount" if appdata else Path.home() / ".imanaccount"
    else:
        base = Path.home() / ".config" / "imanaccount"
    
    base.mkdir(parents=True, exist_ok=True)
    return base


def _secure_file(file_path: Path):
    """محدود کردن دسترسی فایل"""
    try:
        if os.name == 'nt':
            username = os.environ.get('USERNAME', '')
            if username:
                subprocess.run(
                    ['icacls', str(file_path),
                     '/inheritance:r',
                     '/grant:r', f'{username}:F'],
                    check=False, capture_output=True, timeout=5
                )
        else:
            os.chmod(file_path, 0o600)
    except Exception:
        pass


# ============================================================
# ========== ثابت‌ها ==========
# ============================================================

KEYS_DIR = _get_secure_dir()
USER_DATA_DIR = _get_user_data_dir()

PUBLIC_KEY_PATH = KEYS_DIR / "public_key.pem"
PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"
TRIAL_CERT_PATH = Path(__file__).parent / "trial_certificate.bin"

LICENSE_FILE = USER_DATA_DIR / "license.key"
TRIAL_FILE = USER_DATA_DIR / "trial.license"

# Trial Signature Salt (ثابت در همه نسخه‌ها)
TRIAL_SIGNATURE_SALT = b"ImanAI_Trial_Cert_v4_2025"

# Magic برای Trial Certificate
TRIAL_CERT_MAGIC = b"ITRL"  # Iman TRiaL
TRIAL_CERT_VERSION = 1


# ============================================================
# ========== کلاس LicenseCore ==========
# ============================================================

class LicenseCore:
    """
    سیستم لایسنس ImanAccount
    
    حالت فروشنده (is_seller=True):
      - کلید خصوصی + عمومی
      - تولید لایسنس
      - تولید Trial Certificate
    
    حالت مشتری (is_seller=False):
      - فقط کلید عمومی
      - بررسی لایسنس
      - استفاده از Trial Certificate
    """
    
    IS_SELLER_BUILD = False
    LICENSE_FORMAT_VERSION = "4.0.0"
    
    # پلاگین
    PLUGIN_MAGIC = b"IPLG"
    PLUGIN_FORMAT_VERSION = 3
    PLUGIN_APP_SALT = b"ImanAI_Plugin_Encryption_Salt_v4_2025"
    
    def __init__(self, is_seller: Optional[bool] = None):
        if is_seller is None:
            is_seller = self.IS_SELLER_BUILD
        
        self.is_seller = is_seller
        self.public_key = None
        self.private_key = None
        self._aes_key = None
        
        # بارگذاری کلیدها
        if self.is_seller:
            self._init_seller_keys()
        else:
            self._init_customer_keys()
        
        # کلید AES (برای رمزنگاری لایسنس)
        self._init_aes_key()
    
    # ============================================================
    # ========== مدیریت کلیدها ==========
    # ============================================================
    
    def _init_seller_keys(self):
        """فروشنده: کلید خصوصی + عمومی"""
        if PRIVATE_KEY_PATH.exists() and PUBLIC_KEY_PATH.exists():
            self._load_seller_keys()
        else:
            self._generate_seller_keys()
    
    def _init_customer_keys(self):
        """مشتری: فقط کلید عمومی (از فایل)"""
        if PUBLIC_KEY_PATH.exists():
            try:
                with open(PUBLIC_KEY_PATH, 'rb') as f:
                    self.public_key = serialization.load_pem_public_key(
                        f.read(),
                        backend=default_backend()
                    )
                self.private_key = None
                return
            except Exception as e:
                print(f"⚠️ خطا در بارگذاری کلید عمومی: {e}")
        
        # اگر فایل نبود، از embedded key استفاده کن
        embedded_key = self._get_embedded_public_key()
        if embedded_key:
            try:
                self.public_key = serialization.load_pem_public_key(
                    embedded_key.encode('utf-8'),
                    backend=default_backend()
                )
                self.private_key = None
                return
            except Exception as e:
                print(f"⚠️ خطا در بارگذاری embedded key: {e}")
        
        print("⚠️ کلید عمومی یافت نشد! برنامه با محدودیت اجرا می‌شه.")
        self.public_key = None
    
    @staticmethod
    def _get_embedded_public_key() -> Optional[str]:
        """
        کلید عمومی embed شده در کد
        این توسط build_customer.py تنظیم میشه
        """
        # PLACEHOLDER - build_customer.py این رو پر می‌کنه
        return None
    
    def _load_seller_keys(self):
        """بارگذاری کلیدهای فروشنده"""
        try:
            with open(PUBLIC_KEY_PATH, 'rb') as f:
                self.public_key = serialization.load_pem_public_key(
                    f.read(), backend=default_backend()
                )
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری کلید عمومی: {e}")
        
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_pem = f.read()
            
            password = self._get_key_password()
            
            self.private_key = serialization.load_pem_private_key(
                private_pem,
                password=password,
                backend=default_backend()
            )
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری کلید خصوصی: {e}")
            self.private_key = None
    
    def _get_key_password(self) -> Optional[bytes]:
        """دریافت رمز کلید خصوصی"""
        # از ENV
        env_pass = os.environ.get('IMANACCOUNT_KEY_PASSWORD')
        if env_pass:
            return env_pass.encode()
        
        # از فایل محلی (فقط توسعه)
        password_file = KEYS_DIR / "password.txt"
        if password_file.exists():
            try:
                with open(password_file, 'rb') as f:
                    return f.read().strip()
            except:
                pass
        
        # تعاملی
        if sys.stdin.isatty():
            try:
                import getpass
                password = getpass.getpass("🔐 رمز کلید خصوصی فروشنده: ")
                return password.encode() if password else None
            except:
                return None
        
        return None
    
    def _generate_seller_keys(self):
        """تولید کلیدهای فروشنده"""
        if not self.is_seller:
            raise PermissionError("❌ فقط فروشنده!")
        
        print("🔑 تولید کلیدهای RSA 4096-bit فروشنده...")
        
        password = self._get_key_password()
        if not password:
            raise ValueError(
                "❌ رمز کلید خصوصی الزامی است!\n"
                "متغیر محیطی IMANACCOUNT_KEY_PASSWORD را تنظیم کنید."
            )
        
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=4096,
            backend=default_backend()
        )
        
        # ذخیره کلید خصوصی (رمزنگاری‌شده)
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.BestAvailableEncryption(password)
        )
        
        with open(PRIVATE_KEY_PATH, 'wb') as f:
            f.write(private_pem)
        _secure_file(PRIVATE_KEY_PATH)
        
        # ذخیره کلید عمومی
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        )
        
        with open(PUBLIC_KEY_PATH, 'wb') as f:
            f.write(public_pem)
        _secure_file(PUBLIC_KEY_PATH)
        
        self.private_key = private_key
        self.public_key = public_key
        
        print(f"✅ کلیدها ذخیره شدند در {KEYS_DIR}")
    
    def _init_aes_key(self):
        """کلید AES محلی"""
        aes_path = KEYS_DIR / "aes.key"
        
        if aes_path.exists():
            try:
                with open(aes_path, 'rb') as f:
                    key = f.read()
                if len(key) == 32:
                    self._aes_key = key
                    return
            except:
                pass
        
        self._aes_key = os.urandom(32)
        
        with open(aes_path, 'wb') as f:
            f.write(self._aes_key)
        _secure_file(aes_path)
    
    # ============================================================
    # ========== HWID ==========
    # ============================================================
    
    @staticmethod
    def get_machine_id() -> str:
        """دریافت HWID"""
        if REGISTRY_AVAILABLE:
            try:
                return _get_machine_id_from_registry()
            except:
                pass
        
        # Fallback
        try:
            import uuid
            components = [
                platform.node() or '',
                platform.machine() or '',
                platform.processor() or '',
                os.environ.get('COMPUTERNAME', ''),
                os.environ.get('USERNAME', ''),
                str(uuid.getnode())
            ]
            data = '|'.join(components)
            hash_obj = hashlib.sha256(data.encode('utf-8'))
            return f"IACC-{hash_obj.hexdigest()[:32].upper()}"
        except:
            return "IACC-FALLBACK-000000000000000000000000"
    
    @staticmethod
    def get_system_hwid() -> str:
        return LicenseCore.get_machine_id()
    
    # ============================================================
    # ========== تولید لایسنس (فقط فروشنده) ==========
    # ============================================================
    
    def generate_license(
        self,
        customer_name: str,
        company: str = "",
        expire_days: int = 365,
        modules: Optional[List[str]] = None,
        limits: Optional[Dict[str, int]] = None,
        machine_id: Optional[str] = None,
        is_trial: bool = False
    ) -> Dict:
        """تولید لایسنس (فقط فروشنده)"""
        if not self.is_seller:
            raise PermissionError("❌ فقط فروشنده!")
        
        if self.private_key is None:
            raise ValueError("❌ کلید خصوصی در دسترس نیست!")
        
        if modules is None:
            modules = ['accounting', 'inventory', 'payroll', 'parties', 
                      'invoice', 'purchase']
        
        if limits is None:
            limits = {}
        
        if machine_id is None:
            machine_id = self.get_machine_id()
        
        # شناسه یکتا
        license_id = hashlib.sha256(
            f"{customer_name}|{machine_id}|{datetime.now().isoformat()}|{os.urandom(16).hex()}".encode()
        ).hexdigest()[:16].upper()
        
        now = datetime.now()
        expire_date = now + timedelta(days=expire_days)
        
        # کلید AES برای پلاگین‌ها
        plugin_aes_key = self._generate_plugin_aes_key(machine_id, license_id)
        
        payload = {
            'license_id': license_id,
            'customer': customer_name,
            'company': company,
            'machine_id': machine_id,
            'modules': modules,
            'limits': limits,
            'plugin_aes_key': plugin_aes_key,
            'created_at': now.isoformat(),
            'expire_date': expire_date.isoformat(),
            'version': self.LICENSE_FORMAT_VERSION,
            'is_trial': is_trial,
        }
        
        # امضا
        payload_bytes = json.dumps(
            payload, ensure_ascii=False, sort_keys=True
        ).encode('utf-8')
        
        signature = self.private_key.sign(
            payload_bytes,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        license_data = {
            'payload': payload,
            'signature': base64.b64encode(signature).decode('ascii')
        }
        
        encrypted = self._encrypt_data(license_data)
        
        return {
            'license_key': encrypted,
            'formatted': self._format_license_key(encrypted),
            'data': payload
        }
    
    # ============================================================
    # ========== بررسی لایسنس ==========
    # ============================================================
    
    def verify_license(self, license_key: str) -> Dict:
        """بررسی لایسنس (کامل)"""
        try:
            # ===== چک اگر لایسنس trial از پیش موجوده =====
            if license_key == "TRIAL":
                trial_data = self._load_trial_license()
                if trial_data:
                    return self._verify_trial(trial_data)
                return {
                    'valid': False,
                    'error': 'no_trial',
                    'message': '❌ لایسنس آزمایشی فعال نشده است!'
                }
            
            # ===== لایسنس معمولی =====
            if self.public_key is None:
                return {
                    'valid': False,
                    'error': 'no_public_key',
                    'message': '❌ کلید عمومی در دسترس نیست!'
                }
            
            clean_key = license_key.strip().replace('-', '').replace(' ', '')
            
            try:
                license_data = self._decrypt_data(clean_key)
            except Exception:
                return {
                    'valid': False,
                    'error': 'decrypt_failed',
                    'message': '❌ لایسنس نامعتبر یا خراب است'
                }
            
            if 'payload' not in license_data or 'signature' not in license_data:
                return {
                    'valid': False,
                    'error': 'malformed',
                    'message': '❌ ساختار لایسنس نامعتبر است!'
                }
            
            payload = license_data['payload']
            signature = base64.b64decode(license_data['signature'])
            
            payload_bytes = json.dumps(
                payload, ensure_ascii=False, sort_keys=True
            ).encode('utf-8')
            
            # بررسی امضا
            try:
                self.public_key.verify(
                    signature,
                    payload_bytes,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
            except InvalidSignature:
                return {
                    'valid': False,
                    'error': 'invalid_signature',
                    'message': '❌ لایسنس دستکاری شده است!'
                }
            
            # بررسی HWID
            current_machine_id = self.get_machine_id()
            if payload.get('machine_id') != current_machine_id:
                return {
                    'valid': False,
                    'error': 'machine_mismatch',
                    'message': (
                        f'❌ این لایسنس برای این سیستم صادر نشده است!\n'
                        f'HWID سیستم شما: {current_machine_id}'
                    )
                }
            
            # بررسی انقضا
            try:
                expire_date = datetime.fromisoformat(payload['expire_date'])
            except:
                return {
                    'valid': False,
                    'error': 'invalid_date',
                    'message': '❌ تاریخ انقضا نامعتبر است!'
                }
            
            now = datetime.now()
            if now > expire_date:
                days_expired = (now - expire_date).days
                return {
                    'valid': False,
                    'error': 'expired',
                    'message': (
                        f'❌ لایسنس منقضی شده است!\n'
                        f'تاریخ انقضا: {expire_date.strftime("%Y-%m-%d")}\n'
                        f'({days_expired} روز پیش)'
                    )
                }
            
            days_left = (expire_date - now).days
            
            return {
                'valid': True,
                'data': payload,
                'days_left': days_left,
                'message': f'✅ لایسنس معتبر | {payload.get("customer", "نامشخص")}',
                'is_expiring_soon': days_left <= 30
            }
        
        except Exception as e:
            return {
                'valid': False,
                'error': 'unknown',
                'message': f'❌ خطا: {str(e)}'
            }
    
    # ============================================================
    # ========== Trial (نسخه آزمایشی) ==========
    # ============================================================
    
    def create_trial_license(self) -> Dict:
        """
        ایجاد لایسنس آزمایشی 30 روزه
        
        فروشنده: خودش trial می‌سازه
        مشتری: از Trial Certificate از پیش ساخته استفاده می‌کنه
        """
        # بررسی استفاده قبلی
        if self._is_trial_used():
            return {
                'valid': False,
                'error': 'trial_used',
                'message': '❌ نسخه آزمایشی قبلاً در این سیستم استفاده شده است!'
            }
        
        if self.is_seller:
            return self._create_trial_as_seller()
        else:
            return self._create_trial_as_customer()
    
    def _create_trial_as_seller(self) -> Dict:
        """فروشنده: تولید trial با امضای واقعی"""
        try:
            license_data = self.generate_license(
                customer_name="نسخه آزمایشی ImanAccount",
                expire_days=30,
                modules=['accounting', 'inventory', 'payroll', 'parties',
                        'invoice', 'purchase', 'ai', 'reports'],
                limits={
                    'accounting': 50, 'inventory': 20, 'payroll': 5,
                    'parties': 10, 'invoice': 10, 'purchase': 10
                },
                is_trial=True
            )
            
            # ذخیره به عنوان trial
            trial_data = license_data['data'].copy()
            trial_data['is_trial'] = True
            trial_data['trial_signature'] = 'SELLER_SIGNED'  # علامت فروشنده
            
            self._save_trial_license(trial_data)
            self._mark_trial_used()
            
            return {
                'valid': True,
                'data': trial_data,
                'days_left': 30,
                'is_trial': True,
                'message': '✅ نسخه آزمایشی ۳۰ روزه فعال شد!'
            }
        except Exception as e:
            return {
                'valid': False,
                'error': 'trial_failed',
                'message': f'❌ خطا: {str(e)}'
            }
    
    def _create_trial_as_customer(self) -> Dict:
        """
        مشتری: استفاده از Trial Certificate از پیش ساخته
        
        این گواهی توسط فروشنده ساخته شده و در بیلد قرار داره
        مشتری HWID خودش رو جایگزین می‌کنه
        """
        # ===== ۱. بارگذاری Trial Certificate =====
        cert_data = self._load_trial_certificate()
        
        if not cert_data:
            return {
                'valid': False,
                'error': 'no_trial_certificate',
                'message': (
                    '❌ نسخه آزمایشی در این برنامه فعال نیست!\n'
                    'برای دریافت لایسنس با پشتیبانی تماس بگیرید.'
                )
            }
        
        # ===== ۲. ساخت trial برای این سیستم =====
        try:
            trial_payload = self._create_trial_from_certificate(cert_data)
            
            # ذخیره
            self._save_trial_license(trial_payload)
            self._mark_trial_used()
            
            days_left = (datetime.fromisoformat(trial_payload['expire_date']) - datetime.now()).days
            
            return {
                'valid': True,
                'data': trial_payload,
                'days_left': days_left,
                'is_trial': True,
                'message': f'✅ نسخه آزمایشی ۳۰ روزه فعال شد! ({days_left} روز)'
            }
        except Exception as e:
            return {
                'valid': False,
                'error': 'trial_failed',
                'message': f'❌ خطا در فعال‌سازی: {str(e)}'
            }
    
    def _load_trial_certificate(self) -> Optional[Dict]:
        """بارگذاری Trial Certificate"""
        if not TRIAL_CERT_PATH.exists():
            return None
        
        try:
            with open(TRIAL_CERT_PATH, 'rb') as f:
                cert_data = f.read()
            
            return self._parse_trial_certificate(cert_data)
        except Exception as e:
            print(f"⚠️ خطا در بارگذاری Trial Certificate: {e}")
            return None
    
    def _parse_trial_certificate(self, cert_data: bytes) -> Optional[Dict]:
        """
        تجزیه Trial Certificate
        
        فرمت:
        ┌────────────────────────────────┐
        │ Magic: "ITRL" (4 bytes)         │
        │ Version: 1 (1 byte)             │
        │ Cert Length: 4 bytes            │
        │ Certificate JSON: N bytes       │
        │ Signature: 256 bytes (RSA 2048) │
        └────────────────────────────────┘
        """
        try:
            if len(cert_data) < 9:
                return None
            
            if cert_data[:4] != TRIAL_CERT_MAGIC:
                return None
            
            version = cert_data[4]
            if version != TRIAL_CERT_VERSION:
                return None
            
            cert_len = struct.unpack('>I', cert_data[5:9])[0]
            cert_json = cert_data[9:9+cert_len]
            signature = cert_data[9+cert_len:]
            
            # تجزیه JSON
            cert = json.loads(cert_json.decode('utf-8'))
            
            # بررسی امضا
            if self.public_key is None:
                return None
            
            try:
                self.public_key.verify(
                    signature,
                    cert_json,
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
            except InvalidSignature:
                print("❌ امضای Trial Certificate نامعتبر است!")
                return None
            
            return cert
        except Exception as e:
            print(f"⚠️ خطا در تجزیه Trial Certificate: {e}")
            return None
    
    def _create_trial_from_certificate(self, cert: Dict) -> Dict:
        """ساخت trial license از certificate"""
        current_hwid = self.get_machine_id()
        
        now = datetime.now()
        expire_date = now + timedelta(days=cert.get('trial_days', 30))
        
        # شناسه trial منحصر به فرد برای این سیستم
        trial_id = hashlib.sha256(
            f"TRIAL:{current_hwid}:{now.isoformat()}".encode()
        ).hexdigest()[:16].upper()
        
        # کلید AES برای پلاگین‌ها
        plugin_aes_key = self._generate_plugin_aes_key(current_hwid, f"TRIAL_{trial_id}")
        
        trial_payload = {
            'license_id': f"TRIAL_{trial_id}",
            'customer': 'نسخه آزمایشی',
            'company': '',
            'machine_id': current_hwid,
            'modules': cert.get('modules', ['accounting', 'inventory', 'payroll']),
            'limits': cert.get('limits', {}),
            'plugin_aes_key': plugin_aes_key,
            'created_at': now.isoformat(),
            'expire_date': expire_date.isoformat(),
            'version': self.LICENSE_FORMAT_VERSION,
            'is_trial': True,
            'trial_cert_id': cert.get('cert_id', ''),
        }
        
        # امضای trial (با استفاده از salt مشخص)
        trial_signature = hashlib.sha256(
            f"TRIAL:{current_hwid}:{trial_id}:{expire_date.isoformat()}:{cert.get('cert_id', '')}".encode()
            + TRIAL_SIGNATURE_SALT
        ).hexdigest()
        
        trial_payload['trial_signature'] = trial_signature
        
        return trial_payload
    
    def _verify_trial(self, trial: Dict) -> Dict:
        """بررسی trial license"""
        try:
            # بررسی HWID
            current_hwid = self.get_machine_id()
            if trial.get('machine_id') != current_hwid:
                return {
                    'valid': False,
                    'error': 'trial_machine_mismatch',
                    'message': '❌ نسخه آزمایشی برای این سیستم صادر نشده است!'
                }
            
            # بررسی امضا
            trial_signature = trial.get('trial_signature', '')
            
            if trial_signature != 'SELLER_SIGNED':
                # بررسی امضای محلی
                trial_id = trial.get('license_id', '').replace('TRIAL_', '')
                expire_date_str = trial.get('expire_date', '')
                cert_id = trial.get('trial_cert_id', '')
                
                expected = hashlib.sha256(
                    f"TRIAL:{current_hwid}:{trial_id}:{expire_date_str}:{cert_id}".encode()
                    + TRIAL_SIGNATURE_SALT
                ).hexdigest()
                
                if expected != trial_signature:
                    return {
                        'valid': False,
                        'error': 'trial_tampered',
                        'message': '❌ نسخه آزمایشی دستکاری شده است!'
                    }
            
            # بررسی انقضا
            try:
                expire_date = datetime.fromisoformat(trial['expire_date'])
            except:
                return {
                    'valid': False,
                    'error': 'trial_invalid_date',
                    'message': '❌ تاریخ trial نامعتبر است!'
                }
            
            now = datetime.now()
            if now > expire_date:
                days_expired = (now - expire_date).days
                return {
                    'valid': False,
                    'error': 'trial_expired',
                    'message': (
                        f'❌ نسخه آزمایشی منقضی شده است!\n'
                        f'تاریخ انقضا: {expire_date.strftime("%Y-%m-%d")}\n'
                        f'({days_expired} روز پیش)\n'
                        f'برای خرید نسخه کامل با پشتیبانی تماس بگیرید.'
                    )
                }
            
            days_left = (expire_date - now).days
            
            return {
                'valid': True,
                'data': trial,
                'days_left': days_left,
                'is_trial': True,
                'message': f'✅ نسخه آزمایشی معتبر | {days_left} روز باقیمانده',
                'is_expiring_soon': days_left <= 7
            }
        
        except Exception as e:
            return {
                'valid': False,
                'error': 'trial_error',
                'message': f'❌ خطا: {str(e)}'
            }
    
    # ============================================================
    # ========== ذخیره و بارگذاری Trial ==========
    # ============================================================
    
    def _save_trial_license(self, payload: Dict):
        """ذخیره trial"""
        with open(TRIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _secure_file(TRIAL_FILE)
    
    def _load_trial_license(self) -> Optional[Dict]:
        """بارگذاری trial"""
        if not TRIAL_FILE.exists():
            return None
        
        try:
            with open(TRIAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    
    @staticmethod
    def _is_trial_used() -> bool:
        """بررسی استفاده از trial"""
        if os.name == 'nt':
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\ImanAccount",
                    0,
                    winreg.KEY_READ
                )
                try:
                    value, _ = winreg.QueryValueEx(key, "TrialUsed")
                    winreg.CloseKey(key)
                    return value == 1
                except FileNotFoundError:
                    winreg.CloseKey(key)
            except:
                pass
        else:
            marker = Path.home() / ".imanaccount" / ".trial_used"
            return marker.exists()
        
        return TRIAL_FILE.exists()
    
    @staticmethod
    def _mark_trial_used():
        """علامت‌گذاری trial"""
        if os.name == 'nt':
            try:
                import winreg
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\ImanAccount"
                )
                winreg.SetValueEx(key, "TrialUsed", 0, winreg.REG_DWORD, 1)
                winreg.SetValueEx(key, "TrialDate", 0, winreg.REG_SZ, datetime.now().isoformat())
                winreg.CloseKey(key)
            except:
                pass
        else:
            marker = Path.home() / ".imanaccount" / ".trial_used"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(datetime.now().isoformat())
    
    # ============================================================
    # ========== Trial Certificate Builder (فقط فروشنده) ==========
    # ============================================================
    
    def build_trial_certificate(
        self,
        trial_days: int = 30,
        modules: Optional[List[str]] = None,
        limits: Optional[Dict[str, int]] = None
    ) -> bytes:
        """
        ساخت Trial Certificate (فقط فروشنده)
        
        این گواهی در بیلد مشتری قرار می‌گیره و
        به مشتری اجازه trial میده
        """
        if not self.is_seller:
            raise PermissionError("❌ فقط فروشنده!")
        
        if self.private_key is None:
            raise ValueError("❌ کلید خصوصی در دسترس نیست!")
        
        if modules is None:
            modules = ['accounting', 'inventory', 'payroll', 'parties',
                      'invoice', 'purchase', 'ai', 'reports']
        
        if limits is None:
            limits = {
                'accounting': 50, 'inventory': 20, 'payroll': 5,
                'parties': 10, 'invoice': 10, 'purchase': 10
            }
        
        # شناسه certificate
        cert_id = hashlib.sha256(
            f"TRIAL_CERT:{datetime.now().isoformat()}:{os.urandom(16).hex()}".encode()
        ).hexdigest()[:16].upper()
        
        cert = {
            'cert_id': cert_id,
            'trial_days': trial_days,
            'modules': modules,
            'limits': limits,
            'created_at': datetime.now().isoformat(),
            'version': '1.0.0',
        }
        
        # سریالایز
        cert_json = json.dumps(cert, ensure_ascii=False, sort_keys=True).encode('utf-8')
        
        # امضا
        signature = self.private_key.sign(
            cert_json,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        # ساخت فایل
        result = bytearray()
        result += TRIAL_CERT_MAGIC
        result += bytes([TRIAL_CERT_VERSION])
        result += struct.pack('>I', len(cert_json))
        result += cert_json
        result += signature
        
        return bytes(result)
    
    def save_trial_certificate(self, output_path: Optional[str] = None) -> bool:
        """ذخیره Trial Certificate"""
        try:
            cert_data = self.build_trial_certificate()
            
            if output_path is None:
                output_path = TRIAL_CERT_PATH
            
            with open(output_path, 'wb') as f:
                f.write(cert_data)
            
            print(f"✅ Trial Certificate ذخیره شد در: {output_path}")
            return True
        except Exception as e:
            print(f"❌ خطا: {e}")
            return False
    
    # ============================================================
    # ========== رمزنگاری AES ==========
    # ============================================================
    
    def _encrypt_data(self, data: dict) -> str:
        """رمزنگاری AES-GCM"""
        if self._aes_key is None:
            raise ValueError("کلید AES در دسترس نیست!")
        
        data_bytes = json.dumps(
            data, ensure_ascii=False, sort_keys=True
        ).encode('utf-8')
        
        aesgcm = AESGCM(self._aes_key)
        nonce = os.urandom(12)
        encrypted = aesgcm.encrypt(nonce, data_bytes, None)
        
        return base64.b64encode(nonce + encrypted).decode('ascii')
    
    def _decrypt_data(self, encrypted_key: str) -> dict:
        """رمزگشایی AES-GCM"""
        if self._aes_key is None:
            raise ValueError("کلید AES در دسترس نیست!")
        
        clean = encrypted_key.strip().replace('-', '').replace(' ', '')
        padding = (4 - len(clean) % 4) % 4
        clean += '=' * padding
        
        combined = base64.b64decode(clean)
        
        if len(combined) < 28:
            raise ValueError("لایسنس خیلی کوتاه")
        
        nonce = combined[:12]
        ciphertext = combined[12:]
        
        aesgcm = AESGCM(self._aes_key)
        data_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        
        return json.loads(data_bytes.decode('utf-8'))
    
    # ============================================================
    # ========== فرمت‌دهی ==========
    # ============================================================
    
    @staticmethod
    def _format_license_key(key: str) -> str:
        """فرمت‌دهی کلید"""
        clean = key.replace('-', '').replace(' ', '').replace('_', '')
        groups = [clean[i:i+4] for i in range(0, len(clean), 4)]
        return '-'.join(groups)
    
    # ============================================================
    # ========== ذخیره/بارگذاری لایسنس ==========
    # ============================================================
    
    def save_license(self, license_key: str, file_path: Optional[str] = None) -> bool:
        """ذخیره لایسنس"""
        try:
            target = Path(file_path) if file_path else LICENSE_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target, 'w', encoding='utf-8') as f:
                f.write(license_key)
            
            _secure_file(target)
            return True
        except Exception as e:
            print(f"⚠️ خطا: {e}")
            return False
    
    def load_license(self, file_path: Optional[str] = None) -> Optional[str]:
        """بارگذاری لایسنس"""
        try:
            target = Path(file_path) if file_path else LICENSE_FILE
            if target.exists():
                with open(target, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return None
        except:
            return None
    
    # ============================================================
    # ========== رمزنگاری پلاگین (فقط فروشنده) ==========
    # ============================================================
    
    def _generate_plugin_aes_key(self, machine_id: str, license_id: str) -> str:
        """تولید کلید AES برای پلاگین‌ها"""
        key_material = f"{machine_id}:{license_id}".encode('utf-8')
        
        key = hashlib.pbkdf2_hmac(
            'sha256',
            key_material,
            self.PLUGIN_APP_SALT,
            iterations=100000,
            dklen=32
        )
        
        return base64.b64encode(key).decode('ascii')
    
    def get_plugin_aes_key(self, license_data: Dict) -> bytes:
        """دریافت کلید AES پلاگین"""
        if 'plugin_aes_key' in license_data:
            return base64.b64decode(license_data['plugin_aes_key'])
        
        machine_id = license_data.get('machine_id', '')
        license_id = license_data.get('license_id', '')
        
        if not machine_id or not license_id:
            raise ValueError("❌ لایسنس نامعتبر!")
        
        key_material = f"{machine_id}:{license_id}".encode('utf-8')
        
        return hashlib.pbkdf2_hmac(
            'sha256',
            key_material,
            self.PLUGIN_APP_SALT,
            iterations=100000,
            dklen=32
        )
    
    def encrypt_plugin(
        self,
        manifest: Dict,
        code: str,
        license_data: Dict,
        sign: bool = True
    ) -> bytes:
        """رمزنگاری پلاگین"""
        if not self.is_seller:
            raise PermissionError("❌ فقط فروشنده!")
        
        if sign and self.private_key:
            manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
            data_to_sign = manifest_json + "\n---\n" + code
            
            signature = self.private_key.sign(
                data_to_sign.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            manifest = manifest.copy()
            manifest['signature'] = base64.b64encode(signature).decode('ascii')
        
        header = {
            'id': manifest.get('id', 'unknown'),
            'name': manifest.get('name', ''),
            'version': manifest.get('version', '1.0.0'),
            'author': manifest.get('author', 'ImanAI'),
            'type': manifest.get('type', 'internal'),
            'required_modules': manifest.get('required_modules', []),
            'required_license': manifest.get('required_license', ''),
            'description': manifest.get('description', ''),
            'icon': manifest.get('icon', '🔌'),
            'encrypted': True,
            'signed': sign and self.private_key is not None,
            'format_version': self.PLUGIN_FORMAT_VERSION,
        }
        
        header_json = json.dumps(header, ensure_ascii=False, sort_keys=True)
        header_bytes = header_json.encode('utf-8')
        
        payload = {
            'manifest': manifest,
            'code': code,
        }
        
        payload_json = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        payload_bytes = payload_json.encode('utf-8')
        
        aes_key = self.get_plugin_aes_key(license_data)
        
        aesgcm = AESGCM(aes_key)
        nonce = os.urandom(12)
        aad = header_bytes
        
        encrypted_payload = aesgcm.encrypt(nonce, payload_bytes, aad)
        
        result = bytearray()
        result += self.PLUGIN_MAGIC
        result += bytes([self.PLUGIN_FORMAT_VERSION])
        result += struct.pack('>I', len(header_bytes))
        result += header_bytes
        result += nonce
        result += encrypted_payload
        
        return bytes(result)
    
    def decrypt_plugin(self, plugin_data: bytes, license_data: Dict) -> Tuple[Dict, str]:
        """رمزگشایی پلاگین"""
        if len(plugin_data) < 9:
            raise ValueError("❌ فایل خیلی کوچک")
        
        if plugin_data[:4] != self.PLUGIN_MAGIC:
            raise ValueError("❌ فایل نامعتبر")
        
        version = plugin_data[4]
        if version != self.PLUGIN_FORMAT_VERSION:
            raise ValueError(f"❌ نسخه پشتیبانی نمی‌شه: v{version}")
        
        header_len = struct.unpack('>I', plugin_data[5:9])[0]
        
        if len(plugin_data) < 9 + header_len + 12 + 16:
            raise ValueError("❌ فایل ناقص")
        
        header_bytes = plugin_data[9:9+header_len]
        header = json.loads(header_bytes.decode('utf-8'))
        
        if not header.get('encrypted'):
            raise ValueError("❌ فایل رمزنگاری نشده")
        
        try:
            aes_key = self.get_plugin_aes_key(license_data)
        except ValueError:
            raise ValueError(
                "❌ لایسنس نامعتبر: نمی‌توان کلید رمزگشایی را ساخت."
            )
        
        offset = 9 + header_len
        nonce = plugin_data[offset:offset+12]
        encrypted_payload = plugin_data[offset+12:]
        
        aesgcm = AESGCM(aes_key)
        
        try:
            decrypted = aesgcm.decrypt(nonce, encrypted_payload, header_bytes)
        except:
            raise ValueError(
                "❌ رمزگشایی ناموفق!\n"
                "لایسنس شما برای این پلاگین معتبر نیست."
            )
        
        payload = json.loads(decrypted.decode('utf-8'))
        manifest = payload.get('manifest', header)
        code = payload.get('code', '')
        
        # بررسی امضا
        signature = manifest.get('signature', '')
        if signature and self.public_key:
            try:
                manifest_copy = manifest.copy()
                manifest_copy.pop('signature', None)
                manifest_json = json.dumps(
                    manifest_copy, ensure_ascii=False, sort_keys=True
                )
                data_to_verify = manifest_json + "\n---\n" + code
                
                sig_bytes = base64.b64decode(signature)
                
                self.public_key.verify(
                    sig_bytes,
                    data_to_verify.encode('utf-8'),
                    padding.PSS(
                        mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.MAX_LENGTH
                    ),
                    hashes.SHA256()
                )
            except InvalidSignature:
                raise ValueError("❌ امضای پلاگین نامعتبر است!")
        
        return manifest, code
    
    @classmethod
    def read_plugin_header(cls, plugin_data: bytes) -> Optional[Dict]:
        """خواندن Header پلاگین"""
        try:
            if plugin_data[:4] != cls.PLUGIN_MAGIC:
                return None
            
            header_len = struct.unpack('>I', plugin_data[5:9])[0]
            header_bytes = plugin_data[9:9+header_len]
            return json.loads(header_bytes.decode('utf-8'))
        except:
            return None
    
    @classmethod
    def is_encrypted_plugin(cls, plugin_data: bytes) -> bool:
        """بررسی رمزنگاری"""
        header = cls.read_plugin_header(plugin_data)
        return header and header.get('encrypted', False)
    
    # ============================================================
    # ========== اطلاعات ==========
    # ============================================================
    
    def get_public_key_pem(self) -> str:
        """کلید عمومی"""
        if not self.public_key:
            return ""
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    @staticmethod
    def get_keys_info() -> Dict:
        """اطلاعات کلیدها"""
        return {
            'keys_directory': str(KEYS_DIR),
            'public_key_exists': PUBLIC_KEY_PATH.exists(),
            'private_key_exists': PRIVATE_KEY_PATH.exists(),
            'trial_cert_exists': TRIAL_CERT_PATH.exists(),
            'is_seller_build': LicenseCore.IS_SELLER_BUILD,
        }


# ============================================================
# ========== کلاس‌های کمکی ==========
# ============================================================

class PluginSigner:
    """امضا و بررسی امضای پلاگین‌ها"""
    
    def __init__(self):
        self.core = get_license_core()
    
    def sign_plugin_data(self, data: str) -> str:
        if not self.core.is_seller or not self.core.private_key:
            raise PermissionError("❌ فقط فروشنده!")
        
        signature = self.core.private_key.sign(
            data.encode('utf-8'),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        return base64.b64encode(signature).decode('ascii')
    
    def verify_plugin_signature(
        self,
        data: str,
        signature: str,
        public_key_pem: str = None
    ) -> bool:
        try:
            if public_key_pem:
                public_key = serialization.load_pem_public_key(
                    public_key_pem.encode('utf-8'),
                    backend=default_backend()
                )
            else:
                public_key = self.core.public_key
            
            if public_key is None:
                return False
            
            sig_bytes = base64.b64decode(signature)
            
            public_key.verify(
                sig_bytes,
                data.encode('utf-8'),
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            return True
        except:
            return False


class LicenseManager:
    """مدیریت لایسنس"""
    
    def __init__(self):
        self.core = get_license_core()
    
    def verify_license(self, license_key: str) -> Dict:
        return self.core.verify_license(license_key)
    
    def generate_license(self, *args, **kwargs) -> Dict:
        return self.core.generate_license(*args, **kwargs)
    
    def create_trial_license(self) -> Dict:
        return self.core.create_trial_license()
    
    def save_license(self, license_key: str, file_path: str = None) -> bool:
        return self.core.save_license(license_key, file_path)
    
    def load_license(self, file_path: str = None) -> Optional[str]:
        return self.core.load_license(file_path)


# ============================================================
# ========== Singleton ==========
# ============================================================

_license_core_instance: Optional[LicenseCore] = None


def get_license_core(is_seller: Optional[bool] = None) -> LicenseCore:
    global _license_core_instance
    if _license_core_instance is None:
        _license_core_instance = LicenseCore(is_seller=is_seller)
    return _license_core_instance


def get_system_hwid() -> str:
    return LicenseCore.get_machine_id()


def get_machine_id() -> str:
    return LicenseCore.get_machine_id()


def get_public_key() -> str:
    return get_license_core().get_public_key_pem()


# Alias
LicenseGenerator = LicenseCore
