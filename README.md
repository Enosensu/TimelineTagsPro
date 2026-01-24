# 🎬 Timeline Tags Pro

![Blender Version](https://img.shields.io/badge/Blender-3.0%20%7C%204.0%20%7C%205.0+-orange.svg?logo=blender) ![License](https://img.shields.io/badge/license-MIT-blue.svg) ![Version](https://img.shields.io/badge/version-12.3-green.svg) ![Powered By](https://img.shields.io/badge/Powered%20by-Gemini-4E86F6?logo=googlegemini&logoColor=white)

> **Timeline Tags Pro** 是一个专为 Blender 动画师和动态图形设计师打造的高级时间轴标记与字幕管理系统。

它不仅仅是一个备注工具，更是一个完整的**3D 字幕生成管线**。通过全新的“单文件数据库”架构，它解决了 Blender 原生文本编辑器在管理大量字幕文件时的混乱问题，并提供了 SRT 导入导出、多语言版本管理以及智能 3D 物体烘焙功能。

---

## ✨ 核心特性 (Features)

* **🗂️ 单文件数据库架构 (Single Source of Truth)**
    * 告别成百上千个散乱的文本块。每个版本（Preset）的所有数据均存储在一个独立的 JSON 文本块中（如 `TTAG_DB_English.json`），数据结构清晰，易于管理。

* **🌍 多版本预设管理 (Multi-Version Presets)**
    * 在同一个工程中轻松管理多套字幕方案（例如：英语版、中文版、导演批注版）。
    * 支持一键切换、重命名预设，且不同预设的数据互不干扰。

* **🔄 SRT 字幕导入/导出 (SRT Support)**
    * **导入**：将标准的 `.srt` 字幕文件直接解析到 Blender 时间轴，自动匹配帧率。
    * **导出**：将做好的时间轴标签一键导出为 `.srt` 文件，方便在 Premiere/DaVinci 中使用。

* **🧱 智能 3D 烘焙 (Smart 3D Baking)**
    * 一键将二维标签转换为场景中的 **3D 文本物体**。
    * **独立输出**：不同预设会烘焙到不同的父级空物体（如 `TTAG_Root_VersionA`），支持多语言字幕并存。
    * **智能更新**：勾选“覆盖”可保留物体的动画关键帧仅更新文字；不勾选则创建带时间戳的历史版本。

* **⚡ 高效交互体验**
    * **双向同步**：拖动时间轴自动高亮对应标签；点击标签自动跳转时间轴。
    * **剪贴板桥接**：完美解决 Blender 对中文/多行文本输入支持不佳的问题，支持一键复制/粘贴系统剪贴板内容。
    * **紧凑 UI**：颜色标记、帧号、内容一目了然，支持拖拽排序。

---

## 📦 安装说明 (Installation)

1.  下载最新的 `TimelineTagsPro.py` 文件。
2.  打开 Blender。
3.  点击菜单栏 **Edit** -> **Preferences**。
4.  选择左侧的 **Add-ons**。
5.  点击右上角的 **Install...** 按钮，选择下载的 `.py` 文件。
6.  勾选列表中的 **Animation: Timeline Tags Pro** 以启用插件。
7.  在 3D 视图按 **N** 键打开侧边栏，找到 **Tags Pro** 面板。

---

## 🚀 快速上手 (Quick Start)

### 1. 创建版本
在面板顶部的“版本管理”区域，点击 **"新建版本"**。
* 你可以直接在文本框中重命名版本（例如 `English_Draft`）。
* 系统会自动创建一个名为 `TTAG_DB_English_Draft.json` 的后台文件。

### 2. 添加标签
* 移动时间轴到想要添加字幕的位置。
* 点击列表下方的 `+` 号。
* **编辑内容**：
    * **直接编辑**：在下方的“内容编辑”框中输入文本。
    * **剪贴板粘贴**：在外部（如记事本/微信）复制好文本，点击插件上的 **"粘贴内容"** 按钮（推荐用于中文输入）。
* **保存**：点击列表上方的 **"保存到数据库"** 按钮，确保修改被写入后台文件。

### 3. 3D 烘焙 (Baking)
* 点击底部的 **"烘焙: [版本名]"** 按钮。
* 场景中会生成一个根物体，包含了所有字幕的 3D 文本对象。
* 每个标签会自动根据持续时间设置 `Show/Hide` 关键帧。

### 4. 导出 SRT
* 点击 **"导出 SRT"**。
* Blender 会生成一个名为 `Export_[版本名].srt` 的内部文本块。
* 在 **Text Editor** 中查看，复制内容并保存为 `.srt` 文件即可。

---

## ⚙️ 参数说明

| 参数 | 描述 |
| --- | --- |
| **跟随时间轴 (Sync)** | 开启后，列表选中项会随时间轴播放自动切换；点击列表项时间轴会自动跳转。 |
| **覆盖旧烘焙 (Overwrite)** | **勾选**：更新场景中已存在的 `Root` 物体（保留你手动K的位置/旋转动画）。<br>**不勾选**：创建一个带有时间戳后缀的新物体（用于版本对比）。 |
| **默认颜色** | 新建标签时默认分配的颜色（会影响生成的 3D 文字材质）。 |
| **保存到数据库** | ⚠️ **重要**：由于 Blender UI 限制，直接在输入框修改文字不会自动触发后台保存。手动修改属性后，请点击此按钮同步数据。 |

---

## 🛠️ 数据架构 (For Developers)

本项目采用 **JSON 序列化** 方式存储数据：

```json
// TTAG_DB_VersionName.json
[
  {
    "frame": 1,
    "summary": "F1",
    "content": "Hello World",
    "color": [1.0, 1.0, 1.0]
  },
  {
    "frame": 45,
    "summary": "F45",
    "content": "Subtitle Line 2",
    "color": [1.0, 0.0, 0.0]
  }
]
```

* **优势**：你可以直接在 Blender 的文本编辑器中打开这个 JSON 文件进行批量修改（如批量替换文字、调整帧号），修改后点击插件面板的 **"从文件加载"** 即可刷新 UI。

---

## 🤝 贡献 (Contributing)

欢迎提交 Issue 或 Pull Request！
如果你发现任何 Bug 或有新的功能建议，请随时反馈。

## 📄 许可证 (License)

本项目遵循 **MIT License** 开源协议。

---

> 🤖 **Acknowledgment**: This project was developed with the assistance of **Google Gemini**.
> 本项目核心代码与文档由 **Google Gemini** 辅助开发。
