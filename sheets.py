import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

SHEET_ID = os.getenv("GOOGLE_SHEET_ID")

# Tab names
TAB_BARANG_MASUK = "Barang_Masuk"
TAB_BARANG_KELUAR = "Barang_Keluar"
TAB_STOK = "Stok"
TAB_MASTER_BARANG = "Master_Barang"
TAB_USERS = "Users"

HEADER_BARANG_MASUK = ["Tanggal", "Cabang", "Nama Barang", "Kualitas", "Jumlah", "Modal/Satuan", "Total Modal", "Input By"]
HEADER_BARANG_KELUAR = ["Tanggal", "Cabang", "Nama Barang", "Jumlah", "Harga Jual/Satuan", "Total Penjualan", "Kasir"]
HEADER_STOK = ["Nama Barang", "Satuan", "Cabang", "Stok"]
HEADER_MASTER = ["ID", "Nama Barang", "Satuan", "Harga Jual Default", "Kualitas Default", "Deskripsi"]
HEADER_USERS = ["Username", "Password Hash", "Nama Lengkap", "Cabang", "Role", "Aktif"]


class SheetsClient:
    def __init__(self):
        self._gc = None
        self._sheet = None

    def _get_client(self):
        if self._gc is None:
            creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
            if creds_json:
                creds_dict = json.loads(creds_json)
            else:
                # fallback: baca dari file
                with open("service_account.json") as f:
                    creds_dict = json.load(f)
            creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
            self._gc = gspread.authorize(creds)
        return self._gc

    def _get_sheet(self):
        if self._sheet is None:
            gc = self._get_client()
            self._sheet = gc.open_by_key(SHEET_ID)
            self._ensure_tabs()
        return self._sheet

    def _ensure_tabs(self):
        """Buat tab yang belum ada beserta header-nya."""
        existing = [ws.title for ws in self._sheet.worksheets()]
        tabs = {
            TAB_BARANG_MASUK: HEADER_BARANG_MASUK,
            TAB_BARANG_KELUAR: HEADER_BARANG_KELUAR,
            TAB_STOK: HEADER_STOK,
            TAB_MASTER_BARANG: HEADER_MASTER,
            TAB_USERS: HEADER_USERS,
        }
        for tab, header in tabs.items():
            if tab not in existing:
                ws = self._sheet.add_worksheet(title=tab, rows=1000, cols=20)
                ws.append_row(header)

    def _get_ws(self, tab: str):
        return self._get_sheet().worksheet(tab)

    # ──────────────────────────────────────────
    # BARANG MASUK
    # ──────────────────────────────────────────
    def tambah_barang_masuk(self, tanggal, cabang, nama_barang, kualitas, jumlah, modal, input_by):
        ws = self._get_ws(TAB_BARANG_MASUK)
        total = jumlah * modal
        ws.append_row([tanggal, cabang, nama_barang, kualitas, jumlah, modal, total, input_by])
        self._update_stok(nama_barang, cabang, jumlah, "masuk")

    # ──────────────────────────────────────────
    # BARANG KELUAR
    # ──────────────────────────────────────────
    def tambah_barang_keluar(self, tanggal, cabang, nama_barang, jumlah, harga_jual, kasir):
        ws = self._get_ws(TAB_BARANG_KELUAR)
        total = jumlah * harga_jual
        ws.append_row([tanggal, cabang, nama_barang, jumlah, harga_jual, total, kasir])
        self._update_stok(nama_barang, cabang, jumlah, "keluar")

    # ──────────────────────────────────────────
    # STOK
    # ──────────────────────────────────────────
    def _update_stok(self, nama_barang: str, cabang: str, jumlah: int, tipe: str):
        ws = self._get_ws(TAB_STOK)
        records = ws.get_all_records()
        for i, row in enumerate(records):
            if row["Nama Barang"].lower() == nama_barang.lower() and row["Cabang"] == cabang:
                stok_lama = int(row["Stok"])
                stok_baru = stok_lama + jumlah if tipe == "masuk" else max(0, stok_lama - jumlah)
                ws.update_cell(i + 2, 4, stok_baru)  # kolom 4 = Stok
                return
        # Baris baru jika belum ada
        satuan = self._get_satuan(nama_barang)
        stok_awal = jumlah if tipe == "masuk" else 0
        ws.append_row([nama_barang, satuan, cabang, stok_awal])

    def _get_satuan(self, nama_barang: str) -> str:
        try:
            ws = self._get_ws(TAB_MASTER_BARANG)
            records = ws.get_all_records()
            for row in records:
                if row["Nama Barang"].lower() == nama_barang.lower():
                    return row.get("Satuan", "pcs")
        except Exception:
            pass
        return "pcs"

    def get_stok(self, cabang: str = None) -> list:
        ws = self._get_ws(TAB_STOK)
        records = ws.get_all_records()
        if cabang:
            records = [r for r in records if r["Cabang"] == cabang]
        # Sort by cabang then nama barang
        records.sort(key=lambda x: (x.get("Cabang", ""), x.get("Nama Barang", "")))
        return [
            {
                "nama_barang": r["Nama Barang"],
                "satuan": r.get("Satuan", "pcs"),
                "cabang": r["Cabang"],
                "stok": int(r["Stok"]),
            }
            for r in records
        ]

    # ──────────────────────────────────────────
    # MASTER BARANG
    # ──────────────────────────────────────────
    def get_master_barang(self) -> list:
        ws = self._get_ws(TAB_MASTER_BARANG)
        records = ws.get_all_records()
        return [
            {
                "id": r.get("ID", ""),
                "nama_barang": r["Nama Barang"],
                "satuan": r.get("Satuan", "pcs"),
                "harga_jual_default": r.get("Harga Jual Default", 0),
                "kualitas_default": r.get("Kualitas Default", "A"),
                "deskripsi": r.get("Deskripsi", ""),
            }
            for r in records
        ]

    def tambah_master_barang(self, nama, satuan, harga_jual, kualitas, deskripsi=""):
        ws = self._get_ws(TAB_MASTER_BARANG)
        records = ws.get_all_records()
        new_id = f"B{len(records) + 1:04d}"
        ws.append_row([new_id, nama, satuan, harga_jual, kualitas, deskripsi])

    # ──────────────────────────────────────────
    # USERS
    # ──────────────────────────────────────────
    def get_user(self, username: str) -> dict | None:
        ws = self._get_ws(TAB_USERS)
        records = ws.get_all_records()
        for row in records:
            if row["Username"].lower() == username.lower() and str(row.get("Aktif", "TRUE")).upper() == "TRUE":
                return {
                    "username": row["Username"],
                    "password_hash": row["Password Hash"],
                    "nama": row["Nama Lengkap"],
                    "cabang": row["Cabang"],
                    "role": row["Role"],
                }
        return None

    def get_all_users(self) -> list:
        ws = self._get_ws(TAB_USERS)
        return ws.get_all_records()

    def tambah_user(self, username, password_hash, nama, cabang, role):
        ws = self._get_ws(TAB_USERS)
        ws.append_row([username, password_hash, nama, cabang, role, "TRUE"])

    def update_password(self, username: str, password_hash: str):
        ws = self._get_ws(TAB_USERS)
        records = ws.get_all_records()
        for i, row in enumerate(records):
            if row["Username"].lower() == username.lower():
                ws.update_cell(i + 2, 2, password_hash)
                return True
        return False
