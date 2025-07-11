ql repo https://github.com/wuyaos/ql-ck.git

---

## 通用PT站签到脚本 (`pt_checkin.py`)

这是一个用于自动签到多个PT站点的通用脚本。

### 功能

*   **模块化**: 轻松添加和管理多个PT站点。
*   **统一配置**: 使用单个环境变量 `PT_COOKIES` 管理所有站点的Cookie。
*   **日志输出**: 提供带时间和表情符号的友好日志。
*   **自动通知**: 通过`notify.send`发送签到结果。

### 如何使用

1.  **配置站点**:
    打开 `pt_checkin.py` 文件，在 `SITES_CONFIG` 列表中添加或修改你的PT站点信息。

2.  **设置环境变量**:
    在你的运行环境中（例如青龙面板），添加一个名为 `PT_COOKIES` 的环境变量。这个变量的值需要是 **JSON 格式的字符串**。

    **`PT_COOKIES` 格式示例:**
    ```json
    {
      "GGPT": "uid=xxxx; pass=xxxx; ......",
      "HDtime": "uid=yyyy; pass=yyyy; ......"
    }
    ```
    *   **键 (Key)**: 必须与 `SITES_CONFIG` 中配置的 `site_name` 完全一致。
    *   **值 (Value)**: 是对应站点的完整Cookie字符串。

3.  **运行脚本**:
    直接运行 `pt_checkin.py` 脚本。

---
