# Ralph + Claude Code 自动化流程工具集

本仓库用于我基于 Ralph 工作流理念与 Claude Code CLI 构建的自动化流程工具。当前包含两个可运行的工作流模块：
- Code Reader（代码导览生成）
- Security Audit Loop（安全审计循环）

目标是让 AI 以“循环器”的方式对代码库进行规划、执行、产出与标记，从而形成稳定可复用的工程化自动化方案。

---

## 功能概览

- Code Reader
  - 自动规划待读文件清单，循环选择入口与相关上下游文件
  - 为每个被阅读的源码文件生成面向新手的 Markdown 导览文档
  - 记录并同步阅读进度（Pending/Done）
- Security Audit Loop
  - 自动生成审计面列表，按高价值目标循环进行红队式安全审计
  - 记录漏洞报告（含 Root Cause / Exploit / Fix）并标记完成
  - 持续迭代直至清单中的目标全部完成

---

## 环境与前置条件

- 操作系统：Windows（脚本在 Windows 下开发与验证）
- Python
- Claude Code CLI：已安装并在系统 PATH 中，命令名为 `claude`
  - 若运行时报错“找不到 `claude` 命令”，请先安装官方 CLI 并配置 PATH

---

## 快速开始

1) 克隆并进入本项目根目录：

```bash
cd ralph-caludecode-demo
```

2) 代码阅读器（Code Reader）工作流：

```bash
# 在目标代码库根目录执行或指定目标根路径
python .code-reader/read_loop.py [可选：目标根路径]
```

运行后会经历两阶段：
- Phase 1（规划）：扫描并初始化 `.code-read` 目录下的状态与清单（`CODE_READ_TODO.md`、`.state.json`）
- Phase 2（循环）：每轮从待办选择入口文件，阅读关联上下游，生成对应的 Markdown 文档至 `.code-read/src/...`，并将已完成文件打钩

3) 安全审计循环（Security Audit Loop）工作流：

```bash
python .security-audit-loop/loop.py [可选：目标根路径]
```

首次运行会：
- 规划阶段：在目标项目下生成 `.security-audit/SECURITY_FILETREE_TODO.json` 与 `SECURITY_FILETREE_TODO.md`
- 审计循环：依据清单选择 Pending 目标进行红队式审计；若确认存在可利用的高价值漏洞，调用管理脚本写入 `SECURITY_AUDIT_REPORT.md` 并标记 Done

---

## 生成产物

- Code Reader
  - `.code-read/CODE_READ_TODO.md`：阅读进度清单（Pending/Done）
  - `.code-read/.state.json`：内部状态（目标列表、标签、进度等）
  - `.code-read/src/<源码相对路径>.md`：面向新手的功能导览文档
- Security Audit Loop
  - `.security-audit/SECURITY_FILETREE_TODO.json`：审计状态（目标、标签、忽略目录等）
  - `.security-audit/SECURITY_FILETREE_TODO.md`：审计清单（可视化）
  - `.security-audit/SECURITY_AUDIT_REPORT.md`：漏洞报告集合

---

## 目录结构（简要）

```
.code-reader/
  prompts/
    PROMPT_planner.md
    PROMPT_reader.md
  scripts/
    read_manager.py
  read_loop.py

.security-audit-loop/
  prompts/
    PROMPT_planner.md
    PROMPT_audit.md
  scripts/
    audit_manager.py
  loop.py
```

- `read_loop.py` / `loop.py`：各工作流的入口脚本（调用 Claude Code 执行 Prompt）
- `scripts/*_manager.py`：管理器脚本，提供 `scan/init/remove/next/done/report` 等操作
- `prompts/*.md`：各阶段 Prompt 模板，可按实际项目与偏好调整

---

## 提示与约定

- Ralph 作为工作流理念与角色设定体现在 Prompt 模板中；实际执行由 Claude Code CLI 驱动
- 建议将 Prompt 与忽略/包含规则根据项目特性持续迭代，以得到更聚焦的产出
- 默认面向中文环境输出（报告/文档/日志）

