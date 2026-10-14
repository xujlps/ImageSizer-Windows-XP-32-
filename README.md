# ImageSizer — Windows XP 32-bit JPG 绿色版

一个开源的 Windows JPG/JPEG 图片文件大小压缩工具，通过调整 JPEG 质量减小文件大小，保持原始像素宽度和高度。

## 功能

- 仅支持 JPG / JPEG 图片（`.jpg`、`.jpeg`，扩展名不区分大小写）
- Windows 原生拖拽添加图片，也可通过“选择图片”添加
- 批量处理，显示原图像素尺寸和文件大小
- 设置最大文件大小（KB），必须输入正整数；1 KB 按 1024 字节计算
- 保持原始像素宽度和高度，不缩放图片
- 在 JPEG Quality 1–95 范围内使用二分搜索调整质量
- 成功输出的文件实际字节数不超过 `最大 KB × 1024`，保存和重命名后均进行校验
- Quality=1 仍无法满足大小限制时，提示失败，不通过缩小尺寸达到目标
- 自动创建输出目录
- 默认输出到第一张输入图片所在目录的 `ImageSizer_Output` 子目录，也可指定输出目录
- 输出文件名为 `原文件名（不含扩展名）_compressed.jpg`
- 单文件绿色 EXE，使用者无需另外安装 Python
- 兼容目标：Windows XP SP3 32 位

当前版本使用 Windows GDI+ 处理图片，不使用 Pillow 或 `tkinterdnd2`。不支持 PNG 输入或透明背景转换，也未实现 EXIF 方向纠正。

## 使用方法

1. 下载并解压构建产物，运行 `ImageSizer_XP32.exe`。
2. 拖入 JPG/JPEG 图片，或点击“选择图片”。
3. 输入最大文件大小（KB），例如 `500` 表示最多 512000 字节。
4. 按需选择输出目录；留空时使用默认目录。
5. 点击“开始压缩”，完成后查看成功数量、失败文件及输出目录。

压缩会重新编码 JPEG，降低质量可能产生画质损失。目标大小过小时，请提高 KB 上限。

输出目录应具有写入权限。已有同名 `_compressed.jpg` 输出文件会被替换；不同目录下的同名图片也可能生成相同的输出文件名，建议分批输出到不同目录。避免让生成的输出路径与任何输入文件相同。

## 构建配置与兼容性

当前 GitHub Actions 构建链固定为：

- Python 3.4.4 x86
- pip 19.1.1
- PyInstaller 3.4
- altgraph 0.16.1
- pywin32-ctypes 0.2.0
- pefile 2018.8.8

界面使用 Tkinter，图片处理使用 Windows GDI+，拖拽使用 Windows 原生 `WM_DROPFILES`。

构建在 GitHub 的 `windows-latest` runner 上执行，使用 32 位 Python 打包。当前工作流只检查 EXE 是否生成并上传产物；构建成功不代表已经在 Windows XP 上完成运行验证，也不代表已通过图片大小边界测试。使用前应在目标 Windows XP SP3 32 位电脑上验证启动、图片处理和输出文件大小。

## GitHub Actions 构建与下载

工作流文件：[`.github/workflows/build_windows.yml`](.github/workflows/build_windows.yml)

工作流名称：`Build Windows XP 32-bit JPG EXE`

[打开此工作流](https://github.com/xujlps/ImageSizer-Windows-XP-32-/actions/workflows/build_windows.yml)

当前工作流只配置了 `workflow_dispatch`，提交代码不会自动触发构建。

1. 登录 GitHub，打开仓库的 **Actions** 页面。
2. 选择 **Build Windows XP 32-bit JPG EXE**。
3. 点击 **Run workflow**，选择 `main` 分支，再确认运行。手动触发需要仓库写入权限；没有权限的用户可下载已有的有效产物，或 Fork 后在自己的仓库启用 Actions 并运行。
4. 等待运行成功，打开对应运行记录。
5. 在运行详情页的 **Artifacts** 区域下载 `ImageSizer-Windows-XP-32bit-JPG`。
6. 解压下载的 ZIP，得到 `ImageSizer_XP32.exe`，再运行程序。

构建输出路径为 `dist/ImageSizer_XP32.exe`。Artifact 是下载包名称，EXE 是包内程序名称，两者不同。

产物保留时间为 **30 天**。若产物已过期、被删除或构建失败，请重新触发构建，并从新成功运行的详情页下载。仓库的 **Code → Download ZIP** 下载的是源码，不是已构建的 EXE。

## 注意

Windows XP 已停止官方安全支持。此版本是为了兼容旧电脑，不建议在联网的 XP 系统上处理敏感资料。
