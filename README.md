# TOTP Account Manager

基于 Python 的 TOTP（时间同步一次性密码）账户管理工具，支持导入、管理和备份多平台 TOTP 账户，支持扫码导入（otpauth://totp/ 及 otpauth-migration://），并使用桌面 GUI 界面进行操作。

## 功能简介

- 支持 TOTP 账户的添加、删除、编辑、备份和还原。
- 支持通过扫码图片自动识别导入（支持常见的 otpauth://totp/ 和 otpauth-migration:// 格式）。
- 本地 JSON 文件存储账户数据。
- 基于 Tkinter 实现桌面 GUI 界面友好易用。
- 支持多平台（理论上兼容 Windows、Linux、macOS）。

## 主要依赖

- Python 3.13+
- pyotp
- pyzbar
- pillow (PIL)
- tkinter

## 快速开始

1. **安装依赖**

   ```bash
   pip install pyotp pyzbar pillow
   ```

2. **运行主程序**

   ```bash
   python totp_manager.py
   ```

3. **Windows 打包**

   已包含 `pyinstaller.txt`、`totp_manager.spec`，可通过如下命令打包为单文件可执行程序（需根据自身环境调节依赖路径）：

   ```bash
   pyinstaller --onefile --noconsole --add-binary "C:\路径\pyzbar\libiconv.dll;pyzbar" --add-binary "C:\路径\pyzbar\libzbar-64.dll;pyzbar" totp_manager.py
   ```

   或参考 `pyinstaller.txt` 与 `totp_manager.spec` 文件。

4. **账户数据文件**

   账户信息保存在项目根目录下 `totp_accounts.json` 文件，注意定期备份。

## 部分核心代码说明

- `totp_manager.py`：主程序文件，包含 GUI、数据导入导出、二维码解析、TOTP 生成等功能的实现。
- 支持识别 `otpauth://totp/` 和 `otpauth-migration://` 两种二维码/迁移格式。
- 所有操作均为本地离线运行，不上传数据，保障隐私安全。

## 注意事项

- 初始化运行前需确保依赖包已安装。
- 若扫码功能异常，请确保本机已正确安装并配置 pyzbar 及其依赖的 zbar DLL。

## 相关链接

- [GitHub 仓库主页](https://github.com/lanbing1989/totp_account_manage)

---

> **提示**：以上内容为自动生成，若有特殊定制需求可根据实际情况补充完善。