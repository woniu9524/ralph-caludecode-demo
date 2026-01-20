import argparse
import json
import os
import sys
import datetime
from pathlib import Path
from typing import List, Dict, Any

# --- 配置 ---
DATA_DIR = ".code-read"
TODO_FILENAME = "CODE_READ_TODO.md"  # 独立的待办文件
STATE_FILENAME = ".state.json"       # 内部状态文件

def get_data_dir(root: Path) -> Path:
    d = root / DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d

def load_state(root: Path) -> Dict[str, Any]:
    json_path = get_data_dir(root) / STATE_FILENAME
    if not json_path.exists():
        return {}
    return json.loads(json_path.read_text(encoding="utf-8"))

def save_state(root: Path, state: Dict[str, Any]):
    # 1. 保存 JSON
    json_path = get_data_dir(root) / STATE_FILENAME
    json_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    
    # 2. 同步更新 Markdown 待办列表
    _sync_todo_md(root, state)

def _sync_todo_md(root: Path, state: Dict[str, Any]):
    """将状态同步写入到独立的 Markdown 待办列表中"""
    md_path = get_data_dir(root) / TODO_FILENAME
    
    lines = []
    lines.append("# 代码阅读进度清单 (CODE_READ_TODO)")
    lines.append(f"> 最后更新: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    
    targets = state.get("targets", [])
    
    # 分组：Pending 和 Completed
    pending = [t for t in targets if t["status"] == "pending"]
    completed = [t for t in targets if t["status"] == "completed"]
    
    # 统计信息
    total = len(targets)
    done_count = len(completed)
    progress = (done_count / total * 100) if total > 0 else 0
    
    lines.append(f"## 📊 进度概览: {done_count}/{total} ({progress:.1f}%)")
    lines.append("")
    
    lines.append("## 📝 待阅读 (Pending)")
    if not pending:
        lines.append("- (无，所有文件已处理完毕 🎉)")
    else:
        # 智能排序：Entrypoint 放前面
        pending.sort(key=lambda x: 0 if "entrypoint" in x.get("tags", []) else 1)
        for t in pending:
            tag_str = f" `[{','.join(t.get('tags', []))}]`" if t.get("tags") else ""
            lines.append(f"- [ ] `{t['path']}`{tag_str}")
            
    lines.append("")
    lines.append("## ✅ 已完成 (Done)")
    # 只显示最近完成的 20 个，避免文件过长
    for t in completed[-20:]:
        lines.append(f"- [x] `{t['path']}`")
    if len(completed) > 20:
        lines.append(f"- ...(以及其他 {len(completed)-20} 个文件)")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已更新待办列表: {DATA_DIR}/{TODO_FILENAME}")

def get_auto_tags(file_path: str) -> List[str]:
    tags = set()
    p = file_path.lower()
    if any(x in p for x in ["main", "app", "index", "entry", "cmd", "manage"]):
        tags.add("entrypoint")
    if any(x in p for x in ["util", "common", "helper", "lib"]):
        tags.add("utils")
    if any(x in p for x in ["config", "setting", "env"]):
        tags.add("config")
    if any(x in p for x in ["model", "schema", "db", "entity"]):
        tags.add("model")
    return list(tags)

# --- 命令实现 ---

def cmd_init(root: Path, ignore_dirs: str, include_exts: str):
    ignores = set(x.strip() for x in ignore_dirs.split(",") if x.strip())
    # 默认忽略
    ignores.update({".git", ".idea", ".vscode", "__pycache__", "node_modules", "dist", "build", ".code-read", "venv", ".venv"})
    
    inc_exts = set(x.strip() for x in include_exts.split(",") if x.strip())
    
    targets = []
    print("正在扫描文件树...")
    
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in ignores]
        
        for f in filenames:
            ext = os.path.splitext(f)[1]
            if inc_exts and ext not in inc_exts:
                continue
                
            full_path = Path(dirpath) / f
            rel_path = full_path.relative_to(root)
            path_str = str(rel_path).replace("\\", "/")
            
            targets.append({
                "path": path_str,
                "status": "pending",
                "tags": get_auto_tags(path_str)
            })
            
    state = {
        "root": str(root),
        "created_at": str(datetime.datetime.now()),
        "targets": targets
    }
    
    save_state(root, state)
    print(f"初始化完成！待办列表已生成于 {DATA_DIR}/{TODO_FILENAME}")

def cmd_next(root: Path):
    """读取 TODO 文件并为 Prompt 准备上下文"""
    md_path = get_data_dir(root) / TODO_FILENAME
    
    if not md_path.exists():
        print("错误：找不到待办列表。请先运行 init。")
        return

    # 直接读取 Markdown 文件的内容展示给 Agent，保证 Agent 看到的和文件里的一样
    content = md_path.read_text(encoding="utf-8")
    
    # 截取 Pending 部分，防止 Token 过长
    try:
        parts = content.split("## 📝 待阅读 (Pending)")
        if len(parts) > 1:
            pending_section = parts[1].split("## ✅ 已完成 (Done)")[0]
            # 如果太长，只取前 60 行
            lines = pending_section.strip().splitlines()
            if len(lines) > 60:
                pending_display = "\n".join(lines[:60]) + "\n\n... (更多文件请直接读取 TODO 文件)"
            else:
                pending_display = "\n".join(lines)
        else:
            pending_display = "(无法解析待办列表，请手动检查文件)"
    except Exception:
        pending_display = content

    print("--- 待办列表 (片段) ---")
    print(pending_display)
    print("---------------------")

def cmd_done(root: Path, files: List[str]):
    state = load_state(root)
    targets = state.get("targets", [])
    target_map = {t["path"]: t for t in targets}
    
    updated_count = 0
    for f in files:
        # 处理可能的路径格式差异
        f = f.strip().replace("\\", "/")
        if f in target_map:
            if target_map[f]["status"] != "completed":
                target_map[f]["status"] = "completed"
                updated_count += 1
        else:
            print(f"警告: 文件不在列表中: {f}")
    
    if updated_count > 0:
        save_state(root, state)
        print(f"成功标记 {updated_count} 个文件为已完成。")
    else:
        print("没有文件状态被改变。")

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    
    # init
    p_init = subparsers.add_parser("init")
    p_init.add_argument("--ignore-dirs", default="")
    p_init.add_argument("--include-exts", default=".py,.js,.ts,.go,.java,.c,.cpp,.h")
    
    # next
    p_next = subparsers.add_parser("next")
    
    # done
    p_done = subparsers.add_parser("done")
    p_done.add_argument("files", nargs="+")
    
    # scan (简单复用 init 的逻辑或者单独写，这里为了简化省略)
    p_scan = subparsers.add_parser("scan")

    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    
    if args.command == "init":
        cmd_init(root, args.ignore_dirs, args.include_exts)
    elif args.command == "next":
        cmd_next(root)
    elif args.command == "done":
        cmd_done(root, args.files)
    elif args.command == "scan":
        # 简单实现 scan 用于规划阶段
        for r, d, f in os.walk(root):
            if ".git" in d: d.remove(".git")
            if ".code-read" in d: d.remove(".code-read")
            level = len(Path(r).relative_to(root).parts)
            if level < 3:
                print(f"{'  '*level}{Path(r).name}/ ({len(f)} files)")

if __name__ == "__main__":
    main()