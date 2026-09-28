# license_core.py
# ============================================================
# سیستم لایسنس ImanAccount - v5.1 (Self-Check Ready)
# ============================================================
# 
# ✅ Embedded Public Key
# ✅ فقط 1 فایل
# ✅ Self-Check برای فروشنده
# ✅ امنیت RSA 4096
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


# ============================================================
# ========== Import Registry Guard ==========
# ============================================================

try:
    from registry_guard import get_machine_id as _get_machine_id_from_registry
    REGISTRY_AVAILABLE = True
except ImportError:
    REGISTRY_AVAILABLE = False


# ============================================================
# ========== Embedded Public Key ==========
# ============================================================
# 
# ⚠️ این کلید عمومی برای همه مشتری‌ها یکسانه
# ⚠️ توسط فروشنده از Private Key استخراج شده
# ⚠️ هیچ فایل جدا لازم نیست
# 
# ============================================================

EMBEDDED_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIICIjANBgkqhkiG9w0BAQEFAAOCAg8AMIICCgKCAgEAm75rbyg5jusURqCcO3M1
OxbG4WQh0ZFDNxf7OR2TvPB4sTmY9Bq+lACUnqrexpuwluVxp+RxeweVAw2Yeg9b
zX4HPNLg9DO2mRKENLF9nwa0d1GuUZirsoQQ4qnKdPZGx3rPEBOPl25jW9CZTBX2
4Mh8d4dtCwWImyHuhgHj3VU4+3fSCvTyL2JyPeoph/fZ6Ec2tqn48ynwPAORn3mr
Zpf4o63/DapaiHuSlqzx0GBRz2srEpXn7Lsn4Q6/OaqX5CXPy0Tp9SjCGIUou2IS
a0S9h7LRObLK0bwlUh2Tw2p4ldVO6mofsJmt11uDDAGhrueVeDQeBceav5Q/w3rS
YDSz6Qzqtp5Ttz48XGtvpAo68hmHjBGGzm/ckXrBK8SdpUswF0b9P77RcrM5WLLS
/qoNUTtT33CLsBK4wGOjU4IBO3BV95QQFHKucMgJmc4nwgGthV+l+ModO4q2ROPa
aW0JXYr+XQDbXo/P1BvlMvzFesc792mwg1ALoTX6+Z9oX5FSHzpDxLqWAlXfxv/9
7zK81MJ8v1RQd1lSLt46zTo94I/iHrRo4iB01SNCUEmhe+tIu1lXxS6VixV7oE39
SefGNAvPLEYAaSJhGhqkINXlIdZYRiIy3KzxrPylcxsVyayGFXEqAlCGn1DQiEX8
ojRdmrTsuYPxdudMl07A2WUCAwEAAQ==
-----END PUBLIC KEY-----"""


# ============================================================
# ========== مسیرها ==========
# ============================================================

def _get_secure_dir() -> Path:
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / "ImanAccount" / ".keys" if appdata else Path.home() / ".imanaccount" / ".keys"
    else:
        base = Path.home() / ".config" / "imanaccount" / ".keys"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_user_data_dir() -> Path:
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA')
        base = Path(appdata) / "ImanAccount" if appdata else Path.home() / ".imanaccount"
    else:
        base = Path.home() / ".config" / "imanaccount"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _secure_file(file_path: Path):
    try:
        if os.name == 'nt':
            username = os.environ.get('USERNAME', '')
            if username:
                subprocess.run(
                    ['icacls', str(file_path), '/inheritance:r', '/grant:r', f'{username}:F'],
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

PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"
LICENSE_FILE = USER_DATA_DIR / "license.key"
TRIAL_FILE = USER_DATA_DIR / "trial.license"

TRIAL_SIGNATURE_SALT = b"ImanAI_Trial_Cert_v5_2025"
TRIAL_CERT_MAGIC = b"ITRL"
TRIAL_CERT_VERSION = 1


# ============================================================
# ========== کلاس LicenseCore ==========
# ============================================================

class LicenseCore:
    """سیستم لایسنس ImanAccount v5.1"""
    
    IS_SELLER_BUILD = False
    LICENSE_FORMAT_VERSION = "5.1.0"
    
    PLUGIN_MAGIC = b"IPLG"
    PLUGIN_FORMAT_VERSION = 3
    PLUGIN_APP_SALT = b"ImanAI_Plugin_Encryption_Salt_v5_2025"
    
    def __init__(self, is_seller: Optional[bool] = None):
        if is_seller is None:
            is_seller = self.IS_SELLER_BUILD
        
        self.is_seller = is_seller
        self.public_key = None
        self.private_key = None
        self._aes_key = None
        
        self._load_embedded_public_key()
        
        if self.is_seller:
            self._load_seller_private_key()
        
        self._init_aes_key()
    
    # ============================================================
    # ========== Public Key (Embedded) ==========
    # ============================================================
    
    def _load_embedded_public_key(self):
        try:
            self.public_key = serialization.load_pem_public_key(
                EMBEDDED_PUBLIC_KEY.encode('utf-8'),
                backend=default_backend()
            )
        except Exception as e:
            print(f"❌ خطا در بارگذاری Embedded Public Key: {e}")
            self.public_key = None
    
    # ============================================================
    # ========== Private Key (Seller) ==========
    # ============================================================
    
    def _load_seller_private_key(self):
        if not PRIVATE_KEY_PATH.exists():
            self.private_key = None
            return
        
        try:
            with open(PRIVATE_KEY_PATH, 'rb') as f:
                private_pem = f.read()
            
            password = self._get_key_password()
            
            self.private_key = serialization.load_pem_private_key(
                private_pem,
                password=password,
                backend=default_backend()
            )
        except Exception:
            self.private_key = None
    
    def _get_key_password(self) -> Optional[bytes]:
        env_pass = os.environ.get('IMANACCOUNT_KEY_PASSWORD')
        if env_pass:
            return env_pass.encode()
        
        password_file = KEYS_DIR / "password.txt"
        if password_file.exists():
            try:
                with open(password_file, 'rb') as f:
                    return f.read().strip()
            except Exception:
                pass
        
        if sys.stdin.isatty():
            try:
                import getpass
                password = getpass.getpass("🔐 رمز Private Key: ")
                return password.encode() if password else None
            except Exception:
                return None
        
        return None
    
    def _init_aes_key(self):
        aes_path = KEYS_DIR / "aes.key"
        
        if aes_path.exists():
            try:
                with open(aes_path, 'rb') as f:
                    key = f.read()
                if len(key) == 32:
                    self._aes_key = key
                    return
            except Exception:
                pass
        
        self._aes_key = os.urandom(32)
        
        with open(aes_path, 'wb') as f:
            f.write(self._aes_key)
        _secure_file(aes_path)
    
    # ============================================================
    # ========== Init Seller ==========
    # ============================================================
    
    @classmethod
    def init_seller_keys(cls, password: str = None) -> bool:
        """ساخت Private Key برای فروشنده"""
        try:
            if password is None:
                password = os.environ.get('IMANACCOUNT_KEY_PASSWORD')
            
            if not password:
                print("❌ رمز Private Key الزامی است!")
                return False
            
            password_bytes = password.encode()
            
            if PRIVATE_KEY_PATH.exists():
                print(f"✅ Private Key قبلاً ساخته شده")
                return True
            
            print("🔑 ساخت RSA 4096-bit Private Key...")
            
            private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
                backend=default_backend()
            )
            
            private_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(password_bytes)
            )
            
            with open(PRIVATE_KEY_PATH, 'wb') as f:
                f.write(private_pem)
            _secure_file(PRIVATE_KEY_PATH)
            
            public_pem = private_key.public_key().public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo
            ).decode('utf-8')
            
            print()
            print("=" * 70)
            print("📋 Public Key (این رو تو EMBEDDED_PUBLIC_KEY پیست کن):")
            print("=" * 70)
            print(public_pem)
            print("=" * 70)
            print()
            print(f"✅ Private Key ذخیره شد: {PRIVATE_KEY_PATH}")
            
            return True
        
        except Exception as e:
            print(f"❌ خطا: {e}")
            return False
    
    # ============================================================
    # ========== Self-Check (جدید!) ==========
    # ============================================================
    
    def self_check(self) -> Dict:
        """
        چک کردن سیستم لایسنس
        
        Returns:
            {
                'ok': bool,
                'checks': {
                    'private_key': bool,
                    'public_key': bool,
                    'match': bool,
                    'aes_key': bool
                },
                'message': str
            }
        """
        result = {
            'ok': False,
            'checks': {
                'private_key': self.private_key is not None,
                'public_key': self.public_key is not None,
                'match': False,
                'aes_key': self._aes_key is not None,
            },
            'message': ''
        }
        
        # ===== چک Private Key =====
        if not self.private_key:
            result['message'] = "❌ Private Key یافت نشد"
            return result
        
        # ===== چک Public Key =====
        if not self.public_key:
            result['message'] = "❌ Public Key یافت نشد"
            return result
        
        # ===== چک Match =====
        try:
            # یه تست ساده: امضا کن و verify کن
            test_data = b"test_data_for_self_check"
            
            signature = self.private_key.sign(
                test_data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            self.public_key.verify(
                signature,
                test_data,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.MAX_LENGTH
                ),
                hashes.SHA256()
            )
            
            result['checks']['match'] = True
        
        except Exception as e:
            result['message'] = f"❌ Private و Public Key match نمی‌کنن: {e}"
            return result
        
        # ===== چک AES =====
        if not self._aes_key:
            result['message'] = "❌ AES Key یافت نشد"
            return result
        
        # ===== همه چیز OK =====
        result['ok'] = True
        result['message'] = "✅ همه چیز درسته"
        return result
    
    # ============================================================
    # ========== HWID ==========
    # ============================================================
    
    @staticmethod
    def get_machine_id() -> str:
        if REGISTRY_AVAILABLE:
            try:
                return _get_machine_id_from_registry()
            except Exception:
                pass
        
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
        except Exception:
            return "IACC-FALLBACK-000000000000000000000000"
    
    @staticmethod
    def get_system_hwid() -> str:
        return LicenseCore.get_machine_id()
    
    # ============================================================
    # ========== Generate License ==========
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
            raise ValueError("❌ Private Key در دسترس نیست!")
        
        if modules is None:
            modules = ['accounting', 'inventory', 'payroll', 'parties',
                      'invoice', 'purchase']
        
        if limits is None:
            limits = {}
        
        if machine_id is None:
            machine_id = self.get_machine_id()
        
        license_id = hashlib.sha256(
            f"{customer_name}|{machine_id}|{datetime.now().isoformat()}|{os.urandom(16).hex()}".encode()
        ).hexdigest()[:16].upper()
        
        now = datetime.now()
        expire_date = now + timedelta(days=expire_days)
        
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
    # ========== Verify License ==========
    # ============================================================
    
    def verify_license(self, license_key: str) -> Dict:
        """بررسی لایسنس"""
        try:
            if license_key == "TRIAL":
                trial_data = self._load_trial_license()
                if trial_data:
                    return self._verify_trial(trial_data)
                return {
                    'valid': False,
                    'error': 'no_trial',
                    'message': '❌ لایسنس آزمایشی فعال نشده است!'
                }
            
            if self.public_key is None:
                return {
                    'valid': False,
                    'error': 'no_public_key',
                    'message': '❌ Public Key در دسترس نیست!'
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
            
            current_machine_id = self.get_machine_id()
            if payload.get('machine_id') != current_machine_id:
                return {
                    'valid': False,
                    'error': 'machine_mismatch',
                    'message': f'❌ این لایسنس برای این سیستم صادر نشده است!\nHWID: {current_machine_id}'
                }
            
            try:
                expire_date = datetime.fromisoformat(payload['expire_date'])
            except Exception:
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
                    'message': f'❌ لایسنس منقضی شده است!\n({days_expired} روز پیش)'
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
    # ========== Trial ==========
    # ============================================================
    
    def create_trial_license(self) -> Dict:
        if self._is_trial_used():
            return {
                'valid': False,
                'error': 'trial_used',
                'message': '❌ نسخه آزمایشی قبلاً استفاده شده است!'
            }
        
        if self.is_seller:
            return self._create_trial_as_seller()
        else:
            return self._create_trial_as_customer()
    
    def _create_trial_as_seller(self) -> Dict:
        try:
            license_data = self.generate_license(
                customer_name="نسخه آزمایشی",
                expire_days=30,
                is_trial=True
            )
            
            trial_data = license_data['data'].copy()
            trial_data['is_trial'] = True
            trial_data['trial_signature'] = 'SELLER_SIGNED'
            
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
        cert_data = self._load_trial_certificate()
        
        if not cert_data:
            return {
                'valid': False,
                'error': 'no_trial_certificate',
                'message': '❌ نسخه آزمایشی در این برنامه فعال نیست!'
            }
        
        try:
            trial_payload = self._create_trial_from_certificate(cert_data)
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
                'message': f'❌ خطا: {str(e)}'
            }
    
    def _load_trial_certificate(self) -> Optional[Dict]:
        trial_cert_path = Path(__file__).parent / "trial_certificate.bin"
        
        if not trial_cert_path.exists():
            return None
        
        try:
            with open(trial_cert_path, 'rb') as f:
                cert_data = f.read()
            return self._parse_trial_certificate(cert_data)
        except Exception:
            return None
    
    def _parse_trial_certificate(self, cert_data: bytes) -> Optional[Dict]:
        try:
            if len(cert_data) < 9:
                return None
            if cert_data[:4] != TRIAL_CERT_MAGIC:
                return None
            if cert_data[4] != TRIAL_CERT_VERSION:
                return None
            
            cert_len = struct.unpack('>I', cert_data[5:9])[0]
            cert_json = cert_data[9:9+cert_len]
            signature = cert_data[9+cert_len:]
            
            cert = json.loads(cert_json.decode('utf-8'))
            
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
                return None
            
            return cert
        except Exception:
            return None
    
    def _create_trial_from_certificate(self, cert: Dict) -> Dict:
        current_hwid = self.get_machine_id()
        now = datetime.now()
        expire_date = now + timedelta(days=cert.get('trial_days', 30))
        
        trial_id = hashlib.sha256(
            f"TRIAL:{current_hwid}:{now.isoformat()}".encode()
        ).hexdigest()[:16].upper()
        
        plugin_aes_key = self._generate_plugin_aes_key(current_hwid, f"TRIAL_{trial_id}")
        
        trial_payload = {
            'license_id': f"TRIAL_{trial_id}",
            'customer': 'نسخه آزمایشی',
            'company': '',
            'machine_id': current_hwid,
            'modules': cert.get('modules', []),
            'limits': cert.get('limits', {}),
            'plugin_aes_key': plugin_aes_key,
            'created_at': now.isoformat(),
            'expire_date': expire_date.isoformat(),
            'version': self.LICENSE_FORMAT_VERSION,
            'is_trial': True,
            'trial_cert_id': cert.get('cert_id', ''),
        }
        
        trial_signature = hashlib.sha256(
            f"TRIAL:{current_hwid}:{trial_id}:{expire_date.isoformat()}:{cert.get('cert_id', '')}".encode()
            + TRIAL_SIGNATURE_SALT
        ).hexdigest()
        
        trial_payload['trial_signature'] = trial_signature
        
        return trial_payload
    
    def _verify_trial(self, trial: Dict) -> Dict:
        try:
            current_hwid = self.get_machine_id()
            if trial.get('machine_id') != current_hwid:
                return {
                    'valid': False,
                    'error': 'trial_machine_mismatch',
                    'message': '❌ نسخه آزمایشی برای این سیستم صادر نشده است!'
                }
            
            trial_signature = trial.get('trial_signature', '')
            
            if trial_signature != 'SELLER_SIGNED':
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
            
            try:
                expire_date = datetime.fromisoformat(trial['expire_date'])
            except Exception:
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
                    'message': f'❌ نسخه آزمایشی منقضی شده ({days_expired} روز پیش)'
                }
            
            days_left = (expire_date - now).days
            
            return {
                'valid': True,
                'data': trial,
                'days_left': days_left,
                'is_trial': True,
                'message': f'✅ نسخه آزمایشی معتبر | {days_left} روز',
                'is_expiring_soon': days_left <= 7
            }
        
        except Exception as e:
            return {
                'valid': False,
                'error': 'trial_error',
                'message': f'❌ خطا: {str(e)}'
            }
    
    # ============================================================
    # ========== Save/Load Trial ==========
    # ============================================================
    
    def _save_trial_license(self, payload: Dict):
        with open(TRIAL_FILE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        _secure_file(TRIAL_FILE)
    
    def _load_trial_license(self) -> Optional[Dict]:
        if not TRIAL_FILE.exists():
            return None
        try:
            with open(TRIAL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None
    
    @staticmethod
    def _is_trial_used() -> bool:
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
            except Exception:
                pass
        else:
            marker = Path.home() / ".imanaccount" / ".trial_used"
            return marker.exists()
        
        return TRIAL_FILE.exists()
    
    @staticmethod
    def _mark_trial_used():
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
            except Exception:
                pass
        else:
            marker = Path.home() / ".imanaccount" / ".trial_used"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(datetime.now().isoformat())
    
    # ============================================================
    # ========== Trial Certificate Builder ==========
    # ============================================================
    
    def build_trial_certificate(
        self,
        trial_days: int = 30,
        modules: Optional[List[str]] = None,
        limits: Optional[Dict[str, int]] = None
    ) -> bytes:
        if not self.is_seller:
            raise PermissionError("❌ فقط فروشنده!")
        
        if self.private_key is None:
            raise ValueError("❌ Private Key در دسترس نیست!")
        
        if modules is None:
            modules = ['accounting', 'inventory', 'payroll', 'parties',
                      'invoice', 'purchase', 'ai', 'reports']
        
        if limits is None:
            limits = {
                'accounting': 50, 'inventory': 20, 'payroll': 5,
                'parties': 10, 'invoice': 10, 'purchase': 10
            }
        
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
        
        cert_json = json.dumps(cert, ensure_ascii=False, sort_keys=True).encode('utf-8')
        
        signature = self.private_key.sign(
            cert_json,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        
        result = bytearray()
        result += TRIAL_CERT_MAGIC
        result += bytes([TRIAL_CERT_VERSION])
        result += struct.pack('>I', len(cert_json))
        result += cert_json
        result += signature
        
        return bytes(result)
    
    # ============================================================
    # ========== AES ==========
    # ============================================================
    
    def _encrypt_data(self, data: dict) -> str:
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
        if self._aes_key is None:
            raise ValueError("کلید AES در دسترس نیست!")
        
        clean = encrypted_key.strip().replace('-', '').replace(' ', '')
        padding_len = (4 - len(clean) % 4) % 4
        clean += '=' * padding_len
        
        combined = base64.b64decode(clean)
        
        if len(combined) < 28:
            raise ValueError("لایسنس خیلی کوتاه")
        
        nonce = combined[:12]
        ciphertext = combined[12:]
        
        aesgcm = AESGCM(self._aes_key)
        data_bytes = aesgcm.decrypt(nonce, ciphertext, None)
        
        return json.loads(data_bytes.decode('utf-8'))
    
    # ============================================================
    # ========== Helpers ==========
    # ============================================================
    
    @staticmethod
    def _format_license_key(key: str) -> str:
        clean = key.replace('-', '').replace(' ', '').replace('_', '')
        groups = [clean[i:i+4] for i in range(0, len(clean), 4)]
        return '-'.join(groups)
    
    def save_license(self, license_key: str, file_path: Optional[str] = None) -> bool:
        try:
            target = Path(file_path) if file_path else LICENSE_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            
            with open(target, 'w', encoding='utf-8') as f:
                f.write(license_key)
            
            _secure_file(target)
            return True
        except Exception:
            return False
    
    def load_license(self, file_path: Optional[str] = None) -> Optional[str]:
        try:
            target = Path(file_path) if file_path else LICENSE_FILE
            if target.exists():
                with open(target, 'r', encoding='utf-8') as f:
                    return f.read().strip()
            return None
        except Exception:
            return None
    
    def _generate_plugin_aes_key(self, machine_id: str, license_id: str) -> str:
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
    
    # ============================================================
    # ========== Info ==========
    # ============================================================
    
    def get_public_key_pem(self) -> str:
        return EMBEDDED_PUBLIC_KEY
    
    def get_public_key_short(self) -> str:
        """Public Key کوتاه برای نمایش"""
        # خط دوم PEM
        lines = EMBEDDED_PUBLIC_KEY.strip().split('\n')
        if len(lines) >= 2:
            return lines[1][:40] + "..."
        return "..."
    
    @staticmethod
    def get_keys_info() -> Dict:
        return {
            'keys_directory': str(KEYS_DIR),
            'private_key_exists': PRIVATE_KEY_PATH.exists(),
            'public_key_embedded': True,
            'is_seller_build': LicenseCore.IS_SELLER_BUILD,
        }


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
    return EMBEDDED_PUBLIC_KEY


LicenseGenerator = LicenseCore


# ============================================================
# ========== CLI ==========
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ImanAccount License Core v5.1")
    parser.add_argument("--init-seller", action="store_true",
                       help="ساخت Private Key فروشنده")
    parser.add_argument("--password", type=str, default=None)
    parser.add_argument("--self-check", action="store_true",
                       help="چک کردن سیستم لایسنس")
    
    args = parser.parse_args()
    
    if args.init_seller:
        print("=" * 70)
        print("🔑 ساخت Private Key فروشنده")
        print("=" * 70)
        success = LicenseCore.init_seller_keys(password=args.password)
        if success:
            print()
            print("✅ تمام!")
    
    elif args.self_check:
        print("=" * 70)
        print("🔍 Self-Check")
        print("=" * 70)
        
        core = LicenseCore(is_seller=True)
        result = core.self_check()
        
        print()
        print(f"Private Key: {'✅' if result['checks']['private_key'] else '❌'}")
        print(f"Public Key:  {'✅' if result['checks']['public_key'] else '❌'}")
        print(f"Match:       {'✅' if result['checks']['match'] else '❌'}")
        print(f"AES Key:     {'✅' if result['checks']['aes_key'] else '❌'}")
        print()
        print(result['message'])
    
    else:
        parser.print_help()
