# ImageSizer — Windows XP 32-bit 绿色版

一个开源的 Windows 图片尺寸/文件大小压缩工具。

## 功能

- Windows 原生拖拽添加图片
- 批量处理
- 最大宽度
- 最大高度
- 最大文件大小（KB）
- 保持宽高比例
- JPEG 质量二分搜索
- 文件过大时自动继续缩小尺寸
- JPG / JPEG / PNG / WebP / BMP / TIFF
- PNG 透明背景自动转白色
- EXIF 方向纠正
- 自动创建输出目录
- 不覆盖原文件
- 单文件绿色 EXE
- 目标：Windows XP 32 位

## 为什么这版适合 XP

这版不再使用 `tkinterdnd2`，拖拽改为 Windows 原生 `WM_DROPFILES`，减少额外 DLL/Tk 扩展带来的兼容性问题。

构建链固定为：

- Python 3.4.4 x86
- Pillow 5.4.1
- PyInstaller 3.4

PyInstaller 3.4 的 Windows 文档支持 Windows XP；Python 官方文档也指出 Windows XP 需要 Python 3.4。

## GitHub Actions

工作流文件：

`.github/workflows/build_windows_xp32.yml`

GitHub 操作：

1. Actions
2. Build Windows XP 32-bit Portable EXE
3. Run workflow
4. 等待完成
5. 下载 Artifact：`ImageSizer-Windows-XP-32bit`

得到：

`ImageSizer_XP32.exe`

## 注意

Windows XP 已停止官方安全支持。此版本是为了兼容旧电脑，不建议在联网的 XP 系统上处理敏感资料。
