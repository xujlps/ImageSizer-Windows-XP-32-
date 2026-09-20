# -*- coding: utf-8 -*-
"""
ImageSizer - Windows 图片尺寸/文件大小压缩工具
License: MIT
"""

import io
import os
import threading
import ctypes
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from PIL import Image


SUPPORTED = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}


# ============================================================
# EXIF 图片方向处理
# 兼容 Pillow 5.4
# ============================================================

def apply_exif_orientation(img):
    """Pillow 5.4-compatible EXIF orientation handling."""
    try:
        exif = img._getexif()
        orientation = exif.get(274) if exif else None
    except Exception:
        orientation = None

    methods = {
        2: Image.FLIP_LEFT_RIGHT,
        3: Image.ROTATE_180,
        4: Image.FLIP_TOP_BOTTOM,
        5: Image.TRANSPOSE,
        6: Image.ROTATE_270,
        7: Image.TRANSVERSE,
        8: Image.ROTATE_90,
    }

    if orientation in methods:
        return img.transpose(methods[orientation])

    return img.copy()


# ============================================================
# Windows 原生文件拖放
# 不依赖 tkinterdnd2
# ============================================================

WM_DROPFILES = 0x0233
GWL_WNDPROC = -4

_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32


_WNDPROC = ctypes.WINFUNCTYPE(
    ctypes.c_long,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_size_t,
    ctypes.c_ssize_t,
)


class NativeDropHandler(object):
    """Windows 原生 WM_DROPFILES 拖放，不依赖 tkinterdnd2。"""

    def __init__(self, widgets, callback):
        self.callback = callback
        self.old_procs = []
        self.procs = []

        for widget in widgets:
            hwnd = widget.winfo_id()

            proc = _WNDPROC(self._wnd_proc)

            old_proc = _user32.SetWindowLongW(
                hwnd,
                GWL_WNDPROC,
                ctypes.cast(proc, ctypes.c_void_p).value,
            )

            self.procs.append(proc)
            self.old_procs.append((hwnd, old_proc))

            _shell32.DragAcceptFiles(hwnd, True)

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            try:
                self._read_files(wparam)
            finally:
                _shell32.DragFinish(wparam)

            return 0

        old_proc = 0

        for old_hwnd, proc in self.old_procs:
            if old_hwnd == hwnd:
                old_proc = proc
                break

        return _user32.CallWindowProcW(
            old_proc,
            hwnd,
            msg,
            wparam,
            lparam,
        )

    def _read_files(self, hdrop):
        count = _shell32.DragQueryFileW(
            hdrop,
            0xFFFFFFFF,
            None,
            0,
        )

        files = []

        for i in range(count):
            length = _shell32.DragQueryFileW(
                hdrop,
                i,
                None,
                0,
            )

            buf = ctypes.create_unicode_buffer(length + 1)

            _shell32.DragQueryFileW(
                hdrop,
                i,
                buf,
                length + 1,
            )

            files.append(buf.value)

        if files:
            self.callback(files)


# ============================================================
# 图片尺寸计算
# ============================================================

def fit_size(w, h, max_w, max_h):
    scale = min(
        float(max_w) / float(w),
        float(max_h) / float(h),
        1.0,
    )

    return (
        max(1, int(round(w * scale))),
        max(1, int(round(h * scale))),
    )


# ============================================================
# JPEG 编码
# ============================================================

def encode_jpeg(img, quality):
    """
    将图片转换成 JPEG。

    JPEG 不支持透明通道：
    RGBA / LA 图片使用白色背景。
    """

    if img.mode in ("RGBA", "LA"):
        bg = Image.new(
            "RGB",
            img.size,
            "white",
        )

        bg.paste(
            img,
            mask=img.getchannel("A"),
        )

        img = bg

    elif img.mode != "RGB":
        img = img.convert("RGB")

    bio = io.BytesIO()

    img.save(
        bio,
        format="JPEG",
        quality=quality,
        optimize=True,
        progressive=True,
        subsampling="4:2:0",
    )

    return bio.getvalue()


# ============================================================
# 单张图片压缩
# ============================================================

def compress_image(src, dst, max_w, max_h, max_kb):

    with Image.open(src) as original:

        # EXIF 方向修正
        img = apply_exif_orientation(original)

        # 限制最大尺寸
        w, h = fit_size(
            img.width,
            img.height,
            max_w,
            max_h,
        )

        if (w, h) != img.size:
            img = img.resize(
                (w, h),
                Image.ANTIALIAS,
            )

        target = max_kb * 1024

        # ----------------------------------------------------
        # 第一轮：质量 95
        # ----------------------------------------------------

        data = encode_jpeg(
            img,
            95,
        )

        if len(data) <= target:

            quality = 95

        else:

            # ------------------------------------------------
            # 第二轮：二分寻找最高 JPEG 质量
            # ------------------------------------------------

            lo = 20
            hi = 94

            best = None
            best_q = None

            while lo <= hi:

                q = (lo + hi) // 2

                candidate = encode_jpeg(
                    img,
                    q,
                )

                if len(candidate) <= target:

                    best = candidate
                    best_q = q

                    lo = q + 1

                else:

                    hi = q - 1

            # ------------------------------------------------
            # 如果质量最低仍然超过限制
            # 逐步缩小图片尺寸
            # ------------------------------------------------

            if best is None:

                while (
                    img.width > 320
                    and img.height > 320
                ):

                    nw = max(
                        1,
                        int(round(img.width * 0.9)),
                    )

                    nh = max(
                        1,
                        int(round(img.height * 0.9)),
                    )

                    img = img.resize(
                        (nw, nh),
                        Image.ANTIALIAS,
                    )

                    candidate = encode_jpeg(
                        img,
                        20,
                    )

                    if len(candidate) <= target:

                        best = candidate
                        best_q = 20

                        break

            # ------------------------------------------------
            # 仍然无法达到目标
            # ------------------------------------------------

            if best is None:

                raise ValueError(
                    "目标文件大小过小，无法生成满足要求的图片。"
                    "请提高目标 KB。"
                )

            data = best
            quality = best_q

        # ----------------------------------------------------
        # 写入输出文件
        # ----------------------------------------------------

        with open(
            dst,
            "wb",
        ) as fp:

            fp.write(data)

        return (
            img.size,
            quality,
            len(data),
        )


# ============================================================
# 主程序
# ============================================================

class App(object):

    def __init__(self, root):

        self.root = root

        self.root.title(
            "ImageSizer - 图片尺寸与文件大小压缩工具"
        )

        self.root.geometry(
            "720x560"
        )

        self.root.minsize(
            650,
            500
        )

        self.files = []

        # 默认参数
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
            value="等待添加图片"
        )

        self.progress = tk.DoubleVar(
            value=0
        )

        self.build_ui()

        # ----------------------------------------------------
        # Windows 原生拖放
        # ----------------------------------------------------

        self.drop_handler = NativeDropHandler(
            [
                self.root,
                self.drop,
            ],
            self.add_files,
        )


    # ========================================================
    # UI
    # ========================================================

    def build_ui(self):

        style = ttk.Style()

        try:
            style.theme_use(
                "vista"
            )
        except Exception:
            pass

        frm = ttk.Frame(
            self.root,
            padding=16,
        )

        frm.pack(
            fill="both",
            expand=True,
        )

        ttk.Label(
            frm,
            text="ImageSizer",
            font=(
                "Segoe UI",
                20,
                "bold",
            ),
        ).pack(
            anchor="w"
        )

        ttk.Label(
            frm,
            text="拖入图片 → 设置最大尺寸和文件大小 → 一键压缩",
            foreground="#666666",
        ).pack(
            anchor="w",
            pady=(2, 12),
        )

        # ----------------------------------------------------
        # 输出限制
        # ----------------------------------------------------

        settings = ttk.LabelFrame(
            frm,
            text="输出限制",
            padding=12,
        )

        settings.pack(
            fill="x"
        )

        ttk.Label(
            settings,
            text="最大宽度（px）",
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )

        ttk.Entry(
            settings,
            textvariable=self.max_w,
            width=12,
        ).grid(
            row=0,
            column=1,
            padx=(8, 20),
        )

        ttk.Label(
            settings,
            text="最大高度（px）",
        ).grid(
            row=0,
            column=2,
            sticky="w",
        )

        ttk.Entry(
            settings,
            textvariable=self.max_h,
            width=12,
        ).grid(
            row=0,
            column=3,
            padx=(8, 20),
        )

        ttk.Label(
            settings,
            text="最大文件大小（KB）",
        ).grid(
            row=0,
            column=4,
            sticky="w",
        )

        ttk.Entry(
            settings,
            textvariable=self.max_kb,
            width=12,
        ).grid(
            row=0,
            column=5,
            padx=8,
        )

        # ----------------------------------------------------
        # 拖放区域
        # ----------------------------------------------------

        self.drop = tk.Text(
            frm,
            height=12,
            relief="groove",
            borderwidth=1,
            font=(
                "Segoe UI",
                10,
            ),
        )

        self.drop.pack(
            fill="both",
            expand=True,
            pady=14,
        )

        self.drop.insert(
            "1.0",
            "把 JPG / PNG / WebP / BMP / TIFF 图片拖到这里\n\n"
            "也可以点击下面的“选择图片”按钮。",
        )

        self.drop.configure(
            state="disabled"
        )

        # ----------------------------------------------------
        # 按钮
        # ----------------------------------------------------

        buttons = ttk.Frame(
            frm
        )

        buttons.pack(
            fill="x"
        )

        ttk.Button(
            buttons,
            text="选择图片",
            command=self.choose_files,
        ).pack(
            side="left"
        )

        ttk.Button(
            buttons,
            text="清空",
            command=self.clear_files,
        ).pack(
            side="left",
            padx=8,
        )

        ttk.Button(
            buttons,
            text="开始压缩",
            command=self.start,
        ).pack(
            side="right"
        )

        # ----------------------------------------------------
        # 输出目录
        # ----------------------------------------------------

        out = ttk.Frame(
            frm
        )

        out.pack(
            fill="x",
            pady=(12, 0),
        )

        ttk.Label(
            out,
            text="输出目录：",
        ).pack(
            side="left"
        )

        ttk.Entry(
            out,
            textvariable=self.out_dir,
        ).pack(
            side="left",
            fill="x",
            expand=True,
            padx=6,
        )

        ttk.Button(
            out,
            text="浏览",
            command=self.choose_dir,
        ).pack(
            side="right"
        )

        # ----------------------------------------------------
        # 进度条
        # ----------------------------------------------------

        ttk.Progressbar(
            frm,
            variable=self.progress,
            maximum=100,
        ).pack(
            fill="x",
            pady=(12, 4),
        )

        ttk.Label(
            frm,
            textvariable=self.status,
        ).pack(
            anchor="w"
        )


    # ========================================================
    # 选择图片
    # ========================================================

    def choose_files(self):

        files = filedialog.askopenfilenames(
            title="选择图片",
            filetypes=[
                (
                    "图片",
                    "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff",
                ),
                (
                    "所有文件",
                    "*.*",
                ),
            ],
        )

        self.add_files(
            files
        )


    # ========================================================
    # 添加图片
    # ========================================================

    def add_files(self, files):

        added = 0

        for f in files:

            p = Path(f)

            try:
                is_file = p.is_file()
                suffix = p.suffix.lower()
            except Exception:
                continue

            if (
                is_file
                and suffix in SUPPORTED
                and str(p) not in self.files
            ):

                self.files.append(
                    str(p)
                )

                added += 1

        self.drop.configure(
            state="normal"
        )

        self.drop.delete(
            "1.0",
            "end",
        )

        if self.files:

            self.drop.insert(
                "1.0",
                "已添加 {} 张图片\n\n".format(
                    len(self.files)
                ),
            )

            for i, f in enumerate(
                self.files,
                1,
            ):

                self.drop.insert(
                    "end",
                    "{}. {}\n".format(
                        i,
                        Path(f).name,
                    ),
                )

        else:

            self.drop.insert(
                "1.0",
                "请拖入图片或点击“选择图片”。",
            )

        self.drop.configure(
            state="disabled"
        )

        if added:

            self.status.set(
                "已添加 {} 张图片".format(
                    len(self.files)
                )
            )

        else:

            self.status.set(
                "没有新增图片"
            )


    # ========================================================
    # 清空
    # ========================================================

    def clear_files(self):

        self.files[:] = []

        self.drop.configure(
            state="normal"
        )

        self.drop.delete(
            "1.0",
            "end",
        )

        self.drop.insert(
            "1.0",
            "把 JPG / PNG / WebP / BMP / TIFF 图片拖到这里\n\n"
            "也可以点击下面的“选择图片”按钮。",
        )

        self.drop.configure(
            state="disabled"
        )

        self.progress.set(
            0
        )

        self.status.set(
            "等待添加图片"
        )


    # ========================================================
    # 选择输出目录
    # ========================================================

    def choose_dir(self):

        d = filedialog.askdirectory(
            title="选择输出目录"
        )

        if d:

            self.out_dir.set(
                d
            )


    # ========================================================
    # 开始压缩
    # ========================================================

    def start(self):

        if not self.files:

            messagebox.showwarning(
                "提示",
                "请先添加图片。",
            )

            return

        # ----------------------------------------------------
        # 检查参数
        # ----------------------------------------------------

        try:

            mw = int(
                self.max_w.get()
            )

            mh = int(
                self.max_h.get()
            )

            kb = int(
                self.max_kb.get()
            )

            if (
                mw < 1
                or mh < 1
                or kb < 1
            ):
                raise ValueError

        except ValueError:

            messagebox.showerror(
                "参数错误",
                "最大宽度、最大高度、最大文件大小必须是正整数。",
            )

            return

        # ----------------------------------------------------
        # 输出目录
        # ----------------------------------------------------

        if self.out_dir.get():

            out = Path(
                self.out_dir.get()
            )

        else:

            out = (
                Path(self.files[0]).parent
                / "ImageSizer_Output"
            )

        # ----------------------------------------------------
        # 兼容旧版 Python
        #
        # 不使用：
        # mkdir(parents=True, exist_ok=True)
        #
        # 因为 Python 3.4 及更早版本不支持 exist_ok。
        # ----------------------------------------------------

        if not out.exists():

            try:

                out.mkdir(
                    parents=True
                )

            except OSError:

                # 可能是创建过程中目录已经出现
                if not out.exists():

                    messagebox.showerror(
                        "错误",
                        "无法创建输出目录：\n{}".format(
                            out
                        ),
                    )

                    return

        # ----------------------------------------------------
        # 开始后台线程
        # ----------------------------------------------------

        self.progress.set(
            0
        )

        self.status.set(
            "开始压缩..."
        )

        threading.Thread(
            target=self.worker,
            args=(
                mw,
                mh,
                kb,
                out,
            ),
            daemon=True,
        ).start()


    # ========================================================
    # 后台处理
    # ========================================================

    def worker(
        self,
        mw,
        mh,
        kb,
        out,
    ):

        ok = 0
        errors = []

        total = len(
            self.files
        )

        for i, src in enumerate(
            self.files,
            1,
        ):

            try:

                name = (
                    Path(src).stem
                    + "_compressed.jpg"
                )

                dst = out / name

                size, quality, bytes_written = compress_image(
                    src,
                    dst,
                    mw,
                    mh,
                    kb,
                )

                ok += 1

                self.root.after(
                    0,
                    lambda i=i,
                    size=size,
                    q=quality,
                    b=bytes_written:
                    self.status.set(
                        "{}/{}：{}×{}，质量 {}，{:.1f} KB".format(
                            i,
                            total,
                            size[0],
                            size[1],
                            q,
                            b / 1024.0,
                        )
                    ),
                )

            except Exception as e:

                errors.append(
                    "{}: {}".format(
                        Path(src).name,
                        e,
                    )
                )

            self.root.after(
                0,
                lambda i=i:
                self.progress.set(
                    i / float(total) * 100
                ),
            )

        # ----------------------------------------------------
        # 完成提示
        # ----------------------------------------------------

        msg = (
            "完成：{}/{} 张\n"
            "输出目录：{}".format(
                ok,
                total,
                out,
            )
        )

        if errors:

            msg += (
                "\n\n失败文件：\n"
                + "\n".join(
                    errors[:10]
                )
            )

            if len(errors) > 10:

                msg += (
                    "\n……还有 {} 个文件失败".format(
                        len(errors) - 10
                    )
                )

        self.root.after(
            0,
            lambda msg=msg:
            messagebox.showinfo(
                "处理完成",
                msg,
            ),
        )

        self.root.after(
            0,
            lambda ok=ok,
            total=total:
            self.status.set(
                "完成：{}/{} 张".format(
                    ok,
                    total,
                )
            ),
        )


# ============================================================
# 程序入口
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    App(root)

    root.mainloop()
