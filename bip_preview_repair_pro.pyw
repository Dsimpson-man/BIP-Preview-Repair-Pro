# -*- coding: utf-8 -*-
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import winreg
from tkinter import filedialog, messagebox, scrolledtext, ttk


APP_TITLE = "缩略图修复助手 Pro"
APP_VERSION = "2.2.0"
KEYSHOT_DLL_NAME = "KeyShot-ih.dll"
RHINO_DLL_NAME = "RhinoHandlers.dll"
KEYSHOT_ICON_HANDLER_CLSID = "{7FA698E6-F685-4536-B5CF-93F704102025}"
THUMBNAIL_HANDLER_KEY = "{E357FCCD-A995-4576-B01F-234630154E96}"
ASSOC_CHANGED = 0x08000000

MODULES = {
    "keyshot": {
        "label": "KeyShot .bip",
        "extension": ".bip",
        "dll": KEYSHOT_DLL_NAME,
        "kind": "KeyShot",
    },
    "rhino": {
        "label": "Rhino .3dm",
        "extension": ".3dm",
        "dll": RHINO_DLL_NAME,
        "kind": "Rhino",
    },
}


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(sys.argv[0]))


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def logs_dir():
    return ensure_dir(os.path.join(app_base_dir(), "logs"))


def timestamp():
    return time.strftime("%Y%m%d-%H%M%S")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def quote_arg(value):
    return '"' + str(value).replace('"', r'\"') + '"'


def relaunch_as_admin():
    if is_admin():
        return

    script = os.path.abspath(sys.argv[0])
    params = " ".join([quote_arg(script)] + [quote_arg(arg) for arg in sys.argv[1:]])
    rc = ctypes.windll.shell32.ShellExecuteW(
        None,
        "runas",
        sys.executable,
        params,
        None,
        1,
    )
    if rc <= 32:
        messagebox.showerror(APP_TITLE, "没有获得管理员权限，无法注册 KeyShot 预览组件。")
    sys.exit(0)


def normalize_keyshot_install_path(path):
    if not path:
        return None

    path = os.path.expandvars(str(path).strip().strip('"'))
    if not path:
        return None

    if path.lower().endswith(".exe") or path.lower().endswith(".dll"):
        path = os.path.dirname(path)

    candidates = [
        path,
        os.path.dirname(path),
        os.path.dirname(os.path.dirname(path)),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        dll_path = os.path.join(candidate, "bin", KEYSHOT_DLL_NAME)
        if os.path.isfile(dll_path):
            return candidate

    return None


def normalize_rhino_install_path(path):
    if not path:
        return None

    path = os.path.expandvars(str(path).strip().strip('"'))
    if not path:
        return None

    if path.lower().endswith(".exe") or path.lower().endswith(".dll"):
        path = os.path.dirname(path)

    candidates = [
        path,
        os.path.dirname(path),
        os.path.dirname(os.path.dirname(path)),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate = os.path.abspath(candidate)
        dll_path = os.path.join(candidate, "System", RHINO_DLL_NAME)
        if os.path.isfile(dll_path):
            return candidate
    return None


def make_display_name(path):
    base = os.path.basename(os.path.normpath(path))
    if base:
        return base
    return path


def add_found_keyshot(found, path, source):
    install_path = normalize_keyshot_install_path(path)
    if not install_path:
        return
    key = os.path.normcase(os.path.normpath(install_path))
    found[key] = {
        "name": make_display_name(install_path),
        "path": install_path,
        "source": source,
        "dll": os.path.join(install_path, "bin", KEYSHOT_DLL_NAME),
        "module": "keyshot",
    }


def add_found_rhino(found, path, source):
    install_path = normalize_rhino_install_path(path)
    if not install_path:
        return
    key = os.path.normcase(os.path.normpath(install_path))
    found[key] = {
        "name": make_display_name(install_path),
        "path": install_path,
        "source": source,
        "dll": os.path.join(install_path, "System", RHINO_DLL_NAME),
        "module": "rhino",
    }


def read_registry_value(root, path, value_name):
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return value
    except Exception:
        return None


def scan_keyshot_registry(found):
    roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    direct_paths = [
        r"SOFTWARE\Luxion\KeyShot",
        r"SOFTWARE\WOW6432Node\Luxion\KeyShot",
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\KeyShot.exe",
        r"SOFTWARE\Classes\Applications\KeyShot.exe\shell\open\command",
    ]

    for root in roots:
        for reg_path in direct_paths:
            for value_name in ("InstallDir", "InstallLocation", "Path", ""):
                value = read_registry_value(root, reg_path, value_name)
                if value:
                    add_found_keyshot(found, value, "注册表")

        for uninstall_root in uninstall_paths:
            try:
                with winreg.OpenKey(root, uninstall_root, 0, winreg.KEY_READ) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for index in range(count):
                        try:
                            sub_name = winreg.EnumKey(key, index)
                            sub_path = uninstall_root + "\\" + sub_name
                            display_name = read_registry_value(root, sub_path, "DisplayName")
                            if not display_name or "keyshot" not in display_name.lower():
                                continue
                            for value_name in ("InstallLocation", "InstallDir", "DisplayIcon", "UninstallString"):
                                value = read_registry_value(root, sub_path, value_name)
                                if value:
                                    add_found_keyshot(found, value.split(",")[0], "卸载信息")
                        except Exception:
                            continue
            except Exception:
                continue


def scan_keyshot_common_folders(found):
    roots = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        value = os.environ.get(env_name)
        if value and os.path.isdir(value):
            roots.append(value)

    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = letter + ":\\"
        if os.path.isdir(drive):
            roots.append(drive)
            for folder in ("KeyShot", "KeyShot Studio", "Luxion"):
                candidate = os.path.join(drive, folder)
                if os.path.isdir(candidate):
                    roots.append(candidate)

    seen_roots = set()
    for root in roots:
        root_key = os.path.normcase(os.path.normpath(root))
        if root_key in seen_roots:
            continue
        seen_roots.add(root_key)
        try:
            for item in os.listdir(root):
                full = os.path.join(root, item)
                if os.path.isdir(full) and ("keyshot" in item.lower() or "luxion" in item.lower()):
                    add_found_keyshot(found, full, "常见目录")
                    try:
                        for sub_item in os.listdir(full):
                            add_found_keyshot(found, os.path.join(full, sub_item), "常见目录")
                    except Exception:
                        pass
        except Exception:
            continue


def scan_keyshot_installations():
    found = {}
    scan_keyshot_registry(found)
    scan_keyshot_common_folders(found)
    result = list(found.values())
    result.sort(key=lambda item: item["path"].lower())
    return result


def scan_rhino_installations():
    found = {}
    roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    uninstall_paths = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for root in roots:
        for uninstall_root in uninstall_paths:
            try:
                with winreg.OpenKey(root, uninstall_root, 0, winreg.KEY_READ) as key:
                    count = winreg.QueryInfoKey(key)[0]
                    for index in range(count):
                        try:
                            sub_name = winreg.EnumKey(key, index)
                            sub_path = uninstall_root + "\\" + sub_name
                            display_name = read_registry_value(root, sub_path, "DisplayName")
                            if not display_name or ("rhino" not in display_name.lower() and "rhinoceros" not in display_name.lower()):
                                continue
                            for value_name in ("InstallLocation", "InstallDir", "DisplayIcon", "UninstallString"):
                                value = read_registry_value(root, sub_path, value_name)
                                if value:
                                    add_found_rhino(found, value.split(",")[0], "卸载信息")
                        except Exception:
                            continue
            except Exception:
                continue

    roots_to_scan = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
        value = os.environ.get(env_name)
        if value and os.path.isdir(value):
            roots_to_scan.append(value)
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = letter + ":\\"
        if os.path.isdir(drive):
            roots_to_scan.append(drive)

    seen = set()
    for root in roots_to_scan:
        key = os.path.normcase(os.path.normpath(root))
        if key in seen:
            continue
        seen.add(key)
        try:
            for item in os.listdir(root):
                full = os.path.join(root, item)
                lower = item.lower()
                if os.path.isdir(full) and ("rhino" in lower or "rhinoceros" in lower):
                    add_found_rhino(found, full, "常见目录")
                    try:
                        for sub_item in os.listdir(full):
                            add_found_rhino(found, os.path.join(full, sub_item), "常见目录")
                    except Exception:
                        pass
        except Exception:
            continue

    result = list(found.values())
    result.sort(key=lambda item: item["path"].lower())
    return result


def get_regsvr32_path():
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    preferred = os.path.join(system_root, "System32", "regsvr32.exe")
    if os.path.isfile(preferred):
        return preferred
    return "regsvr32.exe"


def register_preview_dll(dll_path):
    if not os.path.isfile(dll_path):
        return False, "没有找到 DLL：" + dll_path

    cmd = [get_regsvr32_path(), "/s", dll_path]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "regsvr32 超时，可能被系统权限或安全软件拦截。"
    except Exception as exc:
        return False, "调用 regsvr32 失败：" + str(exc)

    if proc.returncode == 0:
        refresh_shell_associations()
        return True, "注册成功：" + dll_path

    stderr = proc.stderr.decode("mbcs", errors="ignore").strip()
    stdout = proc.stdout.decode("mbcs", errors="ignore").strip()
    detail = stderr or stdout or "无详细输出"
    return False, "注册失败，退出码 {}：{}".format(proc.returncode, detail)


def refresh_shell_associations():
    try:
        ctypes.windll.shell32.SHChangeNotify(ASSOC_CHANGED, 0, None, None)
    except Exception:
        pass
    try:
        ie4uinit = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "ie4uinit.exe")
        if os.path.isfile(ie4uinit):
            subprocess.run([ie4uinit, "-show"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, timeout=10)
    except Exception:
        pass


def registry_get_default(path):
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, path, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, "")
            return value
    except Exception:
        return None


def registry_key_values(root, path):
    values = {}
    try:
        with winreg.OpenKey(root, path, 0, winreg.KEY_READ) as key:
            value_count = winreg.QueryInfoKey(key)[1]
            for index in range(value_count):
                name, value, value_type = winreg.EnumValue(key, index)
                values[name or "(default)"] = {"type": value_type, "value": value}
    except Exception:
        pass
    return values


def user_choice_prog_id(extension):
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{}\UserChoice".format(extension),
            0,
            winreg.KEY_READ,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "ProgId")
            return value
    except Exception:
        return None


def registry_set_default(path, value):
    with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, path) as key:
        winreg.SetValueEx(key, "", 0, winreg.REG_SZ, value)


def export_registry_snapshot(module_key="keyshot"):
    module = MODULES[module_key]
    active = get_active_handler_info(module_key)
    extension = module["extension"]
    paths = [
        extension,
        r"KeyShot.Document",
        r"KeyShot.Document\ShellEx\IconHandler",
        r"Applications\keyshot.exe",
        r"Applications\keyshot.exe\ShellEx\IconHandler",
        r"CLSID\{}\InProcServer32".format(KEYSHOT_ICON_HANDLER_CLSID),
        r"Rhino3DFile",
        r"Rhino3DFile\ShellEx",
        r"Applications\rhino.exe",
    ]
    snapshot = {
        "app": APP_TITLE,
        "version": APP_VERSION,
        "module": module["label"],
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "active": active,
        "hkcr": {},
        "hkcu_user_choice": {},
    }
    for path in paths:
        snapshot["hkcr"][path] = registry_key_values(winreg.HKEY_CLASSES_ROOT, path)
    snapshot["hkcu_user_choice"] = registry_key_values(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\{}\UserChoice".format(extension),
    )
    return snapshot


def save_registry_backup(module_key="keyshot"):
    path = os.path.join(logs_dir(), "registry-backup-{}-{}.json".format(module_key, timestamp()))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(export_registry_snapshot(module_key), f, ensure_ascii=False, indent=2)
    return path


def export_diagnostic_report(module_key, items, log_lines):
    module = MODULES[module_key]
    report_path = os.path.join(logs_dir(), "diagnostic-report-{}-{}.txt".format(module_key, timestamp()))
    active = get_active_handler_info(module_key)
    lines = [
        "{} {}".format(APP_TITLE, APP_VERSION),
        "生成时间：{}".format(time.strftime("%Y-%m-%d %H:%M:%S")),
        "说明：本工具为独立工具，不包含、不分发软件官方文件。",
        "当前模块：{}".format(module["label"]),
        "",
        "当前关联",
        "HKCR {} 类型：{}".format(module["extension"], active["prog_id"]),
        "用户默认打开方式：{}".format(active["user_choice"]),
        "资源管理器实际使用类型：{}".format(active["active_prog_id"]),
        "当前图标处理器：{}".format(active["icon_handler"]),
        "当前缩略图处理器：{}".format(active["thumbnail_handler"]),
        "当前生效 DLL：{}".format(active["inproc"]),
        "",
        "扫描到的安装目录",
    ]
    if items:
        for item in items:
            lines.append("- [{}] {} | {}".format(item.get("source", ""), item.get("name", ""), item.get("path", "")))
    else:
        lines.append("- 未扫描到安装目录")
    lines.extend(["", "操作日志"])
    lines.extend(log_lines or ["- 无"])
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return report_path


def ensure_bip_file_association():
    prog_id = registry_get_default(r".bip")
    if not prog_id:
        prog_id = "KeyShot.Document"
        registry_set_default(r".bip", prog_id)

    target_prog_ids = [prog_id]
    choice = user_choice_prog_id(".bip")
    if choice and choice not in target_prog_ids:
        target_prog_ids.append(choice)

    changed = []
    normal = []
    for target in target_prog_ids:
        icon_handler_path = target + r"\ShellEx\IconHandler"
        current_handler = registry_get_default(icon_handler_path)
        if current_handler != KEYSHOT_ICON_HANDLER_CLSID:
            registry_set_default(icon_handler_path, KEYSHOT_ICON_HANDLER_CLSID)
            changed.append(target)
        else:
            normal.append(target)

    if changed:
        refresh_shell_associations()
        return True, "已补齐图标处理器关联：{} -> {}".format("、".join(changed), KEYSHOT_ICON_HANDLER_CLSID)
    return True, "图标处理器关联正常：{}".format("、".join(normal or target_prog_ids))


def get_active_handler_info(module_key):
    module = MODULES[module_key]
    extension = module["extension"]
    prog_id = registry_get_default(extension) or "未设置"
    choice = user_choice_prog_id(extension)
    active_prog_id = choice or prog_id
    icon_handler = registry_get_default(str(active_prog_id) + r"\ShellEx\IconHandler") if active_prog_id != "未设置" else None
    thumbnail_handler = registry_get_default(str(active_prog_id) + r"\ShellEx\{}".format(THUMBNAIL_HANDLER_KEY)) if active_prog_id != "未设置" else None
    clsid = icon_handler or thumbnail_handler or "未设置"
    inproc = registry_get_default(r"CLSID\{}\InProcServer32".format(clsid)) if clsid != "未设置" else None
    return {
        "prog_id": prog_id,
        "user_choice": choice or "未设置",
        "active_prog_id": active_prog_id,
        "icon_handler": icon_handler or "未设置",
        "thumbnail_handler": thumbnail_handler or "未设置",
        "inproc": inproc or "未设置",
    }


def clear_thumbnail_cache_and_restart_explorer():
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return False, "没有找到 LOCALAPPDATA，无法定位缩略图缓存。"

    explorer_cache = os.path.join(local_app_data, "Microsoft", "Windows", "Explorer")
    if not os.path.isdir(explorer_cache):
        return False, "没有找到资源管理器缓存目录：" + explorer_cache

    deleted = 0
    errors = []

    subprocess.run(["taskkill", "/f", "/im", "explorer.exe"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False)
    time.sleep(1.0)

    for name in os.listdir(explorer_cache):
        lower = name.lower()
        if not (lower.startswith("thumbcache_") or lower.startswith("iconcache_")):
            continue
        if not lower.endswith(".db"):
            continue
        path = os.path.join(explorer_cache, name)
        try:
            os.remove(path)
            deleted += 1
        except Exception as exc:
            errors.append("{}：{}".format(name, exc))

    subprocess.Popen(["explorer.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)

    if errors:
        return False, "已删除 {} 个缓存文件，但有 {} 个失败：{}".format(deleted, len(errors), "；".join(errors[:3]))
    return True, "已删除 {} 个缩略图/图标缓存文件，并重启资源管理器。".format(deleted)


class FixerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("{} v{}".format(APP_TITLE, APP_VERSION))
        self.root.geometry("980x700")
        self.root.minsize(860, 620)
        self.root.configure(bg="#f4f6f8")

        self.queue = queue.Queue()
        self.items = []
        self.log_lines = []
        self.worker_running = False
        self.current_module = tk.StringVar(value=MODULES["keyshot"]["label"])

        self.build_style()
        self.build_ui()
        self.log("欢迎使用 {} v{}。建议按左侧 5 步流程操作。".format(APP_TITLE, APP_VERSION))
        self.log("本工具不会包含或分发软件官方文件，只调用本机已安装组件。")
        self.poll_queue()

    def build_style(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.colors = {
            "page": "#f4f1eb",
            "card": "#fbfaf7",
            "ink": "#252725",
            "muted": "#6f746f",
            "line": "#d8d3c9",
            "soft": "#ebe7df",
            "sage": "#cfd8cf",
            "sage_dark": "#687568",
            "charcoal": "#2b2f2c",
            "log_bg": "#1f2421",
            "log_fg": "#e8e3da",
        }
        self.style.configure("TFrame", background=self.colors["page"])
        self.style.configure("Card.TFrame", background=self.colors["card"])
        self.style.configure("TLabel", background=self.colors["page"], foreground=self.colors["ink"], font=("Microsoft YaHei UI", 9))
        self.style.configure("Card.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Microsoft YaHei UI", 9))
        self.style.configure("Muted.TLabel", background=self.colors["card"], foreground=self.colors["muted"], font=("Microsoft YaHei UI", 8))
        self.style.configure("Section.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Microsoft YaHei UI", 10, "bold"))
        self.style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=(10, 6), background=self.colors["soft"], foreground=self.colors["ink"])
        self.style.map("TButton", background=[("active", "#dfdbd2"), ("disabled", "#e9e6df")])
        self.style.configure("Primary.TButton", font=("Microsoft YaHei UI", 9, "bold"), padding=(14, 8), background=self.colors["charcoal"], foreground="#ffffff")
        self.style.map("Primary.TButton", background=[("active", "#3a403b"), ("disabled", "#b8b4ab")], foreground=[("disabled", "#ffffff")])
        self.style.configure("Treeview", rowheight=30, font=("Microsoft YaHei UI", 9), background="#ffffff", fieldbackground="#ffffff", foreground=self.colors["ink"], bordercolor=self.colors["line"])
        self.style.configure("Treeview.Heading", font=("Microsoft YaHei UI", 9, "bold"), background=self.colors["soft"], foreground=self.colors["ink"])
        self.style.map("Treeview", background=[("selected", self.colors["sage"])], foreground=[("selected", self.colors["ink"])])

    def build_ui(self):
        self.root.configure(bg=self.colors["page"])
        self.root.geometry("1120x760")
        self.root.minsize(980, 680)

        shell = tk.Frame(self.root, bg=self.colors["page"])
        shell.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)

        left = tk.Frame(shell, bg=self.colors["charcoal"], width=300)
        left.pack(side=tk.LEFT, fill=tk.Y)
        left.pack_propagate(False)

        right = tk.Frame(shell, bg=self.colors["page"])
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        tk.Label(
            left,
            text="BIP Preview\nRepair Pro",
            bg=self.colors["charcoal"],
            fg="#f7f3ec",
            font=("Microsoft YaHei UI", 20, "bold"),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=24, pady=(26, 6))
        tk.Label(
            left,
            text="适用于 KeyShot 用户的 .bip 图标/预览修复工具",
            bg=self.colors["charcoal"],
            fg="#cfc8bb",
            font=("Microsoft YaHei UI", 9),
            wraplength=245,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=24)

        step_box = tk.Frame(left, bg=self.colors["charcoal"])
        step_box.pack(fill=tk.X, padx=20, pady=(28, 10))
        self.add_step(step_box, "01", "自动扫描", "查找本机 KeyShot 安装目录。")
        self.add_step(step_box, "02", "选择常用版本", "多版本时只选平时使用的版本。")
        self.add_step(step_box, "03", "修复选中", "注册预览组件并补齐文件关联。")
        self.add_step(step_box, "04", "确认生效版本", "检查 Explorer 实际使用的 DLL。")
        self.add_step(step_box, "05", "清缓存", "重启资源管理器并刷新缩略图。")

        tk.Label(
            left,
            text="非官方独立工具\n不包含或分发 KeyShot 官方文件",
            bg=self.colors["charcoal"],
            fg="#aaa397",
            font=("Microsoft YaHei UI", 8),
            justify=tk.LEFT,
        ).pack(side=tk.BOTTOM, anchor=tk.W, padx=24, pady=22)

        header = tk.Frame(right, bg=self.colors["page"])
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text="{}  v{}".format(APP_TITLE, APP_VERSION),
            bg=self.colors["page"],
            fg=self.colors["ink"],
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            header,
            text="低风险修复 Windows 文件关联、IconHandler 和缩略图缓存。建议优先使用“修复选中”。",
            bg=self.colors["page"],
            fg=self.colors["muted"],
            font=("Microsoft YaHei UI", 9),
        ).pack(anchor=tk.W, pady=(4, 14))

        action_card = ttk.Frame(right, style="Card.TFrame", padding=14)
        action_card.pack(fill=tk.X)
        ttk.Label(action_card, text="操作面板", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 10))

        module_row = ttk.Frame(action_card, style="Card.TFrame")
        module_row.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(module_row, text="修复模块", style="Card.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.module_combo = ttk.Combobox(
            module_row,
            textvariable=self.current_module,
            values=[MODULES[key]["label"] for key in MODULES],
            state="readonly",
            width=16,
        )
        self.module_combo.pack(side=tk.LEFT)
        self.module_combo.bind("<<ComboboxSelected>>", self.on_module_changed)
        ttk.Label(module_row, text="KeyShot .bip / Rhino .3dm", style="Muted.TLabel").pack(side=tk.LEFT, padx=(10, 0))

        row1 = ttk.Frame(action_card, style="Card.TFrame")
        row1.pack(fill=tk.X)
        self.scan_btn = ttk.Button(row1, text="自动扫描", command=self.scan_versions)
        self.scan_btn.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
        self.add_btn = ttk.Button(row1, text="手动添加", command=self.add_path)
        self.add_btn.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
        self.remove_btn = ttk.Button(row1, text="删除选中", command=self.delete_selected)
        self.remove_btn.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
        self.fix_selected_btn = ttk.Button(row1, text="修复选中", style="Primary.TButton", command=self.fix_selected)
        self.fix_selected_btn.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))
        self.fix_btn = ttk.Button(row1, text="修复全部", command=self.fix_all)
        self.fix_btn.pack(side=tk.LEFT, padx=(0, 8), pady=(0, 8))

        row2 = ttk.Frame(action_card, style="Card.TFrame")
        row2.pack(fill=tk.X)
        self.diagnose_btn = ttk.Button(row2, text="查看当前生效版本", command=self.diagnose_association)
        self.diagnose_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.cache_btn = ttk.Button(row2, text="清缓存并重启资源管理器", command=self.clear_cache)
        self.cache_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.report_btn = ttk.Button(row2, text="导出诊断报告", command=self.export_report)
        self.report_btn.pack(side=tk.LEFT, padx=(0, 8))
        self.backup_btn = ttk.Button(row2, text="备份注册表", command=self.backup_registry)
        self.backup_btn.pack(side=tk.LEFT, padx=(0, 8))

        ttk.Label(
            action_card,
            text="售后建议：先让用户导出诊断报告，再决定是否清缓存或手动添加安装目录。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(10, 0))

        list_card = ttk.Frame(right, style="Card.TFrame", padding=14)
        list_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        self.list_title = ttk.Label(list_card, text="已发现的安装目录", style="Section.TLabel")
        self.list_title.pack(anchor=tk.W)
        list_frame = ttk.Frame(list_card, style="Card.TFrame")
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.tree = ttk.Treeview(list_frame, columns=("name", "path", "source"), show="headings", height=8)
        self.tree.heading("name", text="版本 / 目录名")
        self.tree.heading("path", text="安装路径")
        self.tree.heading("source", text="来源")
        self.tree.column("name", width=160, anchor=tk.CENTER)
        self.tree.column("path", width=520)
        self.tree.column("source", width=90, anchor=tk.CENTER)
        y_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        log_card = ttk.Frame(right, style="Card.TFrame", padding=14)
        log_card.pack(fill=tk.BOTH, expand=True, pady=(14, 0))
        ttk.Label(log_card, text="操作日志", style="Section.TLabel").pack(anchor=tk.W)
        self.log_text = scrolledtext.ScrolledText(
            log_card,
            height=8,
            state=tk.DISABLED,
            font=("Consolas", 9),
            bg=self.colors["log_bg"],
            fg=self.colors["log_fg"],
            insertbackground="#ffffff",
            relief=tk.FLAT,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(6, 8))

        self.status_var = tk.StringVar(value="就绪。选择模块后点击“自动扫描”，或手动添加安装目录。")
        status = tk.Label(
            right,
            textvariable=self.status_var,
            bg=self.colors["soft"],
            fg=self.colors["ink"],
            anchor=tk.W,
            padx=12,
            pady=8,
            font=("Microsoft YaHei UI", 9),
        )
        status.pack(fill=tk.X, pady=(14, 0))
        self.refresh_module_text()

    def module_label(self):
        return MODULES[self.current_module_key()]["label"]

    def current_module_key(self):
        value = self.current_module.get()
        for key, module in MODULES.items():
            if value == module["label"] or value == key:
                return key
        return "keyshot"

    def refresh_module_text(self):
        module = MODULES[self.current_module_key()]
        self.list_title.config(text="已发现的 {} 安装目录".format(module["kind"]))
        self.status_var.set("当前模块：{}。点击“自动扫描”，或手动添加安装目录。".format(module["label"]))

    def on_module_changed(self, event=None):
        self.items = []
        self.update_tree()
        self.refresh_module_text()
        self.log("已切换模块：{}".format(self.module_label()))

    def add_step(self, parent, number, title, desc):
        row = tk.Frame(parent, bg=self.colors["charcoal"])
        row.pack(fill=tk.X, pady=7)
        badge = tk.Label(
            row,
            text=number,
            bg="#eee7dc",
            fg=self.colors["charcoal"],
            width=4,
            height=2,
            font=("Microsoft YaHei UI", 9, "bold"),
        )
        badge.pack(side=tk.LEFT, padx=(0, 10))
        text_box = tk.Frame(row, bg=self.colors["charcoal"])
        text_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            text_box,
            text=title,
            bg=self.colors["charcoal"],
            fg="#f4efe6",
            font=("Microsoft YaHei UI", 10, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            text_box,
            text=desc,
            bg=self.colors["charcoal"],
            fg="#bcb4a8",
            font=("Microsoft YaHei UI", 8),
            wraplength=190,
            justify=tk.LEFT,
        ).pack(anchor=tk.W, pady=(2, 0))

    def enqueue(self, kind, value=None):
        self.queue.put((kind, value))

    def poll_queue(self):
        try:
            while True:
                kind, value = self.queue.get_nowait()
                if kind == "log":
                    self.log(value)
                elif kind == "scan_done":
                    self.scan_done(value)
                elif kind == "fix_done":
                    self.fix_done(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll_queue)

    def log(self, message):
        stamp = time.strftime("%H:%M:%S")
        self.log_lines.append("[{}] {}".format(stamp, message))
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, "[{}] {}\n".format(stamp, message))
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def update_tree(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.items:
            self.tree.insert("", tk.END, values=(item["name"], item["path"], item["source"]))
        self.status_var.set("当前列表：{} 个 KeyShot 安装目录。".format(len(self.items)))

    def merge_items(self, new_items):
        existing = {os.path.normcase(os.path.normpath(item["path"])) for item in self.items}
        added = 0
        for item in new_items:
            key = os.path.normcase(os.path.normpath(item["path"]))
            if key not in existing:
                self.items.append(item)
                existing.add(key)
                added += 1
        self.items.sort(key=lambda item: item["path"].lower())
        return added

    def set_busy(self, busy):
        self.worker_running = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.scan_btn.config(state=state)
        self.add_btn.config(state=state)
        self.remove_btn.config(state=state)
        self.fix_selected_btn.config(state=state)
        self.diagnose_btn.config(state=state)
        self.report_btn.config(state=state)
        self.backup_btn.config(state=state)
        self.cache_btn.config(state=state)
        self.fix_btn.config(state=state)

    def scan_versions(self):
        if self.worker_running:
            return
        self.set_busy(True)
        module_key = self.current_module_key()
        self.status_var.set("正在扫描 {} 安装目录...".format(self.module_label()))
        self.log("开始自动扫描：{}。".format(self.module_label()))

        def worker():
            if module_key == "rhino":
                result = scan_rhino_installations()
            else:
                result = scan_keyshot_installations()
            self.enqueue("scan_done", result)

        threading.Thread(target=worker, daemon=True).start()

    def scan_done(self, result):
        added = self.merge_items(result)
        self.update_tree()
        self.log("扫描完成，新增 {} 个目录。".format(added))
        if not self.items:
            self.log("没有自动找到 {}。请点击“手动添加”，选择安装根目录。".format(self.module_label()))
        self.set_busy(False)

    def add_path(self):
        module_key = self.current_module_key()
        path = filedialog.askdirectory(title="选择 {} 安装根目录".format(self.module_label()))
        if not path:
            return
        if module_key == "rhino":
            install_path = normalize_rhino_install_path(path)
            dll_path = os.path.join(install_path, "System", RHINO_DLL_NAME) if install_path else ""
        else:
            install_path = normalize_keyshot_install_path(path)
            dll_path = os.path.join(install_path, "bin", KEYSHOT_DLL_NAME) if install_path else ""
        if not install_path:
            expected = "System\\{}".format(RHINO_DLL_NAME) if module_key == "rhino" else "bin\\{}".format(KEYSHOT_DLL_NAME)
            messagebox.showerror("路径无效", "所选目录下没有找到 {}，请选择正确的安装根目录。".format(expected))
            return
        item = {
            "name": make_display_name(install_path),
            "path": install_path,
            "source": "手动添加",
            "dll": dll_path,
            "module": module_key,
        }
        added = self.merge_items([item])
        self.update_tree()
        if added:
            self.log("已手动添加：{}".format(install_path))
        else:
            messagebox.showinfo("已存在", "该路径已经在列表中。")

    def delete_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("请选择", "请先在列表中选中一个 KeyShot 目录。")
            return
        selected_paths = {self.tree.item(item, "values")[1] for item in selected}
        self.items = [item for item in self.items if item["path"] not in selected_paths]
        self.update_tree()
        self.log("已删除选中项。")

    def fix_all(self):
        self.fix_items(self.items, "全部")

    def fix_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("请选择", "请先选中你常用或最新的 KeyShot 版本。")
            return
        selected_paths = {self.tree.item(item, "values")[1] for item in selected}
        items = [item for item in self.items if item["path"] in selected_paths]
        self.fix_items(items, "选中")

    def fix_items(self, items, label):
        if self.worker_running:
            return
        if not items:
            messagebox.showwarning("列表为空", "请先自动扫描或手动添加 KeyShot 安装目录。")
            return
        if not is_admin():
            messagebox.showerror(APP_TITLE, "当前不是管理员权限，请重新打开工具并允许管理员授权。")
            return

        self.set_busy(True)
        module_key = self.current_module_key()
        self.status_var.set("正在注册 {} 预览组件...".format(self.module_label()))
        self.log("开始修复{}项目：{}，共 {} 个目录。".format(label, self.module_label(), len(items)))
        try:
            backup_path = save_registry_backup(module_key)
            self.log("已自动备份关键注册表信息：{}".format(backup_path))
        except Exception as exc:
            self.log("注册表备份失败，但修复仍继续：{}".format(exc))

        def worker():
            success = 0
            total = len(items)
            for index, item in enumerate(items, start=1):
                self.enqueue("log", "({}/{}) 正在处理：{}".format(index, total, item["path"]))
                ok, message = register_preview_dll(item["dll"])
                if ok:
                    success += 1
                    self.enqueue("log", "成功：" + message)
                else:
                    self.enqueue("log", "失败：" + message)
            if module_key == "keyshot":
                ok, message = ensure_bip_file_association()
                self.enqueue("log", ("成功：" if ok else "失败：") + message)
            else:
                refresh_shell_associations()
                self.enqueue("log", "已刷新 Windows Shell 文件关联。Rhino 的 .3dm 关联通常由 RhinoHandlers.dll 注册时写入。")
            active = get_active_handler_info(module_key)
            extension = MODULES[module_key]["extension"]
            self.enqueue("log", "HKCR {} 类型：{}".format(extension, active["prog_id"]))
            self.enqueue("log", "用户默认打开方式：{}".format(active["user_choice"]))
            self.enqueue("log", "资源管理器实际使用类型：{}".format(active["active_prog_id"]))
            self.enqueue("log", "当前图标处理器：{}".format(active["icon_handler"]))
            self.enqueue("log", "当前缩略图处理器：{}".format(active["thumbnail_handler"]))
            self.enqueue("log", "当前生效 DLL：{}".format(active["inproc"]))
            self.enqueue("fix_done", {"success": success, "total": total})

        threading.Thread(target=worker, daemon=True).start()

    def diagnose_association(self):
        try:
            module_key = self.current_module_key()
            extension = MODULES[module_key]["extension"]
            active = get_active_handler_info(module_key)
            self.log("HKCR {} 类型：{}".format(extension, active["prog_id"]))
            self.log("用户默认打开方式：{}".format(active["user_choice"]))
            self.log("资源管理器实际使用类型：{}".format(active["active_prog_id"]))
            self.log("当前图标处理器：{}".format(active["icon_handler"]))
            self.log("当前缩略图处理器：{}".format(active["thumbnail_handler"]))
            self.log("当前生效 DLL：{}".format(active["inproc"]))
            messagebox.showinfo(
                APP_TITLE,
                "当前模块：{}\nHKCR {} 类型：{}\n用户默认打开方式：{}\n资源管理器实际使用类型：{}\n当前图标处理器：{}\n当前缩略图处理器：{}\n当前生效 DLL：{}".format(
                    self.module_label(),
                    extension,
                    active["prog_id"],
                    active["user_choice"],
                    active["active_prog_id"],
                    active["icon_handler"],
                    active["thumbnail_handler"],
                    active["inproc"],
                ),
            )
        except Exception as exc:
            self.log("诊断失败：" + str(exc))
            messagebox.showerror(APP_TITLE, "诊断失败：" + str(exc))

    def export_report(self):
        try:
            path = export_diagnostic_report(self.current_module_key(), self.items, self.log_lines)
            self.log("已导出诊断报告：{}".format(path))
            messagebox.showinfo(APP_TITLE, "诊断报告已导出：\n{}".format(path))
        except Exception as exc:
            self.log("导出诊断报告失败：" + str(exc))
            messagebox.showerror(APP_TITLE, "导出诊断报告失败：" + str(exc))

    def backup_registry(self):
        try:
            path = save_registry_backup(self.current_module_key())
            self.log("已备份关键注册表信息：{}".format(path))
            messagebox.showinfo(APP_TITLE, "注册表备份已保存：\n{}".format(path))
        except Exception as exc:
            self.log("备份注册表失败：" + str(exc))
            messagebox.showerror(APP_TITLE, "备份注册表失败：" + str(exc))

    def clear_cache(self):
        if self.worker_running:
            return
        if not messagebox.askyesno(
            APP_TITLE,
            "将关闭并重启 Windows 资源管理器，同时清理缩略图缓存。\n\n桌面和文件夹窗口会闪一下，是否继续？",
        ):
            return
        self.set_busy(True)
        self.status_var.set("正在清理缩略图缓存并重启资源管理器...")
        self.log("开始清理 Windows 缩略图缓存。")

        def worker():
            ok, message = clear_thumbnail_cache_and_restart_explorer()
            self.enqueue("log", ("成功：" if ok else "失败：") + message)
            self.enqueue("fix_done", {"success": 1 if ok else 0, "total": 1, "cache": True})

        threading.Thread(target=worker, daemon=True).start()

    def fix_done(self, result):
        success = result["success"]
        total = result["total"]
        if result.get("cache"):
            self.status_var.set("缓存清理完成。" if success else "缓存清理失败，请查看日志。")
            self.set_busy(False)
            if success:
                messagebox.showinfo(APP_TITLE, "已清理缓存并重启资源管理器。请重新打开包含 .bip 的文件夹查看缩略图。")
            else:
                messagebox.showwarning(APP_TITLE, "缓存清理失败，请查看下方日志。")
            return
        self.log("修复完成：成功 {}/{}。".format(success, total))
        self.status_var.set("修复完成：成功 {}/{}。".format(success, total))
        self.set_busy(False)
        if success == total:
            messagebox.showinfo(APP_TITLE, "修复完成。下一步请点击“清缓存并重启资源管理器”，再重新打开包含 .bip 的文件夹查看预览图。")
        else:
            messagebox.showwarning(APP_TITLE, "部分目录修复失败，请查看下方日志。")


def main():
    relaunch_as_admin()
    root = tk.Tk()
    app = FixerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()








