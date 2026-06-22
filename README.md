# BIP 预览修复助手 Pro

一个用于修复 `.bip` 文件图标/预览不显示的独立工具。适用于已安装 KeyShot 的 Windows 用户。

重要说明：本工具不是 KeyShot 官方产品，不包含、不复制、不分发 KeyShot 的 DLL、EXE、图标或其他官方文件。工具只调用用户本机已安装 KeyShot 中的 `KeyShot-ih.dll`。

## 使用流程

1. 双击 `启动_BIP预览修复助手.cmd`。
2. 允许管理员权限。
3. 点击 `自动扫描`。
4. 选中用户平时使用的 KeyShot 版本。
5. 点击 `修复选中`。
6. 点击 `查看当前生效版本`，确认生效 DLL 指向选中的 KeyShot 目录。
7. 点击 `清缓存并重启资源管理器`。
8. 重新打开 `.bip` 文件夹。

## Pro 功能

- 现代化低饱和黑白灰界面，左侧固定展示 5 步使用流程。
- 自动扫描本机 KeyShot 安装目录。
- 手动添加非标准安装目录。
- 注册 `KeyShot-ih.dll`。
- 自动补齐 `KeyShot.Document` 和 `Applications\keyshot.exe` 的 IconHandler。
- 显示当前生效 ProgID、IconHandler、DLL。
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

对外售卖时建议只分发 EXE、README 和使用说明，不要分发任何 KeyShot 官方文件。

## 商业化建议

- 产品名建议使用“适用于 KeyShot”的描述，不要写成官方工具。
- 购买页写明“需要用户已合法安装 KeyShot”。
- 售后第一步让用户点击“导出诊断报告”。
- 正式售卖版可以再加入授权码、机器码、自动更新和签名证书。

## 界面流程

主界面左侧展示：

1. 自动扫描
2. 选择常用版本
3. 修复选中
4. 确认生效版本
5. 清缓存

右侧是操作面板、安装目录列表、日志和状态栏。
