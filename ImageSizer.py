# -*- coding: utf-8 -*-
"""
ImageSizer XP - JPG 专用版

功能：
1. 只支持 JPG / JPEG
2. Windows XP SP3 32 位兼容
3. 不使用 Pillow，使用 Windows GDI+
4. 支持拖拽、批量处理
5. 保持原图像素尺寸，绝不缩放
6. 自动调整 JPEG Quality
7. 输出文件实际大小严格 <= 用户输入的 KB
"""

import os
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ============================================================
# Windows / GDI+
# ============================================================

gdiplus = ctypes.windll.gdiplus
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32


class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", ctypes.c_bool),
        ("SuppressExternalCodecs", ctypes.c_bool),
    ]


class EncoderParameter(ctypes.Structure):
    _fields_ = [
        ("Guid", ctypes.c_ubyte * 16),
        ("NumberOfValues", ctypes.c_ulong),
        ("Type", ctypes.c_ulong),
        ("Value", ctypes.c_void_p),
    ]


class EncoderParameters(ctypes.Structure):
    _fields_ = [
        ("Count", ctypes.c_uint),
        ("Parameter", EncoderParameter * 1),
    ]


PixelFormat24bppRGB = 0x00021808
InterpolationModeHighQualityBicubic = 7
SmoothingModeHighQuality = 4
CompositingQualityHighQuality = 4

# JPEG Encoder CLSID
JPEG_ENCODER_CLSID = (
    0x01, 0xF4, 0x7C, 0x55,
    0x04, 0x1A,
    0xD3, 0x11,
    0x9A, 0x73,
    0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E
)

# Encoder Quality GUID
QUALITY_GUID = (
    0xB5, 0xE4, 0x5B, 0x1D,
    0x4A, 0xFA,
    0x2D, 0x45,
    0x9C, 0xDD,
    0x5D, 0xB3, 0x51, 0x05, 0xE7, 0xEB
)

gdiplus_token = ctypes.c_void_p()


def guid_bytes(values):
    arr = (ctypes.c_ubyte * 16)()
    for i in range(16):
        arr[i] = values[i]
    return arr


def gdiplus_init():
    global gdiplus_token

    startup = GdiplusStartupInput()
    startup.GdiplusVersion = 1

    status = gdiplus.GdiplusStartup(
        ctypes.byref(gdiplus_token),
        ctypes.byref(startup),
        None
    )

    if status != 0:
        raise RuntimeError(
            "Windows GDI+ 初始化失败，错误代码：{}".format(status)
        )


def gdiplus_shutdown():
    global gdiplus_token

    if gdiplus_token:
        gdiplus.GdiplusShutdown(gdiplus_token)
        gdiplus_token = ctypes.c_void_p()


# ============================================================
# GDI+ API
# ============================================================

gdiplus.GdipLoadImageFromFile.argtypes = [
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_void_p)
]
gdiplus.GdipLoadImageFromFile.restype = ctypes.c_int

gdiplus.GdipGetImageWidth.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint)
]
gdiplus.GdipGetImageWidth.restype = ctypes.c_int

gdiplus.GdipGetImageHeight.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint)
]
gdiplus.GdipGetImageHeight.restype = ctypes.c_int

gdiplus.GdipCreateBitmapFromScan0.argtypes = [
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
]
gdiplus.GdipCreateBitmapFromScan0.restype = ctypes.c_int

gdiplus.GdipGetImageGraphicsContext.argtypes = [
    ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)
]
gdiplus.GdipGetImageGraphicsContext.restype = ctypes.c_int

gdiplus.GdipSetInterpolationMode.argtypes = [
    ctypes.c_void_p, ctypes.c_int
]
gdiplus.GdipSetInterpolationMode.restype = ctypes.c_int

gdiplus.GdipSetSmoothingMode.argtypes = [
    ctypes.c_void_p, ctypes.c_int
]
gdiplus.GdipSetSmoothingMode.restype = ctypes.c_int

gdiplus.GdipSetCompositingQuality.argtypes = [
    ctypes.c_void_p, ctypes.c_int
]
gdiplus.GdipSetCompositingQuality.restype = ctypes.c_int

gdiplus.GdipDrawImageRectI.argtypes = [
    ctypes.c_void_p, ctypes.c_void_p,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int
]
gdiplus.GdipDrawImageRectI.restype = ctypes.c_int

gdiplus.GdipSaveImageToFile.argtypes = [
    ctypes.c_void_p, ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_ubyte), ctypes.c_void_p
]
gdiplus.GdipSaveImageToFile.restype = ctypes.c_int

gdiplus.GdipDeleteGraphics.argtypes = [ctypes.c_void_p]
gdiplus.GdipDisposeImage.argtypes = [ctypes.c_void_p]


# ============================================================
# 图片尺寸
# ============================================================

def get_image_size(filename):
    image = ctypes.c_void_p()

    status = gdiplus.GdipLoadImageFromFile(
        ctypes.c_wchar_p(filename),
        ctypes.byref(image)
    )

    if status != 0:
        raise RuntimeError(
            "无法打开 JPG 文件，GDI+ 错误代码：{}".format(status)
        )

    try:
        width = ctypes.c_uint()
        height = ctypes.c_uint()

        if gdiplus.GdipGetImageWidth(
            image, ctypes.byref(width)
        ) != 0:
            raise RuntimeError("无法读取图片宽度。")

        if gdiplus.GdipGetImageHeight(
            image, ctypes.byref(height)
        ) != 0:
            raise RuntimeError("无法读取图片高度。")

        return width.value, height.value

    finally:
        gdiplus.GdipDisposeImage(image)


# ============================================================
# JPEG 保存
# ============================================================

def save_jpeg(image, filename, quality):
    quality_value = ctypes.c_ulong(int(quality))
    parameter = EncoderParameter()

    guid = guid_bytes(QUALITY_GUID)

    for i in range(16):
        parameter.Guid[i] = guid[i]

    parameter.NumberOfValues = 1
    parameter.Type = 4
    parameter.Value = ctypes.cast(
        ctypes.pointer(quality_value),
        ctypes.c_void_p
    )

    parameters = EncoderParameters()
    parameters.Count = 1
    parameters.Parameter[0] = parameter

    status = gdiplus.GdipSaveImageToFile(
        image,
        ctypes.c_wchar_p(filename),
        guid_bytes(JPEG_ENCODER_CLSID),
        ctypes.byref(parameters)
    )

    if status != 0:
        raise RuntimeError(
            "保存 JPEG 失败，GDI+ 错误代码：{}".format(status)
        )


# ============================================================
# 保持原始像素尺寸重新编码
# ============================================================

def save_same_size(src, dst, width, height, quality):
    source = ctypes.c_void_p()
    target = ctypes.c_void_p()
    graphics = ctypes.c_void_p()

    try:
        status = gdiplus.GdipLoadImageFromFile(
            ctypes.c_wchar_p(src),
            ctypes.byref(source)
        )

        if status != 0:
            raise RuntimeError(
                "无法打开图片，GDI+ 错误代码：{}".format(status)
            )

        status = gdiplus.GdipCreateBitmapFromScan0(
            width, height, 0, PixelFormat24bppRGB,
            None, ctypes.byref(target)
        )

        if status != 0:
            raise RuntimeError(
                "创建目标图片失败，GDI+ 错误代码：{}".format(status)
            )

        status = gdiplus.GdipGetImageGraphicsContext(
            target, ctypes.byref(graphics)
        )

        if status != 0:
            raise RuntimeError(
                "创建绘图环境失败，GDI+ 错误代码：{}".format(status)
            )

        gdiplus.GdipSetInterpolationMode(
            graphics, InterpolationModeHighQualityBicubic
        )
        gdiplus.GdipSetSmoothingMode(
            graphics, SmoothingModeHighQuality
        )
        gdiplus.GdipSetCompositingQuality(
            graphics, CompositingQualityHighQuality
        )

        status = gdiplus.GdipDrawImageRectI(
            graphics, source, 0, 0, width, height
        )

        if status != 0:
            raise RuntimeError(
                "图片处理失败，GDI+ 错误代码：{}".format(status)
            )

        save_jpeg(target, dst, quality)

    finally:
        if graphics:
            gdiplus.GdipDeleteGraphics(graphics)
        if target:
            gdiplus.GdipDisposeImage(target)
        if source:
            gdiplus.GdipDisposeImage(source)


# ============================================================
# 硬性 KB 限制
# ============================================================

def compress_image(src, dst, max_kb):
    width, height = get_image_size(src)

    # 直接使用用户输入的 KB × 1024 作为真实字节上限。
    target_bytes = int(max_kb) * 1024
    temp_file = dst + ".tmp.jpg"

    def remove_temp():
        if os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                pass

    try:
        # 二分寻找在原始像素尺寸下能够满足大小限制的最高质量。
        low = 1
        high = 95
        best_quality = None
        best_size = None

        while low <= high:
            quality = (low + high) // 2

            remove_temp()
            save_same_size(
                src, temp_file, width, height, quality
            )

            actual_size = os.path.getsize(temp_file)

            if actual_size <= target_bytes:
                best_quality = quality
                best_size = actual_size
                low = quality + 1
            else:
                high = quality - 1

        if best_quality is None:
            raise RuntimeError(
                "保持原图 {}×{} 像素时，即使 JPEG Quality=1，"
                "仍无法压缩到 {} KB。"
                .format(width, height, max_kb)
            )

        # 最终重新生成并进行两次硬性验证。
        remove_temp()
        save_same_size(
            src, temp_file, width, height, best_quality
        )

        final_size = os.path.getsize(temp_file)

        if final_size > target_bytes:
            raise RuntimeError(
                "最终文件超过 {} KB，已拒绝输出。"
                .format(max_kb)
            )

        if os.path.exists(dst):
            try:
                os.remove(dst)
            except Exception:
                pass

        os.rename(temp_file, dst)

        # 移动后再次检查实际字节数。
        verified_size = os.path.getsize(dst)

        if verified_size > target_bytes:
            try:
                os.remove(dst)
            except Exception:
                pass

            raise RuntimeError(
                "最终文件实际大小超过 {} KB，已删除超限文件。"
                .format(max_kb)
            )

        return width, height, best_quality, verified_size

    finally:
        remove_temp()


# ============================================================
# Windows 原生拖拽
# ============================================================

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_size_t,
    ctypes.c_size_t
)


class NativeDropHandler(object):

    def __init__(self, widgets, callback):
        self.callback = callback
        self.old_procs = []
        self.procs = []

        for widget in widgets:
            hwnd = widget.winfo_id()
            proc = _WNDPROC(self._wnd_proc)

            old_proc = user32.SetWindowLongW(
                hwnd,
                GWL_WNDPROC,
                ctypes.cast(proc, ctypes.c_void_p).value
            )

            self.procs.append(proc)
            self.old_procs.append((hwnd, old_proc))

            shell32.DragAcceptFiles(hwnd, True)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                self._read_files(wparam)
            finally:
                shell32.DragFinish(wparam)
            return 0

        old_proc = 0
        for old_hwnd, proc in self.old_procs:
            if old_hwnd == hwnd:
                old_proc = proc
                break

        return user32.CallWindowProcW(
            old_proc, hwnd, msg, wparam, lparam
        )

    def _read_files(self, hdrop):
        count = shell32.DragQueryFileW(
            hdrop, 0xFFFFFFFF, None, 0
        )

        files = []

        for i in range(count):
            length = shell32.DragQueryFileW(
                hdrop, i, None, 0
            )

            buffer = ctypes.create_unicode_buffer(length + 1)

            shell32.DragQueryFileW(
                hdrop, i, buffer, length + 1
            )

            files.append(buffer.value)

        if files:
            self.callback(files)


# ============================================================
# GUI
# ============================================================

class App(object):

    def __init__(self, root):
        self.root = root
        self.root.title("ImageSizer XP - JPG 图片压缩工具")
        self.root.geometry("720x560")
        self.root.minsize(650, 500)

        self.files = []
        self.max_kb = tk.StringVar(value="500")
        self.out_dir = tk.StringVar()
        self.status = tk.StringVar(value="等待添加 JPG 图片")
        self.progress = tk.DoubleVar(value=0)

        self.build_ui()

        try:
            self.drop_handler = NativeDropHandler(
                [self.root, self.drop],
                self.add_files
            )
        except Exception:
            self.drop_handler = None
            self.status.set(
                "拖拽功能初始化失败，可使用“选择图片”"
            )

    def build_ui(self):
        style = ttk.Style()

        try:
            style.theme_use("vista")
        except Exception:
            pass

        frame = ttk.Frame(self.root, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="ImageSizer XP",
            font=("Segoe UI", 20, "bold")
        ).pack(anchor="w")

        ttk.Label(
            frame,
            text="JPG 专用 · 保持原始像素，只压缩文件大小"
        ).pack(anchor="w", pady=(2, 12))

        settings = ttk.LabelFrame(
            frame, text="文件大小限制", padding=12
        )
        settings.pack(fill="x")

        ttk.Label(
            settings,
            text="最大文件大小（KB）"
        ).pack(side="left")

        ttk.Entry(
            settings,
            textvariable=self.max_kb,
            width=14
        ).pack(side="left", padx=10)

        ttk.Label(
            settings,
            text="原图像素不会改变"
        ).pack(side="left")

        self.drop = tk.Text(
            frame,
            height=12,
            relief="groove",
            borderwidth=1,
            font=("Segoe UI", 10)
        )
        self.drop.pack(fill="both", expand=True, pady=14)

        self.drop.insert(
            "1.0",
            "把 JPG / JPEG 图片拖到这里\n\n"
            "添加后会显示原始像素尺寸。"
        )
        self.drop.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        ttk.Button(
            buttons,
            text="选择图片",
            command=self.choose_files
        ).pack(side="left")

        ttk.Button(
            buttons,
            text="清空",
            command=self.clear_files
        ).pack(side="left", padx=8)

        ttk.Button(
            buttons,
            text="开始压缩",
            command=self.start
        ).pack(side="right")

        output = ttk.Frame(frame)
        output.pack(fill="x", pady=(12, 0))

        ttk.Label(
            output,
            text="输出目录："
        ).pack(side="left")

        ttk.Entry(
            output,
            textvariable=self.out_dir
        ).pack(side="left", fill="x", expand=True, padx=6)

        ttk.Button(
            output,
            text="浏览",
            command=self.choose_dir
        ).pack(side="right")

        ttk.Progressbar(
            frame,
            variable=self.progress,
            maximum=100
        ).pack(fill="x", pady=(12, 4))

        ttk.Label(
            frame,
            textvariable=self.status
        ).pack(anchor="w")

    def choose_files(self):
        files = filedialog.askopenfilenames(
            title="选择 JPG 图片",
            filetypes=[
                ("JPG 图片", "*.jpg *.jpeg"),
                ("所有文件", "*.*")
            ]
        )
        self.add_files(files)

    def add_files(self, files):
        added = 0

        for filename in files:
            filename = str(filename)

            if not os.path.isfile(filename):
                continue

            if os.path.splitext(filename)[1].lower() not in (
                ".jpg", ".jpeg"
            ):
                continue

            if filename not in self.files:
                self.files.append(filename)
                added += 1

        self.refresh_file_list()

        if added:
            self.status.set(
                "已添加 {} 张 JPG 图片".format(len(self.files))
            )
        else:
            self.status.set("没有新增 JPG 图片")

    def refresh_file_list(self):
        self.drop.configure(state="normal")
        self.drop.delete("1.0", "end")

        if self.files:
            self.drop.insert(
                "1.0",
                "已添加 {} 张 JPG 图片\n\n".format(
                    len(self.files)
                )
            )

            for i, filename in enumerate(self.files, 1):
                try:
                    width, height = get_image_size(filename)
                    size_kb = os.path.getsize(filename) / 1024.0
                    line = "{}. {}   [{}×{}]   {:.1f} KB\n".format(
                        i,
                        os.path.basename(filename),
                        width,
                        height,
                        size_kb
                    )
                except Exception:
                    line = "{}. {}   [无法读取]\n".format(
                        i,
                        os.path.basename(filename)
                    )

                self.drop.insert("end", line)
        else:
            self.drop.insert(
                "1.0",
                "把 JPG / JPEG 图片拖到这里\n\n"
                "添加后会显示原始像素尺寸。"
            )

        self.drop.configure(state="disabled")

    def clear_files(self):
        self.files[:] = []
        self.refresh_file_list()
        self.progress.set(0)
        self.status.set("等待添加 JPG 图片")

    def choose_dir(self):
        directory = filedialog.askdirectory(
            title="选择输出目录"
        )

        if directory:
            self.out_dir.set(directory)

    def start(self):
        if not self.files:
            messagebox.showwarning(
                "提示",
                "请先添加 JPG 图片。"
            )
            return

        try:
            max_kb = int(self.max_kb.get())

            if max_kb < 1:
                raise ValueError

        except ValueError:
            messagebox.showerror(
                "参数错误",
                "最大文件大小必须是正整数。"
            )
            return

        if self.out_dir.get():
            output_dir = self.out_dir.get()
        else:
            output_dir = os.path.join(
                os.path.dirname(self.files[0]),
                "ImageSizer_Output"
            )

        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
            except Exception as e:
                messagebox.showerror(
                    "错误",
                    "无法创建输出目录：\n{}\n\n{}".format(
                        output_dir, e
                    )
                )
                return

        self.progress.set(0)
        self.status.set("开始压缩...")

        threading.Thread(
            target=self.worker,
            args=(max_kb, output_dir)
        ).start()

    def worker(self, max_kb, output_dir):
        success = 0
        errors = []
        total = len(self.files)

        for index, src in enumerate(self.files, 1):
            try:
                filename = os.path.splitext(
                    os.path.basename(src)
                )[0]

                dst = os.path.join(
                    output_dir,
                    filename + "_compressed.jpg"
                )

                width, height, quality, size = compress_image(
                    src, dst, max_kb
                )

                success += 1

                self.root.after(
                    0,
                    lambda index=index,
                    width=width,
                    height=height,
                    quality=quality,
                    size=size:
                    self.status.set(
                        "{}/{}：{}×{}，Quality {}，{:.1f} KB".format(
                            index,
                            total,
                            width,
                            height,
                            quality,
                            size / 1024.0
                        )
                    )
                )

            except Exception as e:
                errors.append(
                    "{}: {}".format(
                        os.path.basename(src), e
                    )
                )

            progress = index / float(total) * 100

            self.root.after(
                0,
                lambda progress=progress:
                self.progress.set(progress)
            )

        message = (
            "完成：{}/{} 张\n\n"
            "输出目录：{}".format(
                success, total, output_dir
            )
        )

        if errors:
            message += (
                "\n\n失败文件：\n" +
                "\n".join(errors[:10])
            )

            if len(errors) > 10:
                message += "\n……还有 {} 个文件失败".format(
                    len(errors) - 10
                )

        self.root.after(
            0,
            lambda message=message:
            messagebox.showinfo(
                "处理完成", message
            )
        )

        self.root.after(
            0,
            lambda success=success, total=total:
            self.status.set(
                "完成：{}/{} 张".format(success, total)
            )
        )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":
    try:
        gdiplus_init()

        root = tk.Tk()
        app = App(root)

        root.protocol(
            "WM_DELETE_WINDOW",
            lambda: (
                gdiplus_shutdown(),
                root.destroy()
            )
        )

        root.mainloop()

    except Exception as e:
        try:
            messagebox.showerror(
                "ImageSizer 启动错误",
                str(e)
            )
        except Exception:
            pass

        try:
            gdiplus_shutdown()
        except Exception:
            pass
