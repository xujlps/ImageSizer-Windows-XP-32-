# -*- coding: utf-8 -*-

"""
ImageSizer XP JPG 专用版

功能：
1. 只支持 JPG / JPEG
2. Windows XP SP3 32位兼容
3. 不使用 Pillow
4. 使用 Windows GDI+ 处理图片
5. 支持拖拽 JPG
6. 支持批量压缩
7. 支持最大宽度
8. 支持最大高度
9. 支持最大文件大小 KB
10. 自动寻找合适 JPEG Quality
"""

import os
import io
import ctypes
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ============================================================
# Windows / GDI+
# ============================================================

gdi32 = ctypes.windll.gdi32
gdiplus = ctypes.windll.gdiplus
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
kernel32 = ctypes.windll.kernel32


# ============================================================
# GDI+ 基础结构
# ============================================================

class GdiplusStartupInput(ctypes.Structure):
    _fields_ = [
        ("GdiplusVersion", ctypes.c_uint32),
        ("DebugEventCallback", ctypes.c_void_p),
        ("SuppressBackgroundThread", ctypes.c_bool),
        ("SuppressExternalCodecs", ctypes.c_bool),
    ]


class Rect(ctypes.Structure):
    _fields_ = [
        ("X", ctypes.c_int),
        ("Y", ctypes.c_int),
        ("Width", ctypes.c_int),
        ("Height", ctypes.c_int),
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


# ============================================================
# GDI+ 常量
# ============================================================

PixelFormat24bppRGB = 0x00021808

ImageLockModeRead = 0x0001
ImageLockModeWrite = 0x0002

UnitPixel = 2

InterpolationModeHighQualityBicubic = 7
SmoothingModeHighQuality = 4
CompositingQualityHighQuality = 4


# JPEG Encoder CLSID
# {557CF401-1A04-11D3-9A73-0000F81EF32E}
JPEG_ENCODER_CLSID = (
    0x01, 0xF4, 0x7C, 0x55,
    0x04, 0x1A,
    0xD3, 0x11,
    0x9A, 0x73,
    0x00, 0x00, 0xF8, 0x1E, 0xF3, 0x2E
)

# Encoder Quality GUID
# {1D5BE4B5-FA4A-452D-9CDD-5DB35105E7EB}
QUALITY_GUID = (
    0xB5, 0xE4, 0x5B, 0x1D,
    0x4A, 0xFA,
    0x2D, 0x45,
    0x9C, 0xDD,
    0x5D, 0xB3, 0x51, 0x05, 0xE7, 0xEB
)


# ============================================================
# GDI+ 初始化
# ============================================================

gdiplus_token = ctypes.c_void_p()


def gdiplus_init():
    global gdiplus_token

    startup_input = GdiplusStartupInput()
    startup_input.GdiplusVersion = 1
    startup_input.DebugEventCallback = None
    startup_input.SuppressBackgroundThread = False
    startup_input.SuppressExternalCodecs = False

    status = gdiplus.GdiplusStartup(
        ctypes.byref(gdiplus_token),
        ctypes.byref(startup_input),
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
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p)
]
gdiplus.GdipCreateBitmapFromScan0.restype = ctypes.c_int

gdiplus.GdipGetImageGraphicsContext.argtypes = [
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p)
]
gdiplus.GdipGetImageGraphicsContext.restype = ctypes.c_int

gdiplus.GdipGraphicsClear.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint
]
gdiplus.GdipGraphicsClear.restype = ctypes.c_int

gdiplus.GdipSetInterpolationMode.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int
]
gdiplus.GdipSetInterpolationMode.restype = ctypes.c_int

gdiplus.GdipSetSmoothingMode.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int
]
gdiplus.GdipSetSmoothingMode.restype = ctypes.c_int

gdiplus.GdipSetCompositingQuality.argtypes = [
    ctypes.c_void_p,
    ctypes.c_int
]
gdiplus.GdipSetCompositingQuality.restype = ctypes.c_int

gdiplus.GdipDrawImageRectI.argtypes = [
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int
]
gdiplus.GdipDrawImageRectI.restype = ctypes.c_int

gdiplus.GdipSaveImageToFile.argtypes = [
    ctypes.c_void_p,
    ctypes.c_wchar_p,
    ctypes.POINTER(ctypes.c_ubyte),
    ctypes.c_void_p
]
gdiplus.GdipSaveImageToFile.restype = ctypes.c_int

gdiplus.GdipDeleteGraphics.argtypes = [
    ctypes.c_void_p
]
gdiplus.GdipDeleteGraphics.restype = ctypes.c_int

gdiplus.GdipDisposeImage.argtypes = [
    ctypes.c_void_p
]
gdiplus.GdipDisposeImage.restype = ctypes.c_int


# ============================================================
# GUID 转换
# ============================================================

def guid_bytes(values):
    arr = (ctypes.c_ubyte * 16)()
    for i in range(16):
        arr[i] = values[i]
    return arr


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

    encoder_clsid = guid_bytes(JPEG_ENCODER_CLSID)

    status = gdiplus.GdipSaveImageToFile(
        image,
        ctypes.c_wchar_p(filename),
        encoder_clsid,
        ctypes.byref(parameters)
    )

    if status != 0:
        raise RuntimeError(
            "保存 JPEG 失败，GDI+ 错误代码：{}".format(status)
        )


# ============================================================
# 获取图片尺寸
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

        status = gdiplus.GdipGetImageWidth(
            image,
            ctypes.byref(width)
        )

        if status != 0:
            raise RuntimeError("无法读取图片宽度。")

        status = gdiplus.GdipGetImageHeight(
            image,
            ctypes.byref(height)
        )

        if status != 0:
            raise RuntimeError("无法读取图片高度。")

        return width.value, height.value

    finally:
        gdiplus.GdipDisposeImage(image)


# ============================================================
# 计算缩放尺寸
# ============================================================

def fit_size(width, height, max_width, max_height):
    scale_w = float(max_width) / float(width)
    scale_h = float(max_height) / float(height)

    scale = min(scale_w, scale_h, 1.0)

    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))

    return new_width, new_height


# ============================================================
# GDI+ 缩放并保存
# ============================================================

def resize_and_save(src, dst, width, height, quality):
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
            width,
            height,
            0,
            PixelFormat24bppRGB,
            None,
            ctypes.byref(target)
        )

        if status != 0:
            raise RuntimeError(
                "创建目标图片失败，GDI+ 错误代码：{}".format(status)
            )

        status = gdiplus.GdipGetImageGraphicsContext(
            target,
            ctypes.byref(graphics)
        )

        if status != 0:
            raise RuntimeError(
                "创建绘图环境失败，GDI+ 错误代码：{}".format(status)
            )

        gdiplus.GdipSetInterpolationMode(
            graphics,
            InterpolationModeHighQualityBicubic
        )

        gdiplus.GdipSetSmoothingMode(
            graphics,
            SmoothingModeHighQuality
        )

        gdiplus.GdipSetCompositingQuality(
            graphics,
            CompositingQualityHighQuality
        )

        # 白色背景
        gdiplus.GdipGraphicsClear(
            graphics,
            0xFFFFFFFF
        )

        status = gdiplus.GdipDrawImageRectI(
            graphics,
            source,
            0,
            0,
            width,
            height
        )

        if status != 0:
            raise RuntimeError(
                "图片缩放失败，GDI+ 错误代码：{}".format(status)
            )

        save_jpeg(
            target,
            dst,
            quality
        )

    finally:

        if graphics:
            gdiplus.GdipDeleteGraphics(graphics)

        if target:
            gdiplus.GdipDisposeImage(target)

        if source:
            gdiplus.GdipDisposeImage(source)


# ============================================================
# 单张图片压缩
# ============================================================

def compress_image(src, dst, max_width, max_height, max_kb):

    original_width, original_height = get_image_size(src)

    width, height = fit_size(
        original_width,
        original_height,
        max_width,
        max_height
    )

    # ========================================================
    # 硬性文件大小上限
    #
    # 用户输入 500 KB -> 最大允许 512000 bytes
    # 最终输出文件必须满足：
    #     os.path.getsize(dst) <= target_bytes
    #
    # 不采用“显示值四舍五入”判断，而是直接比较真实字节数。
    # ========================================================
    target_bytes = int(max_kb) * 1024

    temp_file = dst + ".tmp.jpg"

    def remove_if_exists(filename):
        if os.path.exists(filename):
            try:
                os.remove(filename)
            except Exception:
                pass

    def save_and_check(test_width, test_height, quality):
        remove_if_exists(temp_file)

        resize_and_save(
            src,
            temp_file,
            test_width,
            test_height,
            quality
        )

        if not os.path.exists(temp_file):
            raise RuntimeError("JPEG 临时文件没有生成。")

        actual_size = os.path.getsize(temp_file)

        return actual_size

    try:

        current_width = width
        current_height = height

        while True:

            # ------------------------------------------------
            # 第一阶段：二分寻找“仍然不超过上限”的最高质量
            # ------------------------------------------------
            low = 10
            high = 95

            best_quality = None
            best_size = None

            while low <= high:

                quality = (low + high) // 2

                current_size = save_and_check(
                    current_width,
                    current_height,
                    quality
                )

                if current_size <= target_bytes:

                    best_quality = quality
                    best_size = current_size

                    # 尝试更高质量
                    low = quality + 1

                else:

                    # 超过上限，降低质量
                    high = quality - 1

            # ------------------------------------------------
            # 第二阶段：极端情况下二分法没有找到结果时，
            # 从 Quality 10 开始逐级尝试。
            #
            # 这样不依赖 JPEG 文件大小与 Quality 严格单调，
            # 进一步提高兼容性。
            # ------------------------------------------------
            if best_quality is None:

                for quality in range(10, 96):

                    current_size = save_and_check(
                        current_width,
                        current_height,
                        quality
                    )

                    if current_size <= target_bytes:

                        best_quality = quality
                        best_size = current_size
                        break

            # ------------------------------------------------
            # 找到了满足大小限制的 JPEG
            # ------------------------------------------------
            if best_quality is not None:

                # 再重新生成一次最终文件。
                # 不直接相信前面的临时结果，最后必须重新检查。
                final_size = save_and_check(
                    current_width,
                    current_height,
                    best_quality
                )

                # 硬性检查：真实字节数必须 <= 用户输入上限。
                if final_size <= target_bytes:

                    # 先删除旧输出，再把已验证合格的临时文件移动过去。
                    if os.path.exists(dst):
                        try:
                            os.remove(dst)
                        except Exception:
                            pass

                    os.rename(
                        temp_file,
                        dst
                    )

                    # 移动后再次读取真实文件大小。
                    # 只有再次通过，才允许返回成功。
                    verified_size = os.path.getsize(dst)

                    if verified_size <= target_bytes:

                        return (
                            current_width,
                            current_height,
                            best_quality,
                            verified_size
                        )

                    # 理论上不会发生。
                    # 如果发生，绝不保留超限文件。
                    try:
                        os.remove(dst)
                    except Exception:
                        pass

                    raise RuntimeError(
                        "最终 JPEG 文件超过用户设置的 {} KB，"
                        "已拒绝输出超限文件。".format(
                            max_kb
                        )
                    )

            # ------------------------------------------------
            # 当前尺寸即使 Quality=10 也无法满足大小限制。
            # 必须降低分辨率。
            # ------------------------------------------------
            new_width = int(current_width * 0.90)
            new_height = int(current_height * 0.90)

            # 至少缩小 1 像素，防止整数取整后尺寸不变。
            if new_width >= current_width:
                new_width = current_width - 1

            if new_height >= current_height:
                new_height = current_height - 1

            # 防止进入 0 或负数。
            new_width = max(1, new_width)
            new_height = max(1, new_height)

            # 如果已经无法继续缩小，最后一次用 Quality=10
            # 做严格检查；如果仍超限，则明确失败。
            if (
                new_width < 1
                or new_height < 1
                or (
                    new_width == current_width
                    and new_height == current_height
                )
            ):

                raise RuntimeError(
                    "目标文件大小过小，无法满足 {} KB。".format(
                        max_kb
                    )
                )

            current_width = new_width
            current_height = new_height

    finally:

        # 无论成功还是失败，都不留下 .tmp.jpg。
        remove_if_exists(temp_file)


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

            proc = _WNDPROC(
                self._wnd_proc
            )

            old_proc = user32.SetWindowLongW(
                hwnd,
                GWL_WNDPROC,
                ctypes.cast(
                    proc,
                    ctypes.c_void_p
                ).value
            )

            self.procs.append(proc)
            self.old_procs.append(
                (hwnd, old_proc)
            )

            shell32.DragAcceptFiles(
                hwnd,
                True
            )

    def _wnd_proc(
        self,
        hwnd,
        msg,
        wparam,
        lparam
    ):

        if msg == WM_DROPFILES:

            try:
                self._read_files(wparam)

            finally:
                shell32.DragFinish(
                    wparam
                )

            return 0

        old_proc = 0

        for old_hwnd, proc in self.old_procs:

            if old_hwnd == hwnd:
                old_proc = proc
                break

        return user32.CallWindowProcW(
            old_proc,
            hwnd,
            msg,
            wparam,
            lparam
        )

    def _read_files(self, hdrop):

        count = shell32.DragQueryFileW(
            hdrop,
            0xFFFFFFFF,
            None,
            0
        )

        files = []

        for i in range(count):

            length = shell32.DragQueryFileW(
                hdrop,
                i,
                None,
                0
            )

            buffer = ctypes.create_unicode_buffer(
                length + 1
            )

            shell32.DragQueryFileW(
                hdrop,
                i,
                buffer,
                length + 1
            )

            files.append(
                buffer.value
            )

        if files:
            self.callback(files)


# ============================================================
# GUI
# ============================================================

class App(object):

    def __init__(self, root):

        self.root = root

        self.root.title(
            "ImageSizer XP - JPG 图片压缩工具"
        )

        self.root.geometry(
            "720x560"
        )

        self.root.minsize(
            650,
            500
        )

        self.files = []

        self.max_w = tk.StringVar(
            value="1920"
        )

        self.max_h = tk.StringVar(
            value="1920"
        )

        self.max_kb = tk.StringVar(
            value="500"
        )

        self.out_dir = tk.StringVar()

        self.status = tk.StringVar(
            value="等待添加 JPG 图片"
        )

        self.progress = tk.DoubleVar(
            value=0
        )

        self.build_ui()

        try:

            self.drop_handler = NativeDropHandler(
                [
                    self.root,
                    self.drop
                ],
                self.add_files
            )

        except Exception as e:

            self.drop_handler = None

            self.status.set(
                "拖拽功能初始化失败，可使用“选择图片”"
            )

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self):

        style = ttk.Style()

        try:
            style.theme_use(
                "vista"
            )
        except Exception:
            pass

        frame = ttk.Frame(
            self.root,
            padding=16
        )

        frame.pack(
            fill="both",
            expand=True
        )

        ttk.Label(
            frame,
            text="ImageSizer XP",
            font=("Segoe UI", 20, "bold")
        ).pack(
            anchor="w"
        )

        ttk.Label(
            frame,
            text="JPG 专用 · 图片尺寸与文件大小压缩工具"
        ).pack(
            anchor="w",
            pady=(2, 12)
        )

        settings = ttk.LabelFrame(
            frame,
            text="输出限制",
            padding=12
        )

        settings.pack(
            fill="x"
        )

        ttk.Label(
            settings,
            text="最大宽度（px）"
        ).grid(
            row=0,
            column=0,
            sticky="w"
        )

        ttk.Entry(
            settings,
            textvariable=self.max_w,
            width=12
        ).grid(
            row=0,
            column=1,
            padx=(8, 20)
        )

        ttk.Label(
            settings,
            text="最大高度（px）"
        ).grid(
            row=0,
            column=2,
            sticky="w"
        )

        ttk.Entry(
            settings,
            textvariable=self.max_h,
            width=12
        ).grid(
            row=0,
            column=3,
            padx=(8, 20)
        )

        ttk.Label(
            settings,
            text="最大文件大小（KB）"
        ).grid(
            row=0,
            column=4,
            sticky="w"
        )

        ttk.Entry(
            settings,
            textvariable=self.max_kb,
            width=12
        ).grid(
            row=0,
            column=5,
            padx=8
        )

        self.drop = tk.Text(
            frame,
            height=12,
            relief="groove",
            borderwidth=1,
            font=("Segoe UI", 10)
        )

        self.drop.pack(
            fill="both",
            expand=True,
            pady=14
        )

        self.drop.insert(
            "1.0",
            "把 JPG / JPEG 图片拖到这里\n\n"
            "也可以点击下面的“选择图片”按钮。"
        )

        self.drop.configure(
            state="disabled"
        )

        buttons = ttk.Frame(
            frame
        )

        buttons.pack(
            fill="x"
        )

        ttk.Button(
            buttons,
            text="选择图片",
            command=self.choose_files
        ).pack(
            side="left"
        )

        ttk.Button(
            buttons,
            text="清空",
            command=self.clear_files
        ).pack(
            side="left",
            padx=8
        )

        ttk.Button(
            buttons,
            text="开始压缩",
            command=self.start
        ).pack(
            side="right"
        )

        output = ttk.Frame(
            frame
        )

        output.pack(
            fill="x",
            pady=(12, 0)
        )

        ttk.Label(
            output,
            text="输出目录："
        ).pack(
            side="left"
        )

        ttk.Entry(
            output,
            textvariable=self.out_dir
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=6
        )

        ttk.Button(
            output,
            text="浏览",
            command=self.choose_dir
        ).pack(
            side="right"
        )

        ttk.Progressbar(
            frame,
            variable=self.progress,
            maximum=100
        ).pack(
            fill="x",
            pady=(12, 4)
        )

        ttk.Label(
            frame,
            textvariable=self.status
        ).pack(
            anchor="w"
        )

    # --------------------------------------------------------
    # 添加文件
    # --------------------------------------------------------

    def choose_files(self):

        files = filedialog.askopenfilenames(
            title="选择 JPG 图片",
            filetypes=[
                (
                    "JPG 图片",
                    "*.jpg *.jpeg"
                ),
                (
                    "所有文件",
                    "*.*"
                )
            ]
        )

        self.add_files(files)

    def add_files(self, files):

        added = 0

        for filename in files:

            filename = str(filename)

            if not os.path.isfile(filename):
                continue

            ext = os.path.splitext(
                filename
            )[1].lower()

            if ext not in (
                ".jpg",
                ".jpeg"
            ):
                continue

            if filename not in self.files:

                self.files.append(
                    filename
                )

                added += 1

        self.refresh_file_list()

        if added:

            self.status.set(
                "已添加 {} 张 JPG 图片".format(
                    len(self.files)
                )
            )

        else:

            self.status.set(
                "没有新增 JPG 图片"
            )

    def refresh_file_list(self):

        self.drop.configure(
            state="normal"
        )

        self.drop.delete(
            "1.0",
            "end"
        )

        if self.files:

            self.drop.insert(
                "1.0",
                "已添加 {} 张 JPG 图片\n\n".format(
                    len(self.files)
                )
            )

            for i, filename in enumerate(
                self.files,
                1
            ):

                self.drop.insert(
                    "end",
                    "{}. {}\n".format(
                        i,
                        os.path.basename(
                            filename
                        )
                    )
                )

        else:

            self.drop.insert(
                "1.0",
                "把 JPG / JPEG 图片拖到这里\n\n"
                "也可以点击下面的“选择图片”按钮。"
            )

        self.drop.configure(
            state="disabled"
        )

    # --------------------------------------------------------
    # 清空
    # --------------------------------------------------------

    def clear_files(self):

        self.files[:] = []

        self.refresh_file_list()

        self.progress.set(
            0
        )

        self.status.set(
            "等待添加 JPG 图片"
        )

    # --------------------------------------------------------
    # 输出目录
    # --------------------------------------------------------

    def choose_dir(self):

        directory = filedialog.askdirectory(
            title="选择输出目录"
        )

        if directory:
            self.out_dir.set(
                directory
            )

    # --------------------------------------------------------
    # 开始
    # --------------------------------------------------------

    def start(self):

        if not self.files:

            messagebox.showwarning(
                "提示",
                "请先添加 JPG 图片。"
            )

            return

        try:

            max_width = int(
                self.max_w.get()
            )

            max_height = int(
                self.max_h.get()
            )

            max_kb = int(
                self.max_kb.get()
            )

            if (
                max_width < 1
                or max_height < 1
                or max_kb < 1
            ):
                raise ValueError

        except ValueError:

            messagebox.showerror(
                "参数错误",
                "最大宽度、最大高度、"
                "最大文件大小必须是正整数。"
            )

            return

        if self.out_dir.get():

            output_dir = self.out_dir.get()

        else:

            output_dir = os.path.join(
                os.path.dirname(
                    self.files[0]
                ),
                "ImageSizer_Output"
            )

        if not os.path.exists(
            output_dir
        ):

            try:

                os.makedirs(
                    output_dir
                )

            except Exception as e:

                messagebox.showerror(
                    "错误",
                    "无法创建输出目录：\n{}\n\n{}".format(
                        output_dir,
                        e
                    )
                )

                return

        self.progress.set(
            0
        )

        self.status.set(
            "开始压缩..."
        )

        threading.Thread(
            target=self.worker,
            args=(
                max_width,
                max_height,
                max_kb,
                output_dir
            )
        ).start()

    # --------------------------------------------------------
    # 后台处理
    # --------------------------------------------------------

    def worker(
        self,
        max_width,
        max_height,
        max_kb,
        output_dir
    ):

        success = 0
        errors = []

        total = len(
            self.files
        )

        for index, src in enumerate(
            self.files,
            1
        ):

            try:

                filename = os.path.splitext(
                    os.path.basename(src)
                )[0]

                dst = os.path.join(
                    output_dir,
                    filename + "_compressed.jpg"
                )

                width, height, quality, size = compress_image(
                    src,
                    dst,
                    max_width,
                    max_height,
                    max_kb
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
                        "{}/{}：{}×{}，质量 {}，{:.1f} KB".format(
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
                        os.path.basename(src),
                        e
                    )
                )

            progress = (
                index /
                float(total)
            ) * 100

            self.root.after(
                0,
                lambda progress=progress:
                self.progress.set(
                    progress
                )
            )

        message = (
            "完成：{}/{} 张\n\n"
            "输出目录：{}".format(
                success,
                total,
                output_dir
            )
        )

        if errors:

            message += (
                "\n\n失败文件：\n"
                + "\n".join(
                    errors[:10]
                )
            )

            if len(errors) > 10:

                message += (
                    "\n……还有 {} 个文件失败".format(
                        len(errors) - 10
                    )
                )

        self.root.after(
            0,
            lambda message=message:
            messagebox.showinfo(
                "处理完成",
                message
            )
        )

        self.root.after(
            0,
            lambda success=success,
            total=total:
            self.status.set(
                "完成：{}/{} 张".format(
                    success,
                    total
                )
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
