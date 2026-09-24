# admin_panel.py
# -*- coding: utf-8 -*-
# ============================================================
# پنل مدیریت فروشنده ImanAccount - نسخه v5.0 (PyQt5)
# ============================================================
# 
# ✅ ویندوز — PyQt5
# ✅ سازگار با PyInstaller --windowed
# ✅ مدیریت مشتریان نرم‌افزار
# ✅ مدیریت مشتریان خدمات حسابداری
# ✅ حالت ترکیبی (نرم‌افزار + خدمات)
# ✅ قرارداد خدمات ماهانه
# ✅ فاکتور خدمات
# ✅ گزارش درآمد تفکیک‌شده
# ✅ ویرایش، خروجی Excel، پشتیبان‌گیری
# ✅ نمودار درآمد ۶ ماه
# ============================================================

import sys
import os
import json
import csv
import struct
import base64
import hashlib
import sqlite3
import shutil
import traceback
from pathlib import Path
from datetime import datetime, timedelta
from contextlib import contextmanager
from PyQt5.QtWidgets import QApplication, QMessageBox

# ============================================================
# ========== توابع امن ==========
# ============================================================

def safe_print(*args, **kwargs):
    try:
        if sys.stdout is not None:
            print(*args, **kwargs)
    except (RuntimeError, AttributeError, OSError, ValueError):
        pass


def safe_pause(message: str = "\nEnter..."):
    try:
        if sys.stdin is not None and sys.stdin.isatty():
            input(message)
        else:
            safe_print(message)
    except (RuntimeError, EOFError, AttributeError, OSError):
        safe_print(message)


# ============================================================
# ========== تنظیمات ==========
# ============================================================

def _get_admin_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()


ADMIN_DIR = _get_admin_dir()
sys.path.insert(0, str(ADMIN_DIR))

SELLER_PASSWORD = "MySellerKey@2025#ImanAI"
os.environ.setdefault('IMANACCOUNT_KEY_PASSWORD', SELLER_PASSWORD)


def print_header(title):
    safe_print("\n" + "=" * 60)
    safe_print(f"  {title}")
    safe_print("=" * 60)


def check_and_setup():
    print_header("🔧 راه‌اندازی پنل ادمین")
    safe_print(f"📁 پوشه پنل: {ADMIN_DIR}\n")
    
    if not (ADMIN_DIR / "license_core.py").exists():
        print_header("❌ خطا")
        safe_print("فایل license_core.py یافت نشد!")
        return None, False
    safe_print("✅ license_core.py")
    
    if not (ADMIN_DIR / "registry_guard.py").exists():
        print_header("❌ خطا")
        safe_print("فایل registry_guard.py یافت نشد!")
        return None, False
    safe_print("✅ registry_guard.py")
    
    try:
        from license_core import LicenseCore, get_license_core
        safe_print("✅ import license_core")
    except ImportError as e:
        print_header("❌ خطا در import")
        safe_print(f"خطا: {e}")
        safe_print("💡 راه‌حل: pip install cryptography")
        return None, False
    
    try:
        safe_print("\n🔑 در حال راه‌اندازی فروشنده...")
        core = LicenseCore(is_seller=True)
        safe_print(f"   ✅ کلید خصوصی: {'موجود' if core.private_key else '❌'}")
        safe_print(f"   ✅ کلید عمومی: {'موجود' if core.public_key else '❌'}")
    except Exception as e:
        print_header("❌ خطا")
        safe_print(f"خطا: {e}")
        safe_print(f"\n💡 set IMANACCOUNT_KEY_PASSWORD={SELLER_PASSWORD}")
        return None, False
    
    public_key_file = ADMIN_DIR / "public_key.pem"
    if not public_key_file.exists():
        safe_print("\n🔑 ساخت public_key.pem...")
        try:
            public_pem = core.get_public_key_pem()
            if not public_pem:
                return None, False
            with open(public_key_file, 'w', encoding='utf-8') as f:
                f.write(public_pem)
            safe_print(f"✅ public_key.pem")
        except Exception as e:
            safe_print(f"❌ {e}")
            return None, False
    else:
        safe_print(f"✅ public_key.pem")
    
    safe_print("\n" + "=" * 60)
    safe_print("  ✅ راه‌اندازی کامل شد!")
    safe_print("=" * 60 + "\n")
    return core, True


# ============================================================
# ========== Imports PyQt5 ============
# ============================================================

try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QLabel, QPushButton, QLineEdit, QTextEdit, QComboBox, QSpinBox,
        QCheckBox, QGroupBox, QFormLayout, QGridLayout, QTabWidget,
        QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
        QDialog, QDialogButtonBox, QFrame, QListWidget, QListWidgetItem,
        QHeaderView
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QPainter, QPen, QBrush, QFont
except ImportError:
    safe_print("\n❌ PyQt5 نصب نیست!")
    sys.exit(1)


# ============================================================
# ========== دیتابیس (v3 - دو نوع مشتری) ==========
# ============================================================

class CustomersDB:
    """دیتابیس مشتریان — با پشتیبانی از خدمات حسابداری"""
    
    def __init__(self):
        self.db_path = str(ADMIN_DIR / "customers.db")
        self.backup_dir = ADMIN_DIR / "backups"
        self._init_db()
    
    @contextmanager
    def get_db(self):
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self):
        with self.get_db() as conn:
            c = conn.cursor()
            
            # جدول اصلی مشتریان
            c.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    company TEXT,
                    phone TEXT,
                    email TEXT,
                    hwid TEXT,
                    license_key TEXT,
                    license_type TEXT DEFAULT 'full',
                    modules TEXT,
                    duration_days INTEGER DEFAULT 365,
                    price INTEGER DEFAULT 0,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    
                    -- ✅ فیلدهای جدید: خدمات
                    customer_type TEXT DEFAULT 'software',
                    has_service BOOLEAN DEFAULT 0,
                    service_monthly_fee INTEGER DEFAULT 0,
                    service_start_date TEXT,
                    service_end_date TEXT,
                    service_status TEXT DEFAULT 'inactive'
                )
            ''')
            
            # جدول قراردادهای خدمات
            c.execute('''
                CREATE TABLE IF NOT EXISTS service_contracts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    monthly_fee INTEGER DEFAULT 0,
                    services TEXT,
                    status TEXT DEFAULT 'active',
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )
            ''')
            
            # جدول فاکتورهای خدمات ماهانه
            c.execute('''
                CREATE TABLE IF NOT EXISTS service_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER NOT NULL,
                    contract_id INTEGER,
                    year INTEGER,
                    month INTEGER,
                    amount INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    paid_at TIMESTAMP,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(customer_id) REFERENCES customers(id),
                    FOREIGN KEY(contract_id) REFERENCES service_contracts(id)
                )
            ''')
            
            # جدول تراکنش‌ها
            c.execute('''
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id INTEGER,
                    amount INTEGER DEFAULT 0,
                    type TEXT DEFAULT 'license',
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(customer_id) REFERENCES customers(id)
                )
            ''')
            
            # ایندکس‌ها
            c.execute('CREATE INDEX IF NOT EXISTS idx_hwid ON customers(hwid)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_name ON customers(name)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_customer_type ON customers(customer_type)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_has_service ON customers(has_service)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_trans_date ON transactions(created_at)')
            c.execute('CREATE INDEX IF NOT EXISTS idx_invoice_customer ON service_invoices(customer_id)')
            conn.commit()
    
    # ============================================================
    # ========== CRUD ==========
    # ============================================================
    
    def add_customer(self, data):
        with self.get_db() as conn:
            c = conn.cursor()
            expires = datetime.now() + timedelta(days=data.get('duration_days', 365))
            c.execute('''
                INSERT INTO customers 
                (name, company, phone, email, hwid, license_key, license_type,
                 modules, duration_days, price, notes, expires_at,
                 customer_type, has_service, service_monthly_fee,
                 service_start_date, service_end_date, service_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get('name', ''),
                data.get('company', ''),
                data.get('phone', ''),
                data.get('email', ''),
                data.get('hwid', ''),
                data.get('license_key', ''),
                data.get('license_type', 'full'),
                data.get('modules', '[]'),
                data.get('duration_days', 365),
                data.get('price', 0),
                data.get('notes', ''),
                expires.isoformat(),
                data.get('customer_type', 'software'),
                1 if data.get('has_service') else 0,
                data.get('service_monthly_fee', 0),
                data.get('service_start_date', ''),
                data.get('service_end_date', ''),
                data.get('service_status', 'inactive'),
            ))
            cid = c.lastrowid
            
            price = data.get('price', 0)
            if price > 0:
                c.execute('''
                    INSERT INTO transactions (customer_id, amount, type, description)
                    VALUES (?, ?, 'license', ?)
                ''', (cid, price, f'خرید لایسنس'))
            
            return cid
    
    def update_customer(self, cid, data):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE customers 
                SET name = ?, company = ?, phone = ?, email = ?,
                    hwid = ?, notes = ?,
                    has_service = ?, service_monthly_fee = ?,
                    service_start_date = ?, service_end_date = ?,
                    service_status = ?
                WHERE id = ?
            ''', (
                data.get('name', ''),
                data.get('company', ''),
                data.get('phone', ''),
                data.get('email', ''),
                data.get('hwid', ''),
                data.get('notes', ''),
                1 if data.get('has_service') else 0,
                data.get('service_monthly_fee', 0),
                data.get('service_start_date', ''),
                data.get('service_end_date', ''),
                data.get('service_status', 'inactive'),
                cid
            ))
            return c.rowcount > 0
    
    def get_all_customers(self):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM customers WHERE is_active = 1 ORDER BY created_at DESC')
            return [dict(row) for row in c.fetchall()]
    
    def get_customer(self, cid):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('SELECT * FROM customers WHERE id = ?', [cid])
            row = c.fetchone()
            return dict(row) if row else None
    
    def delete_customer(self, cid):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('UPDATE customers SET is_active = 0 WHERE id = ?', [cid])
            return c.rowcount > 0
    
    def update_license(self, cid, license_key, expires_at, days, price):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE customers 
                SET license_key = ?, expires_at = ?, duration_days = ?, price = price + ?
                WHERE id = ?
            ''', (license_key, expires_at, days, price, cid))
            
            if price > 0:
                c.execute('''
                    INSERT INTO transactions (customer_id, amount, type, description)
                    VALUES (?, ?, 'renewal', ?)
                ''', (cid, price, f'تمدید {days} روزه'))
    
    # ============================================================
    # ========== خدمات ==========
    # ============================================================
    
    def create_contract(self, customer_id, start_date, end_date,
                        monthly_fee, services, notes=''):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO service_contracts
                (customer_id, start_date, end_date, monthly_fee, services, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (customer_id, start_date, end_date, monthly_fee,
                  json.dumps(services), notes))
            contract_id = c.lastrowid
            
            c.execute('''
                UPDATE customers 
                SET has_service = 1, service_monthly_fee = ?,
                    service_start_date = ?, service_end_date = ?,
                    service_status = 'active'
                WHERE id = ?
            ''', (monthly_fee, start_date, end_date, customer_id))
            
            return contract_id
    
    def get_contracts(self, customer_id=None):
        with self.get_db() as conn:
            c = conn.cursor()
            if customer_id:
                c.execute('''
                    SELECT sc.*, cu.name as customer_name
                    FROM service_contracts sc
                    JOIN customers cu ON sc.customer_id = cu.id
                    WHERE sc.customer_id = ?
                    ORDER BY sc.created_at DESC
                ''', [customer_id])
            else:
                c.execute('''
                    SELECT sc.*, cu.name as customer_name
                    FROM service_contracts sc
                    JOIN customers cu ON sc.customer_id = cu.id
                    WHERE sc.status = 'active'
                    ORDER BY sc.created_at DESC
                ''')
            return [dict(row) for row in c.fetchall()]
    
    def generate_monthly_invoice(self, customer_id, contract_id,
                                   year, month, amount):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('''
                INSERT INTO service_invoices
                (customer_id, contract_id, year, month, amount)
                VALUES (?, ?, ?, ?, ?)
            ''', (customer_id, contract_id, year, month, amount))
            return c.lastrowid
    
    def mark_invoice_paid(self, invoice_id):
        with self.get_db() as conn:
            c = conn.cursor()
            c.execute('''
                UPDATE service_invoices
                SET status = 'paid', paid_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', [invoice_id])
            
            c.execute('SELECT customer_id, amount FROM service_invoices WHERE id = ?',
                     [invoice_id])
            row = c.fetchone()
            if row:
                c.execute('''
                    INSERT INTO transactions (customer_id, amount, type, description)
                    VALUES (?, ?, 'service', 'پرداخت فاکتور خدمات')
                ''', (row['customer_id'], row['amount']))
            
            return True
    
    def get_invoices(self, customer_id=None, status=None):
        with self.get_db() as conn:
            c = conn.cursor()
            sql = '''
                SELECT si.*, cu.name as customer_name
                FROM service_invoices si
                JOIN customers cu ON si.customer_id = cu.id
                WHERE 1=1
            '''
            params = []
            
            if customer_id:
                sql += ' AND si.customer_id = ?'
                params.append(customer_id)
            
            if status:
                sql += ' AND si.status = ?'
                params.append(status)
            
            sql += ' ORDER BY si.year DESC, si.month DESC, si.created_at DESC'
            
            c.execute(sql, params)
            return [dict(row) for row in c.fetchall()]
    
    # ============================================================
    # ========== آمار ==========
    # ============================================================
    
    def get_stats(self):
        with self.get_db() as conn:
            c = conn.cursor()
            
            # مشتریان نرم‌افزار
            c.execute('''SELECT COUNT(*) FROM customers WHERE is_active = 1 
                        AND customer_type IN ('software', 'both')''')
            software_total = c.fetchone()[0]
            
            c.execute('''SELECT COUNT(*) FROM customers WHERE is_active = 1 
                        AND customer_type IN ('software', 'both')
                        AND julianday(expires_at) > julianday('now')''')
            software_active = c.fetchone()[0]
            
            # مشتریان خدمات
            c.execute('''SELECT COUNT(*) FROM customers WHERE is_active = 1 
                        AND has_service = 1''')
            service_total = c.fetchone()[0]
            
            c.execute('''SELECT COUNT(*) FROM customers WHERE is_active = 1 
                        AND has_service = 1 AND service_status = 'active' ''')
            service_active = c.fetchone()[0]
            
            # درآمد
            c.execute('SELECT COALESCE(SUM(price), 0) FROM customers WHERE is_active = 1')
            license_revenue = c.fetchone()[0]
            
            c.execute('''SELECT COALESCE(SUM(amount), 0) FROM service_invoices 
                        WHERE status = 'paid' ''')
            service_revenue = c.fetchone()[0]
            
            # فاکتورهای در انتظار
            c.execute('''SELECT COUNT(*) FROM service_invoices 
                        WHERE status = 'pending' ''')
            pending_invoices = c.fetchone()[0]
            
            # درآمد ماهانه جاری
            now = datetime.now()
            current_month_start = f"{now.year}-{now.month:02d}-01"
            
            c.execute('''SELECT COALESCE(SUM(service_monthly_fee), 0) 
                        FROM customers WHERE is_active = 1 AND has_service = 1 
                        AND service_status = 'active' ''')
            monthly_recurring = c.fetchone()[0]
            
            return {
                'software_total': software_total,
                'software_active': software_active,
                'service_total': service_total,
                'service_active': service_active,
                'license_revenue': license_revenue,
                'service_revenue': service_revenue,
                'total_revenue': license_revenue + service_revenue,
                'pending_invoices': pending_invoices,
                'monthly_recurring': monthly_recurring,
            }
    
    def get_monthly_revenue_split(self, months: int = 6):
        """درآمد ۶ ماه اخیر — تفکیک نرم‌افزار و خدمات"""
        with self.get_db() as conn:
            c = conn.cursor()
            result = []
            
            today = datetime.now()
            
            for i in range(months - 1, -1, -1):
                month_date = today - timedelta(days=i*30)
                year = month_date.year
                month = month_date.month
                
                start = f"{year}-{month:02d}-01"
                if month == 12:
                    end = f"{year + 1}-01-01"
                else:
                    end = f"{year}-{month + 1:02d}-01"
                
                # نرم‌افزار
                c.execute('''
                    SELECT COALESCE(SUM(amount), 0)
                    FROM transactions
                    WHERE type IN ('license', 'renewal')
                    AND created_at >= ? AND created_at < ?
                ''', (start, end))
                license = c.fetchone()[0]
                
                # خدمات
                c.execute('''
                    SELECT COALESCE(SUM(amount), 0)
                    FROM transactions
                    WHERE type = 'service'
                    AND created_at >= ? AND created_at < ?
                ''', (start, end))
                service = c.fetchone()[0]
                
                month_names = [
                    '', 'ژانویه', 'فوریه', 'مارس', 'آوریل', 'می', 'ژوئن',
                    'جولای', 'اوت', 'سپتامبر', 'اکتبر', 'نوامبر', 'دسامبر'
                ]
                
                result.append({
                    'year': year,
                    'month': month,
                    'name': month_names[month],
                    'license': license,
                    'service': service,
                    'total': license + service,
                })
            
            return result
    
    def search_customers(self, query: str = '', filter_type: str = 'all'):
        with self.get_db() as conn:
            c = conn.cursor()
            
            sql = 'SELECT * FROM customers WHERE is_active = 1'
            params = []
            
            if query:
                sql += ''' AND (name LIKE ? OR company LIKE ? 
                          OR hwid LIKE ? OR phone LIKE ? OR email LIKE ?)'''
                q = f'%{query}%'
                params.extend([q, q, q, q, q])
            
            if filter_type == 'software':
                sql += " AND customer_type IN ('software', 'both')"
            elif filter_type == 'service':
                sql += " AND has_service = 1"
            elif filter_type == 'both':
                sql += " AND customer_type = 'both'"
            elif filter_type == 'active_license':
                sql += ''' AND license_type = 'full' 
                          AND julianday(expires_at) > julianday('now')'''
            elif filter_type == 'active_service':
                sql += " AND has_service = 1 AND service_status = 'active'"
            elif filter_type == 'expiring':
                sql += ''' AND julianday(expires_at) > julianday('now')
                          AND julianday(expires_at) <= julianday('now', '+30 day')'''
            elif filter_type == 'expired':
                sql += " AND julianday(expires_at) <= julianday('now')"
            
            sql += ' ORDER BY created_at DESC'
            
            c.execute(sql, params)
            return [dict(row) for row in c.fetchall()]
    
    # ============================================================
    # ========== پشتیبان‌گیری ==========
    # ============================================================
    
    def create_backup(self):
        try:
            self.backup_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = self.backup_dir / f"customers_{timestamp}.db"
            shutil.copy2(self.db_path, backup_file)
            
            backups = sorted(self.backup_dir.glob("customers_*.db"))
            while len(backups) > 10:
                old = backups.pop(0)
                try:
                    old.unlink()
                except Exception:
                    pass
            
            return str(backup_file)
        except Exception as e:
            raise RuntimeError(f"خطا در پشتیبان‌گیری: {e}")
    
    def restore_backup(self, backup_path: str):
        try:
            self.create_backup()
            shutil.copy2(backup_path, self.db_path)
            return True
        except Exception as e:
            raise RuntimeError(f"خطا در بازیابی: {e}")
    
    def get_backup_list(self):
        if not self.backup_dir.exists():
            return []
        backups = sorted(self.backup_dir.glob("customers_*.db"), reverse=True)
        result = []
        for b in backups:
            size = b.stat().st_size
            mtime = datetime.fromtimestamp(b.stat().st_mtime)
            result.append({
                'path': str(b), 'name': b.name,
                'size': size, 'mtime': mtime,
            })
        return result


# ============================================================
# ========== ساخت Manifest ==========
# ============================================================

def build_manifest(plugin_id, name, version="1.0.0", author="ImanAI",
                   description="", plugin_type="internal", icon="🔌",
                   required_modules=None, required_license=""):
    if required_modules is None:
        required_modules = []
    return {
        'id': plugin_id, 'name': name, 'version': version,
        'author': author, 'description': description,
        'type': plugin_type, 'icon': icon,
        'required_modules': required_modules,
        'required_license': required_license,
        'created_at': datetime.now().isoformat(),
        'format_version': 3,
    }


# ============================================================
# ========== نمودار (تفکیک‌شده) ============
# ============================================================

class RevenueChart(QWidget):
    """نمودار درآمد — نرم‌افزار + خدمات"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = []
        self.setMinimumHeight(220)
        self.setStyleSheet("background: #0a0a1a; border-radius: 8px;")
    
    def set_data(self, data):
        self.data = data
        self.update()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        w = self.width()
        h = self.height()
        
        painter.fillRect(0, 0, w, h, QColor("#0a0a1a"))
        
        if not self.data:
            painter.setPen(QColor("#666"))
            painter.setFont(QFont("Tahoma", 11))
            painter.drawText(0, 0, w, h, Qt.AlignCenter, "داده‌ای نیست")
            return
        
        margin_left = 70
        margin_right = 20
        margin_top = 40
        margin_bottom = 50
        
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom
        
        max_amount = max(d.get('total', 0) for d in self.data) if self.data else 1
        if max_amount == 0:
            max_amount = 1
        
        # خطوط افقی
        painter.setPen(QPen(QColor("#1a2a4a"), 1))
        for i in range(5):
            y = margin_top + (chart_h * i / 4)
            painter.drawLine(margin_left, int(y), w - margin_right, int(y))
            
            value = max_amount * (4 - i) / 4
            painter.setPen(QColor("#888"))
            painter.setFont(QFont("Tahoma", 8))
            painter.drawText(0, int(y) - 8, margin_left - 5, 16,
                           Qt.AlignRight | Qt.AlignVCenter,
                           f"{int(value / 1000):,}K")
            painter.setPen(QPen(QColor("#1a2a4a"), 1))
        
        # ستون‌ها
        n = len(self.data)
        bar_width = chart_w / (n * 2)
        spacing = chart_w / n
        
        for i, d in enumerate(self.data):
            x_base = margin_left + (i * spacing) + (spacing - bar_width * 2) / 2
            
            # ستون نرم‌افزار (آبی)
            lic_h = (d.get('license', 0) / max_amount) * chart_h
            painter.setBrush(QBrush(QColor("#3498db")))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(
                int(x_base), int(margin_top + chart_h - lic_h),
                int(bar_width), int(lic_h), 3, 3
            )
            
            # ستون خدمات (سبز)
            ser_h = (d.get('service', 0) / max_amount) * chart_h
            painter.setBrush(QBrush(QColor("#27ae60")))
            painter.drawRoundedRect(
                int(x_base + bar_width + 2),
                int(margin_top + chart_h - ser_h),
                int(bar_width), int(ser_h), 3, 3
            )
            
            # نام ماه
            painter.setPen(QColor("#ccc"))
            painter.setFont(QFont("Tahoma", 9))
            painter.drawText(
                int(x_base - 15), int(margin_top + chart_h + 10),
                int(bar_width * 2 + 30), 25,
                Qt.AlignCenter, d['name']
            )
            
            # مقدار کل
            total = d.get('total', 0)
            if total > 0:
                painter.setPen(QColor("#e94560"))
                painter.setFont(QFont("Tahoma", 8, QFont.Bold))
                painter.drawText(
                    int(x_base - 20), int(margin_top + chart_h - lic_h - ser_h - 22),
                    int(bar_width * 2 + 40), 18,
                    Qt.AlignCenter, f"{int(total / 1000):,}K"
                )
        
        # راهنما
        painter.setPen(QColor("#3498db"))
        painter.setFont(QFont("Tahoma", 9, QFont.Bold))
        painter.drawText(margin_left, 10, 150, 20, Qt.AlignLeft, "🟦 نرم‌افزار")
        
        painter.setPen(QColor("#27ae60"))
        painter.drawText(margin_left + 120, 10, 150, 20, Qt.AlignLeft, "🟩 خدمات")
        
        # عنوان
        painter.setPen(QColor("#e94560"))
        painter.setFont(QFont("Tahoma", 12, QFont.Bold))
        painter.drawText(0, 5, w, 25, Qt.AlignCenter, "📊 درآمد ۶ ماه اخیر")


# ============================================================
# ========== تب ۱: داشبورد ==========
# ============================================================

class DashboardTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.db = parent_window.db
        self.core = parent_window.core
        self.setup_ui()
        self.load()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("📊 داشبورد")
        title.setStyleSheet("font-size: 20pt; font-weight: bold; color: #e94560; padding: 10px;")
        layout.addWidget(title)
        
        # ===== KPI ردیف ۱ =====
        kpi1 = QHBoxLayout()
        kpi1.setSpacing(10)
        
        self.sw_total_card = self._card("💻 مشتریان نرم‌افزار", "0", "#3498db")
        kpi1.addWidget(self.sw_total_card)
        
        self.sw_active_card = self._card("✅ فعال", "0", "#4CAF50")
        kpi1.addWidget(self.sw_active_card)
        
        self.srv_total_card = self._card("📊 مشتریان خدمات", "0", "#9C27B0")
        kpi1.addWidget(self.srv_total_card)
        
        self.srv_active_card = self._card("✅ خدمات فعال", "0", "#27ae60")
        kpi1.addWidget(self.srv_active_card)
        
        layout.addLayout(kpi1)
        
        # ===== KPI ردیف ۲ =====
        kpi2 = QHBoxLayout()
        kpi2.setSpacing(10)
        
        self.license_rev_card = self._card("💰 درآمد نرم‌افزار", "0", "#3498db")
        kpi2.addWidget(self.license_rev_card)
        
        self.service_rev_card = self._card("💼 درآمد خدمات", "0", "#27ae60")
        kpi2.addWidget(self.service_rev_card)
        
        self.mrr_card = self._card("📅 درآمد ماهانه خدمات", "0", "#F39C12")
        kpi2.addWidget(self.mrr_card)
        
        self.pending_card = self._card("⏳ فاکتور در انتظار", "0", "#e74c3c")
        kpi2.addWidget(self.pending_card)
        
        layout.addLayout(kpi2)
        
        # ===== نمودار =====
        chart_group = QGroupBox("📊 نمودار درآمد")
        chart_layout = QVBoxLayout(chart_group)
        
        self.chart = RevenueChart()
        chart_layout.addWidget(self.chart)
        
        layout.addWidget(chart_group)
        
        # ===== اطلاعات =====
        info_group = QGroupBox("💻 اطلاعات سیستم")
        info_layout = QVBoxLayout(info_group)
        
        self.info = QTextEdit()
        self.info.setReadOnly(True)
        self.info.setMaximumHeight(120)
        self.info.setStyleSheet("""
            QTextEdit {
                background: #16213e; color: #e0e0e0;
                font-family: 'Courier New', monospace;
                font-size: 10pt; padding: 10px;
                border-radius: 8px;
            }
        """)
        info_layout.addWidget(self.info)
        layout.addWidget(info_group)
        
        # ===== دکمه‌ها =====
        btn_row = QHBoxLayout()
        
        r = QPushButton("🔄 بروزرسانی")
        r.clicked.connect(self.load)
        btn_row.addWidget(r)
        
        backup_btn = QPushButton("💾 پشتیبان‌گیری")
        backup_btn.setStyleSheet("QPushButton { background: #4CAF50; }")
        backup_btn.clicked.connect(self.backup_now)
        btn_row.addWidget(backup_btn)
        
        restore_btn = QPushButton("📂 بازیابی")
        restore_btn.setStyleSheet("QPushButton { background: #FF9800; }")
        restore_btn.clicked.connect(self.restore_backup)
        btn_row.addWidget(restore_btn)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)
    
    def _card(self, title, value, color):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {color}; border-radius: 10px;
                padding: 12px; min-height: 80px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(10, 8, 10, 8)
        
        t = QLabel(title)
        t.setStyleSheet("color: white; font-size: 10pt; font-weight: bold;")
        layout.addWidget(t)
        
        v = QLabel(value)
        v.setStyleSheet("color: white; font-size: 18pt; font-weight: bold;")
        layout.addWidget(v)
        
        card.value_label = v
        return card
    
    def load(self):
        try:
            stats = self.db.get_stats()
            
            self.sw_total_card.value_label.setText(str(stats.get('software_total', 0)))
            self.sw_active_card.value_label.setText(str(stats.get('software_active', 0)))
            self.srv_total_card.value_label.setText(str(stats.get('service_total', 0)))
            self.srv_active_card.value_label.setText(str(stats.get('service_active', 0)))
            self.license_rev_card.value_label.setText(f"{stats.get('license_revenue', 0):,}")
            self.service_rev_card.value_label.setText(f"{stats.get('service_revenue', 0):,}")
            self.mrr_card.value_label.setText(f"{stats.get('monthly_recurring', 0):,}")
            self.pending_card.value_label.setText(str(stats.get('pending_invoices', 0)))
            
            # نمودار
            monthly = self.db.get_monthly_revenue_split(6)
            self.chart.set_data(monthly)
            
            # اطلاعات
            try:
                from license_core import KEYS_DIR
                keys_dir_str = str(KEYS_DIR)
            except Exception:
                keys_dir_str = "نامشخص"
            
            info = f"""
👨‍💼 حالت: فروشنده + خدمات حسابداری
🔑 کلید خصوصی: {'✅' if self.core.private_key else '❌'}
🔓 کلید عمومی: {'✅' if self.core.public_key else '❌'}

💰 کل درآمد: {stats.get('total_revenue', 0):,} تومان
📅 درآمد ماهانه خدمات: {stats.get('monthly_recurring', 0):,} تومان

📁 پنل: {ADMIN_DIR}
💾 دیتابیس: {self.db.db_path}

📅 {datetime.now().strftime('%Y/%m/%d %H:%M')}
            """.strip()
            
            self.info.setText(info)
        except Exception as e:
            safe_print(f"خطا: {e}")
    
    def backup_now(self):
        try:
            path = self.db.create_backup()
            self.parent_window.show_success("✅", f"پشتیبان ساخته شد:\n{path}")
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def restore_backup(self):
        backups = self.db.get_backup_list()
        if not backups:
            self.parent_window.show_warning("خطا", "پشتیبانی وجود ندارد!")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle("📂 بازیابی")
        dialog.setMinimumSize(500, 400)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("یک پشتیبان را انتخاب کن:"))
        
        list_widget = QListWidget()
        list_widget.setStyleSheet("""
            QListWidget {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item { padding: 8px; }
            QListWidget::item:selected { background: #533483; }
        """)
        
        for b in backups:
            text = f"📅 {b['mtime'].strftime('%Y/%m/%d %H:%M')} | {b['size']:,} بایت"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, b['path'])
            list_widget.addItem(item)
        
        layout.addWidget(list_widget)
        
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        layout.addWidget(box)
        
        if dialog.exec_() == QDialog.Accepted:
            current = list_widget.currentItem()
            if not current:
                return
            path = current.data(Qt.UserRole)
            
            if QMessageBox.question(self, "تأیید",
                "⚠️ این کار همه اطلاعات را جایگزین می‌کند!\nادامه؟",
                QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                try:
                    self.db.restore_backup(path)
                    self.load()
                    self.parent_window.show_success("✅", "بازیابی انجام شد!")
                except Exception as e:
                    self.parent_window.show_error("خطا", str(e))
    
    def refresh(self):
        self.load()


# ============================================================
# ========== تب ۲: ایجاد مشتری ==========
# ============================================================

class CreateCustomerTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.db = parent_window.db
        self.core = parent_window.core
        self.generated_license = None
        self.generated_formatted = None
        self.setup_ui()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # ===== چپ (اسکرول) =====
        left_scroll = QTextEdit()  # placeholder
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        
        title = QLabel("➕ ایجاد مشتری جدید")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        left_layout.addWidget(title)
        
        # ===== نوع مشتری =====
        type_group = QGroupBox("🎯 نوع مشتری")
        type_layout = QVBoxLayout(type_group)
        
        self.type_combo = QComboBox()
        self.type_combo.addItems([
            "💻 فقط نرم‌افزار",
            "📊 فقط خدمات حسابداری",
            "🎯 ترکیبی (نرم‌افزار + خدمات)",
        ])
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        type_layout.addWidget(self.type_combo)
        
        left_layout.addWidget(type_group)
        
        # ===== اطلاعات مشتری =====
        info_group = QGroupBox("👤 اطلاعات مشتری")
        info_layout = QFormLayout(info_group)
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("مثال: شرکت الف")
        info_layout.addRow("نام *:", self.name_input)
        
        self.company_input = QLineEdit()
        info_layout.addRow("شرکت:", self.company_input)
        
        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("09121234567")
        info_layout.addRow("تلفن:", self.phone_input)
        
        self.email_input = QLineEdit()
        info_layout.addRow("ایمیل:", self.email_input)
        
        left_layout.addWidget(info_group)
        
        # ===== HWID (فقط نرم‌افزار) =====
        self.hwid_group = QGroupBox("🖥️ HWID مشتری")
        hwid_layout = QVBoxLayout(self.hwid_group)
        
        self.hwid_input = QTextEdit()
        self.hwid_input.setPlaceholderText("HWID مشتری رو پیست کن")
        self.hwid_input.setMaximumHeight(60)
        hwid_layout.addWidget(self.hwid_input)
        
        left_layout.addWidget(self.hwid_group)
        
        # ===== تنظیمات لایسنس =====
        self.license_group = QGroupBox("🔑 تنظیمات لایسنس")
        config_layout = QFormLayout(self.license_group)
        
        self.duration = QComboBox()
        self.duration.addItems([
            "۱ ماه (۳۰ روز)", "۳ ماه (۹۰ روز)", "۶ ماه (۱۸۰ روز)",
            "۱ سال (۳۶۵ روز)", "۲ سال (۷۳۰ روز)", "۳ سال (۱۰۹۵ روز)", "دلخواه"
        ])
        self.duration.setCurrentIndex(3)
        self.duration.currentIndexChanged.connect(self._on_duration)
        config_layout.addRow("مدت:", self.duration)
        
        self.custom_days = QSpinBox()
        self.custom_days.setRange(1, 3650)
        self.custom_days.setValue(365)
        self.custom_days.setSuffix(" روز")
        self.custom_days.setEnabled(False)
        config_layout.addRow("روز:", self.custom_days)
        
        self.license_price = QSpinBox()
        self.license_price.setRange(0, 999999999)
        self.license_price.setSuffix(" تومان")
        self.license_price.setSingleStep(100000)
        config_layout.addRow("قیمت نرم‌افزار:", self.license_price)
        
        left_layout.addWidget(self.license_group)
        
        # ===== ماژول‌ها =====
        self.modules_group = QGroupBox("📦 ماژول‌ها")
        mod_layout = QGridLayout(self.modules_group)
        
        self.module_checks = {}
        modules = [
            ('accounting', '📚 حسابداری'), ('inventory', '📦 انبار'),
            ('payroll', '💰 حقوق'), ('parties', '👥 اشخاص'),
            ('invoice', '📄 فروش'), ('purchase', '📥 خرید'),
            ('ai', '🤖 AI'), ('reports', '📊 گزارشات'),
        ]
        for i, (k, l) in enumerate(modules):
            cb = QCheckBox(l)
            cb.setChecked(True)
            self.module_checks[k] = cb
            mod_layout.addWidget(cb, i // 2, i % 2)
        
        left_layout.addWidget(self.modules_group)
        
        # ===== تنظیمات خدمات =====
        self.service_group = QGroupBox("📊 تنظیمات خدمات حسابداری")
        service_layout = QFormLayout(self.service_group)
        
        self.service_fee = QSpinBox()
        self.service_fee.setRange(0, 999999999)
        self.service_fee.setSuffix(" تومان / ماه")
        self.service_fee.setSingleStep(100000)
        self.service_fee.setValue(1500000)
        service_layout.addRow("مبلغ ماهانه:", self.service_fee)
        
        self.service_duration = QComboBox()
        self.service_duration.addItems([
            "۶ ماه", "۱۲ ماه", "۲۴ ماه"
        ])
        self.service_duration.setCurrentIndex(1)
        service_layout.addRow("مدت قرارداد:", self.service_duration)
        
        # خدمات
        services_widget = QWidget()
        services_layout = QGridLayout(services_widget)
        
        self.service_checks = {}
        services = [
            ('bookkeeping', '📒 دفترداری'),
            ('vat', '💰 ارزش افزوده'),
            ('performance', '📊 عملکرد'),
            ('insurance', '🏥 بیمه'),
            ('payroll_service', '👥 حقوق'),
            ('modian', '📤 مودیان'),
            ('consulting', '💬 مشاوره'),
            ('tax_planning', '📈 برنامه‌ریزی مالیاتی'),
        ]
        for i, (k, l) in enumerate(services):
            cb = QCheckBox(l)
            cb.setChecked(True)
            self.service_checks[k] = cb
            services_layout.addWidget(cb, i // 2, i % 2)
        
        service_layout.addRow("خدمات:", services_widget)
        
        self.service_notes = QLineEdit()
        service_layout.addRow("یادداشت خدمات:", self.service_notes)
        
        left_layout.addWidget(self.service_group)
        
        # ===== دکمه‌ها =====
        btn_layout = QHBoxLayout()
        
        gen = QPushButton("🔑 تولید لایسنس")
        gen.setStyleSheet("""
            QPushButton {
                background: #4CAF50; color: white;
                padding: 12px; border-radius: 8px;
                font-size: 12pt; font-weight: bold;
            }
        """)
        gen.setMinimumHeight(45)
        gen.clicked.connect(self.generate)
        btn_layout.addWidget(gen)
        
        save = QPushButton("💾 ذخیره مشتری")
        save.setStyleSheet("""
            QPushButton {
                background: #3498db; color: white;
                padding: 12px; border-radius: 8px;
                font-size: 12pt; font-weight: bold;
            }
        """)
        save.setMinimumHeight(45)
        save.clicked.connect(self.save)
        btn_layout.addWidget(save)
        
        left_layout.addLayout(btn_layout)
        left_layout.addStretch()
        
        # ===== اسکرول =====
        from PyQt5.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        layout.addWidget(scroll, 2)
        
        # ===== راست =====
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(12)
        
        t = QLabel("📋 نتیجه")
        t.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        right_layout.addWidget(t)
        
        lic_group = QGroupBox("🔑 کلید لایسنس")
        lic_layout = QVBoxLayout(lic_group)
        
        self.license_display = QTextEdit()
        self.license_display.setReadOnly(True)
        self.license_display.setPlaceholderText("هنوز تولید نشده...")
        self.license_display.setStyleSheet("""
            QTextEdit {
                background: #0a0a1a; color: #4CAF50;
                font-family: 'Courier New', monospace;
                font-size: 9pt; padding: 10px;
                border: 2px solid #4CAF50; border-radius: 8px;
                min-height: 100px;
            }
        """)
        lic_layout.addWidget(self.license_display)
        
        copy_lay = QHBoxLayout()
        c1 = QPushButton("📋 فرمت‌شده")
        c1.clicked.connect(lambda: self._copy('f'))
        copy_lay.addWidget(c1)
        c2 = QPushButton("📋 خام")
        c2.clicked.connect(lambda: self._copy('r'))
        copy_lay.addWidget(c2)
        lic_layout.addLayout(copy_lay)
        
        right_layout.addWidget(lic_group)
        
        info_g = QGroupBox("📋 خلاصه")
        info_l = QVBoxLayout(info_g)
        
        self.summary = QTextEdit()
        self.summary.setReadOnly(True)
        self.summary.setStyleSheet("""
            QTextEdit {
                background: #16213e; color: #e0e0e0;
                font-size: 10pt; padding: 10px;
                border-radius: 8px; min-height: 250px;
            }
        """)
        info_l.addWidget(self.summary)
        
        right_layout.addWidget(info_g)
        right_layout.addStretch()
        
        layout.addWidget(right, 1)
        
        # تنظیمات اولیه
        self._on_type_changed(0)
    
    def _on_type_changed(self, idx):
        """نمایش/مخفی کردن بخش‌ها بر اساس نوع مشتری"""
        is_software = idx in [0, 2]
        is_service = idx in [1, 2]
        
        # HWID + لایسنس + ماژول‌ها فقط برای نرم‌افزار
        self.hwid_group.setVisible(is_software)
        self.license_group.setVisible(is_software)
        self.modules_group.setVisible(is_software)
        
        # خدمات فقط برای خدمات
        self.service_group.setVisible(is_service)
        
        # دکمه تولید لایسنس فقط برای نرم‌افزار
        if not is_software:
            self.license_display.setPlaceholderText("برای خدمات لایسنس لازم نیست")
    
    def _on_duration(self, i):
        if i == 6:
            self.custom_days.setEnabled(True)
        else:
            self.custom_days.setEnabled(False)
            self.custom_days.setValue([30, 90, 180, 365, 730, 1095][i])
    
    def _get_days(self):
        if self.duration.currentIndex() == 6:
            return self.custom_days.value()
        return [30, 90, 180, 365, 730, 1095][self.duration.currentIndex()]
    
    def _get_service_months(self):
        return [6, 12, 24][self.service_duration.currentIndex()]
    
    def _get_customer_type(self):
        idx = self.type_combo.currentIndex()
        return ['software', 'service', 'both'][idx]
    
    def generate(self):
        ctype = self._get_customer_type()
        
        if ctype == 'service':
            self.parent_window.show_warning("توجه", "برای خدمات لایسنس لازم نیست!")
            return
        
        if not self.name_input.text().strip():
            self.parent_window.show_warning("خطا", "نام مشتری رو وارد کن!")
            return
        
        hwid = self.hwid_input.toPlainText().strip()
        if not hwid:
            self.parent_window.show_warning("خطا", "HWID مشتری رو وارد کن!")
            return
        
        modules = [k for k, cb in self.module_checks.items() if cb.isChecked()]
        if not modules:
            self.parent_window.show_warning("خطا", "یک ماژول انتخاب کن!")
            return
        
        try:
            result = self.core.generate_license(
                customer_name=self.name_input.text().strip(),
                company=self.company_input.text().strip(),
                expire_days=self._get_days(),
                modules=modules,
                limits={},
                machine_id=hwid
            )
            
            self.generated_license = result['license_key']
            self.generated_formatted = result['formatted']
            self.license_display.setText(result['formatted'])
            
            self._update_summary()
            self.parent_window.show_success("✅", "لایسنس تولید شد!")
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def _update_summary(self):
        ctype = self._get_customer_type()
        type_names = {
            'software': '💻 فقط نرم‌افزار',
            'service': '📊 فقط خدمات',
            'both': '🎯 ترکیبی',
        }
        
        text = f"""
🎯 نوع: {type_names.get(ctype, '')}

👤 نام: {self.name_input.text()}
🏢 شرکت: {self.company_input.text() or '-'}
📞 تلفن: {self.phone_input.text() or '-'}
"""
        
        if ctype in ['software', 'both']:
            text += f"""
━━━━━━━━━━━━━━━━━━━
💻 بخش نرم‌افزار:
📅 مدت: {self._get_days()} روز
💰 قیمت: {self.license_price.value():,} تومان
"""
            if self.generated_license:
                text += f"🆔 لایسنس: تولید شده ✅"
        
        if ctype in ['service', 'both']:
            months = self._get_service_months()
            fee = self.service_fee.value()
            total = fee * months
            
            services = [k for k, cb in self.service_checks.items() if cb.isChecked()]
            
            text += f"""
━━━━━━━━━━━━━━━━━━━
📊 بخش خدمات:
📅 مدت: {months} ماه
💰 ماهانه: {fee:,} تومان
💵 کل: {total:,} تومان
📋 خدمات: {', '.join(services)}
"""
        
        self.summary.setText(text.strip())
    
    def save(self):
        if not self.name_input.text().strip():
            self.parent_window.show_warning("خطا", "نام مشتری!")
            return
        
        try:
            ctype = self._get_customer_type()
            has_service = ctype in ['service', 'both']
            
            modules = [k for k, cb in self.module_checks.items() if cb.isChecked()]
            
            # تاریخ‌های خدمات
            service_start = ''
            service_end = ''
            service_fee = 0
            service_status = 'inactive'
            
            if has_service:
                service_fee = self.service_fee.value()
                months = self._get_service_months()
                now = datetime.now()
                service_start = now.strftime('%Y-%m-%d')
                service_end = (now + timedelta(days=months * 30)).strftime('%Y-%m-%d')
                service_status = 'active'
            
            data = {
                'name': self.name_input.text().strip(),
                'company': self.company_input.text().strip(),
                'phone': self.phone_input.text().strip(),
                'email': self.email_input.text().strip(),
                'hwid': self.hwid_input.toPlainText().strip(),
                'license_key': self.generated_formatted or '',
                'license_type': 'full',
                'modules': json.dumps(modules),
                'duration_days': self._get_days() if ctype in ['software', 'both'] else 0,
                'price': self.license_price.value() if ctype in ['software', 'both'] else 0,
                'notes': '',
                'customer_type': ctype,
                'has_service': has_service,
                'service_monthly_fee': service_fee,
                'service_start_date': service_start,
                'service_end_date': service_end,
                'service_status': service_status,
            }
            
            cid = self.db.add_customer(data)
            
            # ساخت قرارداد خدمات
            if has_service:
                services = [k for k, cb in self.service_checks.items() if cb.isChecked()]
                self.db.create_contract(
                    customer_id=cid,
                    start_date=service_start,
                    end_date=service_end,
                    monthly_fee=service_fee,
                    services=services,
                    notes=self.service_notes.text()
                )
            
            self.parent_window.show_success(
                "✅",
                f"مشتری #{cid} ذخیره شد!\n\n"
                f"نوع: {ctype}\n"
                f"خدمات: {'فعال' if has_service else 'ندارد'}"
            )
            self.parent_window.refresh_all()
            self._clear()
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def _clear(self):
        self.name_input.clear()
        self.company_input.clear()
        self.phone_input.clear()
        self.email_input.clear()
        self.hwid_input.clear()
        self.license_price.setValue(0)
        self.generated_license = None
        self.generated_formatted = None
        self.license_display.clear()
        self.summary.clear()
    
    def _copy(self, mode):
        if not self.generated_license:
            return
        text = self.generated_formatted if mode == 'f' else self.generated_license
        QApplication.clipboard().setText(text)
        self.parent_window.show_status("✅ کپی شد")
    
    def refresh(self):
        pass


# ============================================================
# ========== تب ۳: مشتریان (فیلتر + ویرایش) ==========
# ============================================================

class CustomersTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.db = parent_window.db
        self.core = parent_window.core
        self.all_customers = []
        self.setup_ui()
        self.load()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("👥 مدیریت مشتریان")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        layout.addWidget(title)
        
        # نوار ابزار ۱
        toolbar1 = QHBoxLayout()
        
        self.search = QLineEdit()
        self.search.setPlaceholderText("🔍 جستجو...")
        self.search.textChanged.connect(self.filter)
        toolbar1.addWidget(self.search, 2)
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems([
            "🔍 همه",
            "💻 نرم‌افزار",
            "📊 خدمات",
            "🎯 ترکیبی",
            "✅ لایسنس فعال",
            "✅ خدمات فعال",
            "⏰ نزدیک انقضا",
            "❌ منقضی",
        ])
        self.filter_combo.currentIndexChanged.connect(self.filter)
        toolbar1.addWidget(self.filter_combo, 1)
        
        layout.addLayout(toolbar1)
        
        # نوار ابزار ۲
        toolbar2 = QHBoxLayout()
        
        r = QPushButton("🔄")
        r.setToolTip("بروزرسانی")
        r.clicked.connect(self.load)
        toolbar2.addWidget(r)
        
        v = QPushButton("👁️ نمایش")
        v.clicked.connect(self.view)
        toolbar2.addWidget(v)
        
        e = QPushButton("✏️ ویرایش")
        e.setStyleSheet("QPushButton { background: #3498db; }")
        e.clicked.connect(self.edit)
        toolbar2.addWidget(e)
        
        rn = QPushButton("🔄 تمدید")
        rn.setStyleSheet("QPushButton { background: #FF9800; }")
        rn.clicked.connect(self.renew)
        toolbar2.addWidget(rn)
        
        cr = QPushButton("📄 قرارداد")
        cr.setStyleSheet("QPushButton { background: #9C27B0; }")
        cr.clicked.connect(self.show_contract)
        toolbar2.addWidget(cr)
        
        ex = QPushButton("📊 Excel")
        ex.setStyleSheet("QPushButton { background: #4CAF50; }")
        ex.clicked.connect(self.export_excel)
        toolbar2.addWidget(ex)
        
        d = QPushButton("🗑️")
        d.setStyleSheet("QPushButton { background: #e74c3c; }")
        d.clicked.connect(self.delete)
        toolbar2.addWidget(d)
        
        toolbar2.addStretch()
        layout.addLayout(toolbar2)
        
        # جدول
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "ID", "نام", "شرکت", "نوع", "نرم‌افزار",
            "خدمات", "ماهانه", "تلفن", "عملیات"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.doubleClicked.connect(self.view)
        layout.addWidget(self.table)
        
        # خلاصه
        self.summary = QLabel()
        self.summary.setStyleSheet("""
            font-weight: bold; padding: 10px;
            background: #16213e; border-radius: 6px;
            color: #e94560; font-size: 11pt;
        """)
        layout.addWidget(self.summary)
    
    def load(self):
        try:
            self.all_customers = self.db.get_all_customers()
            self.filter()
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def filter(self):
        query = self.search.text().strip()
        filter_map = {
            0: 'all', 1: 'software', 2: 'service', 3: 'both',
            4: 'active_license', 5: 'active_service',
            6: 'expiring', 7: 'expired',
        }
        ftype = filter_map.get(self.filter_combo.currentIndex(), 'all')
        
        try:
            customers = self.db.search_customers(query, ftype)
            self.display(customers)
        except Exception as e:
            safe_print(f"خطا: {e}")
            self.display(self.all_customers)
    
    def display(self, customers):
        self.table.setRowCount(len(customers))
        total_license = 0
        total_service = 0
        
        type_names = {
            'software': '💻 نرم‌افزار',
            'service': '📊 خدمات',
            'both': '🎯 ترکیبی',
        }
        
        for i, c in enumerate(customers):
            self.table.setItem(i, 0, QTableWidgetItem(str(c.get('id', ''))))
            self.table.setItem(i, 1, QTableWidgetItem(c.get('name', '')))
            self.table.setItem(i, 2, QTableWidgetItem(c.get('company', '-') or '-'))
            
            ctype = c.get('customer_type', 'software')
            ti = QTableWidgetItem(type_names.get(ctype, ctype))
            color = {
                'software': '#3498db',
                'service': '#9C27B0',
                'both': '#e94560',
            }.get(ctype, '#666')
            ti.setForeground(QColor(color))
            self.table.setItem(i, 3, ti)
            
            # وضعیت نرم‌افزار
            if ctype in ['software', 'both']:
                exp = c.get('expires_at', '')
                if exp:
                    try:
                        e = datetime.fromisoformat(exp)
                        d = (e - datetime.now()).days
                        if d < 0:
                            txt, col = f"❌ منقضی", '#e74c3c'
                        elif d <= 30:
                            txt, col = f"🟡 {d} روز", '#FF9800'
                        else:
                            txt, col = f"✅ {d} روز", '#4CAF50'
                        item = QTableWidgetItem(txt)
                        item.setForeground(QColor(col))
                        self.table.setItem(i, 4, item)
                    except Exception:
                        pass
                total_license += c.get('price', 0)
            else:
                self.table.setItem(i, 4, QTableWidgetItem('-'))
            
            # وضعیت خدمات
            if c.get('has_service'):
                status = c.get('service_status', 'inactive')
                if status == 'active':
                    txt, col = "✅ فعال", '#27ae60'
                else:
                    txt, col = "❌ غیرفعال", '#e74c3c'
                item = QTableWidgetItem(txt)
                item.setForeground(QColor(col))
                self.table.setItem(i, 5, item)
                
                fee = c.get('service_monthly_fee', 0)
                total_service += fee
                fi = QTableWidgetItem(f"{fee:,}")
                fi.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(i, 6, fi)
            else:
                self.table.setItem(i, 5, QTableWidgetItem('-'))
                self.table.setItem(i, 6, QTableWidgetItem('-'))
            
            self.table.setItem(i, 7, QTableWidgetItem(c.get('phone', '-') or '-'))
            
            # وضعیت کلی
            ops = QTableWidgetItem("👁️ ✏️")
            ops.setToolTip("دابل کلیک = نمایش")
            self.table.setItem(i, 8, ops)
        
        self.summary.setText(
            f"📊 {len(customers)} مشتری | "
            f"💰 نرم‌افزار: {total_license:,} | "
            f"📅 خدمات ماهانه: {total_service:,} تومان"
        )
    
    def get_selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        try:
            return int(self.table.item(row, 0).text())
        except Exception:
            return None
    
    def view(self):
        cid = self.get_selected_id()
        if not cid:
            self.parent_window.show_warning("خطا", "یک مشتری انتخاب کن!")
            return
        
        c = self.db.get_customer(cid)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"👁️ {c.get('name')}")
        dialog.setMinimumSize(700, 600)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")
        
        layout = QVBoxLayout(dialog)
        
        info = QTextEdit()
        info.setReadOnly(True)
        info.setStyleSheet("""
            QTextEdit {
                background: #0a0a1a; color: #4CAF50;
                font-family: 'Courier New', monospace;
                font-size: 11pt; padding: 15px; border-radius: 8px;
            }
        """)
        
        type_names = {
            'software': '💻 فقط نرم‌افزار',
            'service': '📊 فقط خدمات',
            'both': '🎯 ترکیبی',
        }
        
        text = f"""
👤 نام: {c.get('name', '-')}
🏢 شرکت: {c.get('company', '-')}
📞 تلفن: {c.get('phone', '-')}
📧 ایمیل: {c.get('email', '-')}
🎯 نوع: {type_names.get(c.get('customer_type', ''), '-')}
📅 تاریخ ثبت: {c.get('created_at', '')[:19]}
"""
        
        if c.get('customer_type') in ['software', 'both']:
            exp = c.get('expires_at', '')
            days_left = '-'
            if exp:
                try:
                    e = datetime.fromisoformat(exp)
                    days_left = (e - datetime.now()).days
                except Exception:
                    pass
            
            text += f"""
━━━━━━━━━━━━━━━━━━━
💻 نرم‌افزار:
🖥️ HWID: {c.get('hwid', '-')}
📅 انقضا: {exp[:10] if exp else '-'}
⏰ روز باقیمانده: {days_left}
💰 قیمت: {c.get('price', 0):,} تومان
🔑 لایسنس:
{c.get('license_key', '-')}
"""
        
        if c.get('has_service'):
            text += f"""
━━━━━━━━━━━━━━━━━━━
📊 خدمات حسابداری:
💰 ماهانه: {c.get('service_monthly_fee', 0):,} تومان
📅 شروع: {c.get('service_start_date', '-')}
📅 پایان: {c.get('service_end_date', '-')}
🎯 وضعیت: {c.get('service_status', '-')}
"""
        
        info.setText(text.strip())
        layout.addWidget(info)
        
        btn = QHBoxLayout()
        cp = QPushButton("📋 کپی لایسنس")
        cp.clicked.connect(lambda: QApplication.clipboard().setText(c.get('license_key', '') or ''))
        btn.addWidget(cp)
        btn.addStretch()
        cl = QPushButton("بستن")
        cl.clicked.connect(dialog.accept)
        btn.addWidget(cl)
        layout.addLayout(btn)
        
        dialog.exec_()
    
    def edit(self):
        cid = self.get_selected_id()
        if not cid:
            self.parent_window.show_warning("خطا", "یک مشتری انتخاب کن!")
            return
        
        c = self.db.get_customer(cid)
        if not c:
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"✏️ ویرایش {c.get('name')}")
        dialog.setMinimumSize(550, 600)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")
        
        layout = QVBoxLayout(dialog)
        
        title = QLabel(f"✏️ ویرایش مشتری #{cid}")
        title.setStyleSheet("font-size: 14pt; font-weight: bold; color: #e94560; padding: 10px;")
        layout.addWidget(title)
        
        form_group = QGroupBox("اطلاعات")
        form_layout = QFormLayout(form_group)
        
        name_input = QLineEdit(c.get('name', ''))
        form_layout.addRow("نام:", name_input)
        
        company_input = QLineEdit(c.get('company', '') or '')
        form_layout.addRow("شرکت:", company_input)
        
        phone_input = QLineEdit(c.get('phone', '') or '')
        form_layout.addRow("تلفن:", phone_input)
        
        email_input = QLineEdit(c.get('email', '') or '')
        form_layout.addRow("ایمیل:", email_input)
        
        hwid_input = QLineEdit(c.get('hwid', ''))
        form_layout.addRow("HWID:", hwid_input)
        
        notes_input = QTextEdit(c.get('notes', '') or '')
        notes_input.setMaximumHeight(60)
        form_layout.addRow("یادداشت:", notes_input)
        
        layout.addWidget(form_group)
        
        # بخش خدمات
        if c.get('has_service'):
            service_group = QGroupBox("📊 خدمات حسابداری")
            service_layout = QFormLayout(service_group)
            
            service_fee = QSpinBox()
            service_fee.setRange(0, 999999999)
            service_fee.setSuffix(" تومان / ماه")
            service_fee.setValue(c.get('service_monthly_fee', 0))
            service_layout.addRow("مبلغ ماهانه:", service_fee)
            
            service_status = QComboBox()
            service_status.addItems(["active - فعال", "inactive - غیرفعال", "suspended - معلق"])
            status_map = {'active': 0, 'inactive': 1, 'suspended': 2}
            service_status.setCurrentIndex(status_map.get(c.get('service_status', 'active'), 0))
            service_layout.addRow("وضعیت:", service_status)
            
            layout.addWidget(service_group)
        else:
            service_fee = None
            service_status = None
        
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        layout.addWidget(box)
        
        if dialog.exec_() == QDialog.Accepted:
            try:
                data = {
                    'name': name_input.text().strip(),
                    'company': company_input.text().strip(),
                    'phone': phone_input.text().strip(),
                    'email': email_input.text().strip(),
                    'hwid': hwid_input.text().strip(),
                    'notes': notes_input.toPlainText().strip(),
                    'has_service': c.get('has_service', 0),
                    'service_monthly_fee': service_fee.value() if service_fee else 0,
                    'service_start_date': c.get('service_start_date', ''),
                    'service_end_date': c.get('service_end_date', ''),
                    'service_status': service_status.currentText().split(' - ')[0] if service_status else 'inactive',
                }
                
                self.db.update_customer(cid, data)
                self.parent_window.show_success("✅", "مشتری ویرایش شد!")
                self.load()
            except Exception as e:
                self.parent_window.show_error("خطا", str(e))
    
    def show_contract(self):
        """نمایش قرارداد خدمات"""
        cid = self.get_selected_id()
        if not cid:
            self.parent_window.show_warning("خطا", "یک مشتری انتخاب کن!")
            return
        
        c = self.db.get_customer(cid)
        if not c.get('has_service'):
            self.parent_window.show_warning("توجه", "این مشتری خدمات ندارد!")
            return
        
        contracts = self.db.get_contracts(cid)
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"📄 قرارداد {c.get('name')}")
        dialog.setMinimumSize(600, 500)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")
        
        layout = QVBoxLayout(dialog)
        
        info = QTextEdit()
        info.setReadOnly(True)
        info.setStyleSheet("""
            QTextEdit {
                background: #0a0a1a; color: #4CAF50;
                font-family: 'Courier New', monospace;
                font-size: 11pt; padding: 15px;
            }
        """)
        
        if not contracts:
            info.setText("❌ قراردادی ثبت نشده")
        else:
            text = f"📄 قراردادهای {c.get('name')}\n{'=' * 50}\n\n"
            for ct in contracts:
                services = json.loads(ct.get('services', '[]'))
                text += f"""
🆔 قرارداد #{ct.get('id')}
📅 شروع: {ct.get('start_date', '')}
📅 پایان: {ct.get('end_date', '')}
💰 ماهانه: {ct.get('monthly_fee', 0):,} تومان
🎯 وضعیت: {ct.get('status', '')}
📋 خدمات: {', '.join(services)}

📝 یادداشت: {ct.get('notes', '-')}
{'=' * 50}

"""
            info.setText(text)
        
        layout.addWidget(info)
        
        close_btn = QPushButton("بستن")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        
        dialog.exec_()
    
    def renew(self):
        cid = self.get_selected_id()
        if not cid:
            self.parent_window.show_warning("خطا", "یک مشتری انتخاب کن!")
            return
        
        c = self.db.get_customer(cid)
        
        if c.get('customer_type') == 'service':
            self.parent_window.show_warning("توجه", "برای خدمات، تمدید قرارداد از بخش ویرایش انجام بده!")
            return
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"🔄 تمدید {c.get('name')}")
        dialog.setMinimumWidth(420)
        dialog.setStyleSheet("QDialog { background: #1a1a2e; }")
        
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"مشتری: {c.get('name')}"))
        layout.addWidget(QLabel(f"انقضای فعلی: {c.get('expires_at', '')[:10]}"))
        
        form = QFormLayout()
        days = QSpinBox()
        days.setRange(1, 3650)
        days.setValue(365)
        days.setSuffix(" روز")
        form.addRow("تمدید:", days)
        
        price = QSpinBox()
        price.setRange(0, 999999999)
        price.setSingleStep(100000)
        price.setSuffix(" تومان")
        form.addRow("قیمت:", price)
        
        layout.addLayout(form)
        
        box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        box.accepted.connect(dialog.accept)
        box.rejected.connect(dialog.reject)
        layout.addWidget(box)
        
        if dialog.exec_() == QDialog.Accepted:
            try:
                modules = json.loads(c.get('modules', '[]'))
                result = self.core.generate_license(
                    customer_name=c.get('name', ''),
                    company=c.get('company', '') or '',
                    expire_days=days.value(),
                    modules=modules,
                    machine_id=c.get('hwid', '')
                )
                
                new_exp = datetime.now() + timedelta(days=days.value())
                self.db.update_license(
                    cid, result['formatted'],
                    new_exp.isoformat(),
                    days.value(),
                    price.value()
                )
                
                self.parent_window.show_success(
                    "✅", f"تمدید شد! انقضای جدید: {new_exp.strftime('%Y-%m-%d')}"
                )
                self.load()
            except Exception as e:
                self.parent_window.show_error("خطا", str(e))
    
    def export_excel(self):
        if not self.all_customers:
            self.parent_window.show_warning("خطا", "داده‌ای نیست!")
            return
        
        default_name = f"customers_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_name, _ = QFileDialog.getSaveFileName(
            self, "ذخیره خروجی",
            str(ADMIN_DIR / default_name),
            "CSV Files (*.csv);;All Files (*)"
        )
        
        if not file_name:
            return
        
        try:
            with open(file_name, 'w', encoding='utf-8-sig', newline='') as f:
                writer = csv.writer(f)
                
                writer.writerow([
                    "ID", "نام", "شرکت", "تلفن", "ایمیل", "نوع مشتری",
                    "HWID", "لایسنس", "تاریخ انقضا", "روز باقیمانده",
                    "قیمت نرم‌افزار", "خدمات فعال", "مبلغ ماهانه",
                    "شروع خدمات", "پایان خدمات", "وضعیت خدمات"
                ])
                
                for c in self.all_customers:
                    exp = c.get('expires_at', '') or ''
                    days_left = ''
                    if exp:
                        try:
                            e = datetime.fromisoformat(exp)
                            days_left = (e - datetime.now()).days
                        except Exception:
                            pass
                    
                    writer.writerow([
                        c.get('id', ''),
                        c.get('name', ''),
                        c.get('company', ''),
                        c.get('phone', ''),
                        c.get('email', ''),
                        c.get('customer_type', 'software'),
                        c.get('hwid', ''),
                        c.get('license_key', ''),
                        exp[:10] if exp else '',
                        days_left,
                        c.get('price', 0),
                        'بله' if c.get('has_service') else 'خیر',
                        c.get('service_monthly_fee', 0),
                        c.get('service_start_date', ''),
                        c.get('service_end_date', ''),
                        c.get('service_status', ''),
                    ])
            
            self.parent_window.show_success(
                "✅",
                f"فایل:\n{file_name}\n\n📊 {len(self.all_customers)} مشتری"
            )
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def delete(self):
        cid = self.get_selected_id()
        if not cid:
            self.parent_window.show_warning("خطا", "یک مشتری انتخاب کن!")
            return
        
        c = self.db.get_customer(cid)
        
        if QMessageBox.question(
            self, "تأیید",
            f"'{c.get('name')}' حذف بشه؟\n\n(قابل بازگشت نیست)",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            self.db.delete_customer(cid)
            self.load()
            self.parent_window.show_success("✅", "حذف شد")
    
    def refresh(self):
        self.load()


# ============================================================
# ========== تب ۴: Trial Certificate ==========
# ============================================================

class TrialTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.core = parent_window.core
        self.setup_ui()
        self.check()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        title = QLabel("🎁 Trial Certificate")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        layout.addWidget(title)
        
        desc = QLabel(
            "📌 این گواهی در بیلد مشتری قرار می‌گیرد و به مشتری اجازه می‌دهد\n"
            "بدون لایسنس، برنامه را برای مدت مشخص تست کند."
        )
        desc.setStyleSheet("""
            color: #a0a0a0; font-size: 11pt; padding: 15px;
            background: #16213e; border-radius: 8px;
            border-left: 4px solid #e94560;
        """)
        desc.setWordWrap(True)
        layout.addWidget(desc)
        
        status_group = QGroupBox("📊 وضعیت")
        status_layout = QVBoxLayout(status_group)
        
        self.status = QLabel("...")
        self.status.setStyleSheet("""
            font-size: 12pt; padding: 15px;
            border-radius: 8px; background: #16213e;
        """)
        self.status.setWordWrap(True)
        status_layout.addWidget(self.status)
        layout.addWidget(status_group)
        
        config = QGroupBox("⚙️ تنظیمات")
        config_l = QFormLayout(config)
        
        self.days = QSpinBox()
        self.days.setRange(7, 365)
        self.days.setValue(30)
        self.days.setSuffix(" روز")
        config_l.addRow("مدت trial:", self.days)
        
        mod_widget = QWidget()
        mod_layout = QGridLayout(mod_widget)
        
        self.module_checks = {}
        modules = [
            ('accounting', '📚 حسابداری'), ('inventory', '📦 انبار'),
            ('payroll', '💰 حقوق'), ('parties', '👥 اشخاص'),
            ('invoice', '📄 فروش'), ('purchase', '📥 خرید'),
            ('ai', '🤖 AI'), ('reports', '📊 گزارشات'),
        ]
        for i, (k, l) in enumerate(modules):
            cb = QCheckBox(l)
            cb.setChecked(True)
            self.module_checks[k] = cb
            mod_layout.addWidget(cb, i // 4, i % 4)
        
        config_l.addRow("ماژول‌ها:", mod_widget)
        layout.addWidget(config)
        
        btn = QHBoxLayout()
        
        gen = QPushButton("🎁 تولید Certificate")
        gen.setStyleSheet("""
            QPushButton {
                background: #FF9800; color: white;
                padding: 15px; border-radius: 8px;
                font-size: 13pt; font-weight: bold;
            }
        """)
        gen.setMinimumHeight(50)
        gen.clicked.connect(self.generate)
        btn.addWidget(gen)
        
        rm = QPushButton("🗑️ حذف")
        rm.setStyleSheet("""
            QPushButton {
                background: #e74c3c; color: white;
                padding: 15px; border-radius: 8px;
                font-size: 13pt; font-weight: bold;
            }
        """)
        rm.setMinimumHeight(50)
        rm.clicked.connect(self.delete)
        btn.addWidget(rm)
        
        layout.addLayout(btn)
        layout.addStretch()
    
    def check(self):
        p = ADMIN_DIR / "trial_certificate.bin"
        if p.exists():
            size = p.stat().st_size
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            self.status.setText(
                f"✅ موجود\n"
                f"📁 {p.name}\n"
                f"📊 {size:,} بایت\n"
                f"📅 {mtime.strftime('%Y/%m/%d %H:%M')}"
            )
            self.status.setStyleSheet("""
                font-size: 12pt; padding: 15px;
                border-radius: 8px; background: #1a3a1a;
                color: #4CAF50; border-left: 4px solid #4CAF50;
            """)
        else:
            self.status.setText("⚠️ موجود نیست")
            self.status.setStyleSheet("""
                font-size: 12pt; padding: 15px;
                border-radius: 8px; background: #3a2a1a;
                color: #FF9800; border-left: 4px solid #FF9800;
            """)
    
    def generate(self):
        modules = [k for k, cb in self.module_checks.items() if cb.isChecked()]
        if not modules:
            self.parent_window.show_warning("خطا", "یک ماژول انتخاب کن!")
            return
        
        try:
            data = self.core.build_trial_certificate(
                trial_days=self.days.value(),
                modules=modules,
                limits={}
            )
            
            p = ADMIN_DIR / "trial_certificate.bin"
            with open(p, 'wb') as f:
                f.write(data)
            
            self.check()
            self.parent_window.show_success("✅", f"ساخته شد! {len(data):,} بایت")
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def delete(self):
        p = ADMIN_DIR / "trial_certificate.bin"
        if not p.exists():
            self.parent_window.show_warning("خطا", "فایل نیست!")
            return
        if QMessageBox.question(self, "تأیید", "حذف بشه؟") == QMessageBox.Yes:
            p.unlink()
            self.check()
    
    def refresh(self):
        self.check()


# ============================================================
# ========== تب ۵: امضای پلاگین ==========
# ============================================================

class SignPluginTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.core = parent_window.core
        self.db = parent_window.db
        
        self.selected_license_data = None
        self.code_data = None
        
        self.setup_ui()
        self.load_customers_list()
    
    def setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)
        
        # چپ
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setSpacing(12)
        
        title = QLabel("🔐 امضای پلاگین")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        left_layout.addWidget(title)
        
        manifest_group = QGroupBox("📄 اطلاعات Manifest")
        manifest_layout = QFormLayout(manifest_group)
        
        self.plugin_id = QLineEdit()
        self.plugin_id.setPlaceholderText("modian_invoice")
        manifest_layout.addRow("شناسه *:", self.plugin_id)
        
        self.plugin_name = QLineEdit()
        self.plugin_name.setPlaceholderText("ارسال صورتحساب مودیان")
        manifest_layout.addRow("نام *:", self.plugin_name)
        
        self.plugin_version = QLineEdit()
        self.plugin_version.setText("1.0.0")
        manifest_layout.addRow("نسخه:", self.plugin_version)
        
        self.plugin_author = QLineEdit()
        self.plugin_author.setText("ImanAI")
        manifest_layout.addRow("نویسنده:", self.plugin_author)
        
        self.plugin_description = QLineEdit()
        manifest_layout.addRow("توضیحات:", self.plugin_description)
        
        self.plugin_icon = QLineEdit()
        self.plugin_icon.setText("🔌")
        self.plugin_icon.setMaximumWidth(80)
        manifest_layout.addRow("آیکون:", self.plugin_icon)
        
        self.plugin_type = QComboBox()
        self.plugin_type.addItems([
            "internal (داخلی)",
            "official (رسمی)",
            "third_party (شخص ثالث)"
        ])
        manifest_layout.addRow("نوع:", self.plugin_type)
        
        left_layout.addWidget(manifest_group)
        
        modules_group = QGroupBox("📦 ماژول‌های موردنیاز")
        modules_layout = QGridLayout(modules_group)
        
        self.module_checks = {}
        modules = [
            ('accounting', '📚 حسابداری'), ('inventory', '📦 انبار'),
            ('payroll', '💰 حقوق'), ('parties', '👥 اشخاص'),
            ('invoice', '📄 فروش'), ('purchase', '📥 خرید'),
            ('ai', '🤖 AI'), ('reports', '📊 گزارشات'),
        ]
        for i, (k, l) in enumerate(modules):
            cb = QCheckBox(l)
            cb.setChecked(False)
            self.module_checks[k] = cb
            modules_layout.addWidget(cb, i // 2, i % 2)
        
        left_layout.addWidget(modules_group)
        
        code_group = QGroupBox("💻 فایل کد پلاگین")
        code_layout = QHBoxLayout(code_group)
        
        self.code_path = QLineEdit()
        self.code_path.setPlaceholderText("فایل .py پلاگین")
        self.code_path.setReadOnly(True)
        code_layout.addWidget(self.code_path)
        
        browse_code = QPushButton("📁")
        browse_code.clicked.connect(self.browse_code)
        code_layout.addWidget(browse_code)
        
        left_layout.addWidget(code_group)
        
        customer_group = QGroupBox("👤 انتخاب مشتری")
        customer_layout = QVBoxLayout(customer_group)
        
        self.customer_list = QListWidget()
        self.customer_list.setMaximumHeight(150)
        self.customer_list.itemClicked.connect(self.on_customer_selected)
        customer_layout.addWidget(self.customer_list)
        
        self.license_info = QLabel("هنوز مشتری‌ای انتخاب نشده")
        self.license_info.setStyleSheet("""
            color: #a0a0a0; font-size: 10pt; padding: 10px;
            background: #0a0a1a; border-radius: 6px;
        """)
        self.license_info.setWordWrap(True)
        customer_layout.addWidget(self.license_info)
        
        refresh_btn = QPushButton("🔄 بروزرسانی لیست")
        refresh_btn.clicked.connect(self.load_customers_list)
        customer_layout.addWidget(refresh_btn)
        
        left_layout.addWidget(customer_group)
        left_layout.addStretch()
        
        # راست
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(15)
        
        preview_group = QGroupBox("👁️ پیش‌نمایش")
        preview_layout = QVBoxLayout(preview_group)
        
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet("""
            QTextEdit {
                background: #0a0a1a; color: #4CAF50;
                font-family: 'Courier New', monospace;
                font-size: 10pt; padding: 10px;
                border-radius: 8px; min-height: 200px;
            }
        """)
        preview_layout.addWidget(self.preview)
        
        right_layout.addWidget(preview_group)
        
        btn_layout = QVBoxLayout()
        
        update_btn = QPushButton("🔄 بروزرسانی پیش‌نمایش")
        update_btn.clicked.connect(self.update_preview)
        btn_layout.addWidget(update_btn)
        
        encrypt_btn = QPushButton("🔐 رمزنگاری و ذخیره")
        encrypt_btn.setStyleSheet("""
            QPushButton {
                background: #9C27B0; color: white;
                padding: 20px; border-radius: 8px;
                font-size: 14pt; font-weight: bold;
            }
        """)
        encrypt_btn.setMinimumHeight(70)
        encrypt_btn.clicked.connect(self.encrypt_plugin)
        btn_layout.addWidget(encrypt_btn)
        
        right_layout.addLayout(btn_layout)
        right_layout.addStretch()
        
        layout.addWidget(left, 2)
        layout.addWidget(right, 1)
    
    def load_customers_list(self):
        self.customer_list.clear()
        customers = self.db.get_all_customers()
        
        if not customers:
            item = QListWidgetItem("❌ هیچ مشتری‌ای ثبت نشده")
            item.setFlags(Qt.NoItemFlags)
            self.customer_list.addItem(item)
            return
        
        for c in customers:
            if c.get('customer_type') == 'service':
                continue  # خدمات لایسنس ندارند
            
            exp = c.get('expires_at', '')
            status = "⚪"
            if exp:
                try:
                    e = datetime.fromisoformat(exp)
                    d = (e - datetime.now()).days
                    if d < 0:
                        status = "❌"
                    elif d <= 30:
                        status = "🟡"
                    else:
                        status = "✅"
                except Exception:
                    pass
            
            name = c.get('name', '')
            hwid_short = c.get('hwid', '')[:15]
            text = f"{status} {name} ({hwid_short}...)"
            
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, c.get('id'))
            self.customer_list.addItem(item)
    
    def on_customer_selected(self, item):
        cid = item.data(Qt.UserRole)
        if not cid:
            return
        
        c = self.db.get_customer(cid)
        if not c:
            return
        
        license_key = c.get('license_key', '')
        if not license_key:
            self.license_info.setText("❌ این مشتری لایسنس ندارد!")
            self.selected_license_data = None
            return
        
        result = self.core.verify_license(license_key)
        
        if not result.get('valid'):
            self.license_info.setText(f"❌ نامعتبر: {result.get('message', '')}")
            self.selected_license_data = None
            return
        
        self.selected_license_data = result['data']
        modules = result['data'].get('modules', [])
        days_left = result.get('days_left', 0)
        
        self.license_info.setText(
            f"✅ {c.get('name')}\n"
            f"🖥️ {c.get('hwid', '')[:25]}...\n"
            f"⏰ {days_left} روز\n"
            f"📦 {', '.join(modules)}"
        )
        self.license_info.setStyleSheet("""
            color: #4CAF50; font-size: 10pt; padding: 10px;
            background: #1a3a1a; border-radius: 6px;
            border-left: 4px solid #4CAF50;
        """)
        
        self.update_preview()
    
    def browse_code(self):
        p, _ = QFileDialog.getOpenFileName(self, "کد پلاگین", "", "Python (*.py)")
        if p:
            self.code_path.setText(p)
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    self.code_data = f.read()
                self.update_preview()
            except Exception as e:
                self.parent_window.show_error("خطا", str(e))
    
    def update_preview(self):
        if not self.plugin_id.text().strip():
            self.preview.setText("⚠️ شناسه پلاگین رو وارد کن")
            return
        
        manifest = build_manifest(
            plugin_id=self.plugin_id.text().strip(),
            name=self.plugin_name.text().strip() or self.plugin_id.text().strip(),
            version=self.plugin_version.text().strip() or "1.0.0",
            author=self.plugin_author.text().strip() or "ImanAI",
            description=self.plugin_description.text().strip(),
            plugin_type=self.plugin_type.currentText().split()[0],
            icon=self.plugin_icon.text().strip() or "🔌",
            required_modules=[k for k, cb in self.module_checks.items() if cb.isChecked()],
        )
        
        preview = "📄 Manifest:\n\n" + json.dumps(manifest, ensure_ascii=False, indent=2)
        
        if self.code_data:
            preview += f"\n\n💻 کد: {len(self.code_data):,} کاراکتر"
        else:
            preview += "\n\n⚠️ کد بارگذاری نشده"
        
        if self.selected_license_data:
            preview += f"\n\n👤 مشتری: {self.selected_license_data.get('customer', '')}"
        else:
            preview += "\n\n⚠️ مشتری انتخاب نشده"
        
        self.preview.setText(preview)
    
    def encrypt_plugin(self):
        if not self.plugin_id.text().strip():
            self.parent_window.show_warning("خطا", "شناسه!")
            return
        if not self.plugin_name.text().strip():
            self.parent_window.show_warning("خطا", "نام!")
            return
        if not self.code_data:
            self.parent_window.show_warning("خطا", "کد!")
            return
        if not self.selected_license_data:
            self.parent_window.show_warning("خطا", "مشتری!")
            return
        
        manifest = build_manifest(
            plugin_id=self.plugin_id.text().strip(),
            name=self.plugin_name.text().strip(),
            version=self.plugin_version.text().strip() or "1.0.0",
            author=self.plugin_author.text().strip() or "ImanAI",
            description=self.plugin_description.text().strip(),
            plugin_type=self.plugin_type.currentText().split()[0],
            icon=self.plugin_icon.text().strip() or "🔌",
            required_modules=[k for k, cb in self.module_checks.items() if cb.isChecked()],
        )
        
        try:
            encrypted = self.core.encrypt_plugin(
                manifest=manifest,
                code=self.code_data,
                license_data=self.selected_license_data
            )
            
            output_dir = ADMIN_DIR / "plugins_output"
            output_dir.mkdir(exist_ok=True)
            
            safe_name = manifest['id']
            safe_customer = self.selected_license_data.get('customer', 'unknown').replace(' ', '_')
            filename = f"{safe_name}_{safe_customer}.plugin"
            filepath = output_dir / filename
            
            with open(filepath, 'wb') as f:
                f.write(encrypted)
            
            self.parent_window.show_success(
                "✅ موفق",
                f"📁 {filepath}\n📊 {len(encrypted):,} بایت"
            )
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def refresh(self):
        self.load_customers_list()


# ============================================================
# ========== تب ۶: فاکتور خدمات ==========
# ============================================================

class ServiceInvoicesTab(QWidget):
    def __init__(self, parent_window):
        super().__init__()
        self.parent_window = parent_window
        self.db = parent_window.db
        self.setup_ui()
        self.load()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)
        
        title = QLabel("📄 فاکتورهای خدمات")
        title.setStyleSheet("font-size: 18pt; font-weight: bold; color: #e94560; padding: 10px;")
        layout.addWidget(title)
        
        # نوار ابزار
        toolbar = QHBoxLayout()
        
        gen_btn = QPushButton("🆕 تولید فاکتور ماه")
        gen_btn.setStyleSheet("QPushButton { background: #4CAF50; }")
        gen_btn.clicked.connect(self.generate_monthly_invoices)
        toolbar.addWidget(gen_btn)
        
        r = QPushButton("🔄")
        r.clicked.connect(self.load)
        toolbar.addWidget(r)
        
        toolbar.addStretch()
        
        self.filter_combo = QComboBox()
        self.filter_combo.addItems(["همه", "در انتظار", "پرداخت شده"])
        self.filter_combo.currentIndexChanged.connect(self.load)
        toolbar.addWidget(self.filter_combo)
        
        layout.addLayout(toolbar)
        
        # جدول
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "ID", "مشتری", "سال/ماه", "مبلغ", "وضعیت", "تاریخ پرداخت", "عملیات"
        ])
        self.table.setAlternatingRowColors(True)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        layout.addWidget(self.table)
        
        self.summary = QLabel()
        self.summary.setStyleSheet("""
            font-weight: bold; padding: 10px;
            background: #16213e; border-radius: 6px;
            color: #e94560;
        """)
        layout.addWidget(self.summary)
    
    def load(self):
        status_map = {0: None, 1: 'pending', 2: 'paid'}
        status = status_map.get(self.filter_combo.currentIndex())
        
        try:
            invoices = self.db.get_invoices(status=status)
            self.display(invoices)
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def display(self, invoices):
        self.table.setRowCount(len(invoices))
        total_pending = 0
        total_paid = 0
        
        for i, inv in enumerate(invoices):
            self.table.setItem(i, 0, QTableWidgetItem(str(inv.get('id', ''))))
            self.table.setItem(i, 1, QTableWidgetItem(inv.get('customer_name', '')))
            
            ym = f"{inv.get('year', '')}/{inv.get('month', ''):02d}"
            self.table.setItem(i, 2, QTableWidgetItem(ym))
            
            amount = inv.get('amount', 0)
            ai = QTableWidgetItem(f"{amount:,}")
            ai.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 3, ai)
            
            status = inv.get('status', 'pending')
            if status == 'paid':
                si = QTableWidgetItem("✅ پرداخت شده")
                si.setForeground(QColor('#4CAF50'))
                total_paid += amount
            else:
                si = QTableWidgetItem("⏳ در انتظار")
                si.setForeground(QColor('#FF9800'))
                total_pending += amount
            self.table.setItem(i, 4, si)
            
            paid_at = inv.get('paid_at', '') or '-'
            self.table.setItem(i, 5, QTableWidgetItem(paid_at[:10] if paid_at != '-' else '-'))
            
            if status == 'pending':
                btn_text = "💰 پرداخت"
            else:
                btn_text = "✅"
            self.table.setItem(i, 6, QTableWidgetItem(btn_text))
        
        self.summary.setText(
            f"📊 {len(invoices)} فاکتور | "
            f"⏳ در انتظار: {total_pending:,} | "
            f"✅ پرداخت شده: {total_paid:,} تومان"
        )
    
    def generate_monthly_invoices(self):
        """تولید فاکتور برای همه مشتریان خدمات فعال"""
        now = datetime.now()
        year = now.year
        month = now.month
        
        try:
            customers = self.db.search_customers('', 'active_service')
            
            if not customers:
                self.parent_window.show_warning("توجه", "مشتری خدمات فعال وجود ندارد!")
                return
            
            reply = QMessageBox.question(
                self, "تأیید",
                f"تولید فاکتور برای {len(customers)} مشتری؟\n\n"
                f"دوره: {year}/{month:02d}",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if reply != QMessageBox.Yes:
                return
            
            count = 0
            total = 0
            
            for c in customers:
                cid = c.get('id')
                fee = c.get('service_monthly_fee', 0)
                
                if fee > 0:
                    contracts = self.db.get_contracts(cid)
                    contract_id = contracts[0]['id'] if contracts else None
                    
                    self.db.generate_monthly_invoice(
                        customer_id=cid,
                        contract_id=contract_id,
                        year=year, month=month,
                        amount=fee
                    )
                    count += 1
                    total += fee
            
            self.load()
            self.parent_window.show_success(
                "✅ موفق",
                f"{count} فاکتور ساخته شد\n"
                f"💰 مجموع: {total:,} تومان"
            )
        except Exception as e:
            self.parent_window.show_error("خطا", str(e))
    
    def refresh(self):
        self.load()


# ============================================================
# ========== پنجره اصلی ==========
# ============================================================

class AdminPanel(QMainWindow):
    def __init__(self, core):
        super().__init__()
        
        self.core = core
        self.db = CustomersDB()
        
        self.setWindowTitle("👨‍💼 ImanAccount - پنل مدیریت (v5.0)")
        self.setMinimumSize(1450, 920)
        
        self.setup_ui()
        self.apply_theme()
    
    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # هدر
        header = QFrame()
        header.setFixedHeight(70)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1a1a2e, stop:1 #0f3460);
                border-bottom: 3px solid #e94560;
            }
        """)
        
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 10, 20, 10)
        
        icon = QLabel("👨‍💼")
        icon.setStyleSheet("font-size: 32pt;")
        h_layout.addWidget(icon)
        
        t = QLabel("پنل مدیریت — نرم‌افزار + خدمات حسابداری")
        t.setStyleSheet("font-size: 14pt; font-weight: bold; color: #e94560;")
        h_layout.addWidget(t)
        
        h_layout.addStretch()
        
        badge = QLabel("✅ v5.0")
        badge.setStyleSheet("""
            background: #4CAF50; color: white;
            padding: 6px 15px; border-radius: 15px;
            font-weight: bold;
        """)
        h_layout.addWidget(badge)
        
        layout.addWidget(header)
        
        # تب‌ها
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border: none; background: #1a1a2e; }
            QTabBar::tab {
                padding: 12px 20px; margin: 2px;
                border-radius: 6px; background: #16213e;
                color: #a0a0a0; font-weight: bold; font-size: 10pt;
            }
            QTabBar::tab:selected { background: #e94560; color: white; }
            QTabBar::tab:hover { background: #533483; color: white; }
        """)
        
        self.dashboard_tab = DashboardTab(self)
        self.create_tab = CreateCustomerTab(self)
        self.customers_tab = CustomersTab(self)
        self.invoices_tab = ServiceInvoicesTab(self)
        self.trial_tab = TrialTab(self)
        self.plugin_tab = SignPluginTab(self)
        
        self.tabs.addTab(self.dashboard_tab, "📊 داشبورد")
        self.tabs.addTab(self.create_tab, "➕ ایجاد مشتری")
        self.tabs.addTab(self.customers_tab, "👥 مشتریان")
        self.tabs.addTab(self.invoices_tab, "📄 فاکتور خدمات")
        self.tabs.addTab(self.trial_tab, "🎁 Trial")
        self.tabs.addTab(self.plugin_tab, "🔐 پلاگین")
        
        self.tabs.currentChanged.connect(self.on_tab_changed)
        
        layout.addWidget(self.tabs, 1)
        
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background: #0f3460; color: #e0e0e0;
                font-weight: bold; padding: 5px;
            }
        """)
        self.statusBar().showMessage("✅ آماده — v5.0 (نرم‌افزار + خدمات)")
    
    def on_tab_changed(self, index):
        tab = self.tabs.widget(index)
        if tab == self.plugin_tab:
            self.plugin_tab.load_customers_list()
        elif tab == self.invoices_tab:
            self.invoices_tab.load()
    
    def apply_theme(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background: #1a1a2e; color: #e0e0e0; }
            QLabel { color: #e0e0e0; }
            
            QLineEdit, QTextEdit {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 6px;
                padding: 8px; font-size: 11pt;
            }
            QLineEdit:focus, QTextEdit:focus { border-color: #e94560; }
            
            QComboBox {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 6px;
                padding: 8px; font-size: 11pt;
            }
            QComboBox QAbstractItemView {
                background: #16213e; color: #e0e0e0;
                selection-background-color: #e94560;
            }
            
            QPushButton {
                background: #e94560; color: white;
                border: none; border-radius: 6px;
                padding: 10px 20px; font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background: #c62a40; }
            
            QGroupBox {
                border: 2px solid #0f3460; border-radius: 8px;
                margin-top: 15px; padding-top: 15px;
                font-weight: bold; color: #e94560;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px;
                padding: 0 10px; background: #1a1a2e;
            }
            
            QTableWidget {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 8px;
                gridline-color: #0f3460; alternate-background-color: #0f0f23;
            }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:selected { background: #533483; color: white; }
            QHeaderView::section {
                background: #0f3460; color: white;
                padding: 10px; border: none; font-weight: bold;
            }
            
            QListWidget {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 6px;
                padding: 5px;
            }
            QListWidget::item { padding: 8px; border-radius: 4px; }
            QListWidget::item:selected { background: #533483; color: white; }
            QListWidget::item:hover { background: #0f3460; }
            
            QSpinBox {
                background: #16213e; color: #e0e0e0;
                border: 2px solid #0f3460; border-radius: 6px;
                padding: 8px;
            }
            
            QCheckBox { color: #e0e0e0; spacing: 8px; }
            QCheckBox::indicator {
                width: 20px; height: 20px; border-radius: 4px;
                border: 2px solid #0f3460; background: #16213e;
            }
            QCheckBox::indicator:checked {
                background: #e94560; border-color: #e94560;
            }
            
            QScrollArea { border: none; }
            QScrollBar:vertical {
                background: #16213e; width: 10px; border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #0f3460; border-radius: 5px; min-height: 20px;
            }
            QScrollBar::handle:vertical:hover { background: #e94560; }
        """)
    
    def show_success(self, title, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Information)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStyleSheet("""
            QMessageBox { background: #1a1a2e; }
            QMessageBox QLabel { color: #e0e0e0; font-size: 11pt; }
            QMessageBox QPushButton {
                background: #4CAF50; color: white;
                padding: 8px 20px; border: none; border-radius: 6px;
                font-weight: bold; min-width: 80px;
            }
        """)
        msg.exec_()
    
    def show_error(self, title, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStyleSheet("""
            QMessageBox { background: #1a1a2e; }
            QMessageBox QLabel { color: #e0e0e0; font-size: 11pt; }
            QMessageBox QPushButton {
                background: #e74c3c; color: white;
                padding: 8px 20px; border: none; border-radius: 6px;
                font-weight: bold; min-width: 80px;
            }
        """)
        msg.exec_()
    
    def show_warning(self, title, message):
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Warning)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.setStyleSheet("""
            QMessageBox { background: #1a1a2e; }
            QMessageBox QLabel { color: #e0e0e0; font-size: 11pt; }
            QMessageBox QPushButton {
                background: #FF9800; color: white;
                padding: 8px 20px; border: none; border-radius: 6px;
                font-weight: bold; min-width: 80px;
            }
        """)
        msg.exec_()
    
    def show_status(self, message, duration=3000):
        self.statusBar().showMessage(message, duration)
    
    def refresh_all(self):
        for tab in [self.dashboard_tab, self.customers_tab, self.invoices_tab]:
            if hasattr(tab, 'refresh'):
                tab.refresh()


# ============================================================
# ========== خطاگیری ==========
# ============================================================

def save_error_log(error_msg):
    try:
        log_path = ADMIN_DIR / "admin_error.log"
        with open(log_path, 'a', encoding='utf-8') as f:
            f.write(f"\n{'=' * 60}\n")
            f.write(f"=== {datetime.now().isoformat()} ===\n")
            f.write(error_msg)
            f.write("\n")
    except Exception:
        pass


def show_error_dialog(error_msg):
    try:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            _app = QApplication(sys.argv)
        
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("خطای بحرانی")
        msg.setText("خطای غیرمنتظره:")
        msg.setDetailedText(error_msg)
        msg.setStyleSheet("""
            QMessageBox { background: #1a1a2e; }
            QMessageBox QLabel { color: #e0e0e0; font-size: 11pt; }
            QMessageBox QPushButton {
                background: #e74c3c; color: white;
                padding: 8px 20px; border: none; border-radius: 6px;
                font-weight: bold; min-width: 80px;
            }
        """)
        msg.exec_()
    except Exception:
        pass


# ============================================================
# ========== اجرا ==========
# ============================================================

def main():
    core, ok = check_and_setup()
    
    if not ok:
        try:
            if QApplication.instance() is None:
                _app = QApplication(sys.argv)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("خطا")
            msg.setText(
                "راه‌اندازی ناموفق!\n\n"
                "فایل‌های license_core.py و registry_guard.py را\n"
                "کنار فایل اجرایی قرار بده.\n\n"
                f"مسیر: {ADMIN_DIR}"
            )
            msg.exec_()
        except Exception:
            pass
        return 1
    
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    
    app = QApplication(sys.argv)
    app.setApplicationName("ImanAccount Admin v5.0")
    
    window = AdminPanel(core)
    window.show()
    
    return app.exec_()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        error_msg = traceback.format_exc()
        save_error_log(error_msg)
        
        safe_print("\n" + "=" * 60)
        safe_print("❌ خطای غیرمنتظره:")
        safe_print("=" * 60)
        safe_print(error_msg)
        
        show_error_dialog(error_msg)
        
        sys.exit(1)
