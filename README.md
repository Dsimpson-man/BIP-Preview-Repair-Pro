# 缩略图修复助手 Pro

一个用于修复常用设计软件文件图标/缩略图不显示的独立工具。目前支持：

- KeyShot `.bip`
- Rhino `.3dm`
- Blender `.blend`

重要说明：本工具不是 KeyShot、Rhino 或 Blender 官方产品，不包含、不复制、不分发任何软件官方 DLL、EXE、图标或其他文件。工具只调用用户本机已安装软件中的 Shell 组件。

## 使用流程

1. 双击 `启动_BIP预览修复助手.cmd`。
2. 允许管理员权限。
3. 在 `修复模块` 选择 `KeyShot .bip`、`Rhino .3dm` 或 `Blender .blend`。
4. 点击 `自动扫描`。
5. 选中用户平时使用的软件版本。
6. 点击 `修复选中`。
7. 点击 `查看当前生效版本`，确认生效 DLL 指向选中的安装目录。
8. 点击 `清缓存并重启资源管理器`。
9. 重新打开文件夹。

## Pro 功能

- 现代化低饱和黑白灰界面，左侧固定展示 5 步使用流程。
- 可切换 KeyShot / Rhino / Blender 修复模块。
- 左侧流程会跟随当前软件变化，分别展示该软件的修复步骤和注意事项。
- 自动扫描本机软件安装目录。
- 手动添加非标准安装目录。
- KeyShot 注册 `KeyShot-ih.dll`。
- Rhino 注册 `RhinoHandlers.dll`。
- Blender 注册 `BlendThumb.dll` 缩略图组件。不要用 `blender.exe -R` 修缩略图，否则部分版本会弹出“不是有效 Blender 文件”的提示。
- Blender 缩略图还取决于 `.blend` 文件本身是否保存了预览；如果旧文件没有内置预览，注册成功后也可能只显示图标。
- 自动补齐 KeyShot 常见 `IconHandler` 关联。
- 显示当前生效 ProgID、IconHandler、ThumbnailHandler、DLL。
- 修复前自动备份关键注册表信息。
- 可手动导出诊断报告，便于售后。
- 可清理缩略图缓存并重启资源管理器。

## 打包为 EXE

开发机安装 Python 3 后，在工具目录运行：

```powershell
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name "BIPPreviewRepairPro" bip_preview_repair_pro.pyw
```

生成文件在：

```text
dist\BIPPreviewRepairPro.exe
```

对外售卖时建议只分发 EXE、README 和使用说明，不要分发任何软件官方文件。

## 商业化建议

- 产品名建议使用“适用于 KeyShot / Rhino / Blender”的描述，不要写成官方工具。
- 购买页写明“需要用户已合法安装对应软件”。
- 售后第一步让用户点击“导出诊断报告”。
- 正式售卖版可以再加入授权码、机器码、自动更新和签名证书。

## 界面流程

主界面左侧会根据当前模块展示对应流程。例如 KeyShot 是：

1. 自动扫描
2. 选择常用版本
3. 修复选中
4. 确认生效版本
5. 清缓存

Rhino 会提示注册 `RhinoHandlers.dll`；Blender 会提示注册 `BlendThumb.dll`，并提醒如果诊断中没有 `ThumbnailHandler`，可能需要选择另一个带 `BlendThumb.dll` 的 Blender 安装目录。

右侧是操作面板、安装目录列表、日志和状态栏。

## 版本记录

- v2.4.1：修正 Blender 缩略图修复逻辑，改为注册 `BlendThumb.dll`，并优化 `.blend` 预览说明。



