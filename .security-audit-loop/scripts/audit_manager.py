import argparse
import json
import os
import re
import sys
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from collections import Counter, defaultdict

# 配置
DATA_DIR = ".security-audit"
TODO_FILE = "SECURITY_FILETREE_TODO.md"
JSON_FILE = "SECURITY_FILETREE_TODO.json"
REPORT_FILE = "SECURITY_AUDIT_REPORT.md"
# 动态计算 Prompt 模板路径 (假定脚本位于 scripts/ 目录，模板在父目录)
PROMPT_TEMPLATE = Path(__file__).parent.parent / "prompts/PROMPT_audit.md"

def get_data_dir(root: Path) -> Path:
    """获取并创建数据存储目录"""
    d = root / DATA_DIR
    if not d.exists():
        d.mkdir(parents=True, exist_ok=True)
    return d

def load_json_state(root: Path) -> Dict[str, Any]:
    d = root / DATA_DIR
    if not d.exists():
        return {}
    json_path = d / JSON_FILE
    if not json_path.exists():
        # 如果不存在，返回一个空的初始状态，避免报错，方便 init 命令检查
        return {}
    return json.loads(json_path.read_text(encoding="utf-8"))

def save_json_state(root: Path, state: Dict[str, Any]):
    """
    保存状态到 JSON 文件。
    序列化格式规范：
    - 缩进: 2 空格
    - 编码: UTF-8
    - 键排序: 是 (sort_keys=True)
    - 确保 ASCII: 否 (允许中文)
    """
    d = get_data_dir(root)
    json_path = d / JSON_FILE
    json_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

def update_markdown_state(root: Path, state: Dict[str, Any]):
    # 这是一个简化后的重新生成逻辑。
    # 理想情况下应该解析 MD，但从 JSON 状态重新生成对于保持一致性更安全
    # 前提是我们要保留 'reason' 和 'tags'
    d = get_data_dir(root)
    md_path = d / TODO_FILE
    
    lines = []
    lines.append("# 安全审计文件树待办列表 (TODO)")
    lines.append("")
    lines.append(f"生成时间: `{state.get('generated_at', '')}`")
    lines.append(f"根目录: `{state.get('root', '')}`")
    lines.append(f"审计目标: `{state.get('goal', '')}`")
    lines.append("")
    lines.append("## 检测到的技术栈")
    for s in state.get("stacks", []):
        lines.append(f"- {s}")
    lines.append("")
    lines.append("## 待办事项 (TODO)")
    
    targets = state.get("targets", [])
    if not targets:
        lines.append("- (无目标)")
    else:
        for t in targets:
            status_mark = "[x]" if t.get("status") == "completed" else "[ ]"
            tag_str = ",".join(t.get("tags", []))
            lines.append(f"- {status_mark} `{t['path']}`  ({tag_str})  — {t.get('reason', '')}")
            
    lines.append("")
    lines.append("## 已忽略的目录")
    for d in state.get("ignored_dirs", []):
        lines.append(f"- `{d}/`")
    lines.append("")
    lines.append("## 注意事项")
    lines.append("- 勾选框代表你已经完成该文件（及相关调用链）的安全审计。")
    
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"已更新 {TODO_FILE}")

def cmd_next(root: Path):
    state = load_json_state(root)
    if not state:
        print(f"Error: {JSON_FILE} not found in {DATA_DIR}. Please run 'init' first.")
        return
    targets = state.get("targets", [])
    
    pending = [t for t in targets if t.get("status") == "pending"]
    if not pending:
        print("所有任务已完成！ 🎉")
        return

    # 加载 Prompt 模板
    prompt_path = PROMPT_TEMPLATE
    if not prompt_path.exists():
        # 如果模板缺失，使用备选方案
        prompt_tmpl = "请分析 {target_file} 是否存在安全漏洞。"
    else:
        prompt_tmpl = prompt_path.read_text(encoding="utf-8")
        
    # 注入当前 scripts/audit_manager.py 的绝对路径，以便 Prompt 中的命令可以正确执行
    audit_manager_path = str(Path(__file__).absolute())
    prompt_tmpl = prompt_tmpl.replace("{{AUDIT_MANAGER}}", audit_manager_path)
        
    final_prompt = prompt_tmpl.replace("{target_file}", "<从下方 Pending 列表选择一个目标文件>")
    final_prompt = final_prompt.replace("{goal}", state.get("goal", "安全审计"))
    
    lines = [final_prompt.rstrip(), "", "---", ""]
    lines.append(f"本轮可选 Pending 目标数: {len(pending)}")
    lines.append("从以下列表选择一个目标文件开始审计：")
    lines.append("")

    max_items = 120
    for t in pending[:max_items]:
        tag_str = ",".join(t.get("tags", []))
        reason = t.get("reason", "")
        lines.append(f"- `{t['path']}`  ({tag_str})  — {reason}")

    if len(pending) > max_items:
        lines.append(f"- ...(剩余 {len(pending) - max_items} 个，详见 .security-audit/{TODO_FILE})")

    print("\n".join(lines))

def cmd_done(root: Path, files: List[str]):
    state = load_json_state(root)
    targets = state.get("targets", [])
    updated_count = 0
    
    target_map = {t["path"]: t for t in targets}
    
    for fpath in files:
        # 统一路径分隔符
        fpath = fpath.replace("\\", "/")
        if fpath in target_map:
            if target_map[fpath]["status"] != "completed":
                target_map[fpath]["status"] = "completed"
                updated_count += 1
        else:
            # 可能是相对路径或需要解析
            # 目前仅严格匹配 JSON 中的路径
            pass
            
    if updated_count > 0:
        save_json_state(root, state)
        update_markdown_state(root, state)
        print(f"已将 {updated_count} 个文件标记为已完成。")
    else:
        print("未找到匹配的待处理文件。")

def cmd_report(root: Path, title: str, severity: str, file_path: str, description: str):
    d = get_data_dir(root)
    report_path = d / REPORT_FILE
    
    entry = []
    entry.append(f"### [漏洞] {title}")
    entry.append("")
    entry.append(f"- **严重程度**: {severity}")
    entry.append(f"- **文件**: `{file_path}`")
    # 简化时间戳，避免 Windows 上 os.times() 导致的 JSON 序列化问题
    import datetime
    entry.append(f"- **日期**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    entry.append(f"- **描述**: {description}")
    entry.append("")
    entry.append("---")
    entry.append("")
    
    mode = "a" if report_path.exists() else "w"
    with open(report_path, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("# 安全审计报告\n\n")
        f.write("\n".join(entry))
    
    print(f"已将漏洞添加到 {REPORT_FILE}")

def get_auto_tags(file_path: str) -> List[str]:
    """根据文件路径自动生成标签"""
    tags = set()
    lower_path = file_path.lower()
    
    keywords = {
        "auth": "auth", "login": "auth", "register": "auth", "password": "auth", "secret": "auth", "token": "auth",
        "api": "routes", "route": "routes", "controller": "routes", "view": "routes", "endpoint": "routes",
        "config": "config", "settings": "config", "env": "config",
        "db": "database", "database": "database", "model": "database", "sql": "database", "schema": "database",
        "upload": "upload", "file": "upload", "image": "upload",
        "util": "utils", "helper": "utils", "common": "utils",
        "docker": "container", "k8s": "container", "kube": "container",
        "main": "entrypoint", "app": "entrypoint", "index": "entrypoint", "server": "entrypoint"
    }
    
    for kw, tag in keywords.items():
        if kw in lower_path:
            tags.add(tag)
            
    # 根据扩展名打标
    ext = os.path.splitext(lower_path)[1]
    if ext in [".ini", ".env", ".yaml", ".yml", ".json", ".xml", ".toml"]:
        tags.add("config")
        
    return list(tags)

def cmd_scan(root: Path, max_depth: int = 3):
    """扫描目录结构并统计文件类型"""
    print(f"正在扫描根目录: {root} (深度限制: {max_depth})")
    print("-" * 60)
    
    # 默认忽略的目录
    default_ignores = {".git", ".idea", ".vscode", "__pycache__", "node_modules", "venv", ".venv", "env", "dist", "build", ".trae"}
    
    dir_stats = {} # path -> {count: int, exts: Counter}
    
    for dirpath, dirnames, filenames in os.walk(root):
        # 修改 dirnames 以便原地修剪
        dirnames[:] = [d for d in dirnames if d not in default_ignores]
        
        rel_path = Path(dirpath).relative_to(root)
        depth = len(rel_path.parts)
        
        if depth > max_depth:
            # 虽然 os.walk 还会继续，但我们不统计过深的内容，或者可以在这里清空 dirnames 来停止递归？
            # 为了简单起见，这里不清空，只是不打印详情
            pass
            
        exts = Counter([os.path.splitext(f)[1] for f in filenames])
        dir_stats[str(rel_path)] = {
            "count": len(filenames),
            "exts": exts,
            "depth": depth
        }

    # 打印树状摘要
    sorted_paths = sorted(dir_stats.keys())
    for p in sorted_paths:
        stat = dir_stats[p]
        if stat["depth"] > max_depth:
            continue
            
        indent = "  " * stat["depth"]
        if stat["count"] == 0:
            print(f"{indent}{p}/ (0 files)")
        else:
            ext_summary = ", ".join([f"{k}: {v}" for k, v in stat["exts"].most_common(3)])
            print(f"{indent}{p}/ ({stat['count']} files: {ext_summary})")
            
    print("-" * 60)
    print("扫描完成。请根据以上信息决定要忽略的目录 (--ignore-dirs) 或文件类型 (--exclude-exts)。")

def cmd_init(root: Path, ignore_dirs: str, include_exts: str, exclude_exts: str):
    """初始化任务列表"""
    
    ignores = set(x.strip() for x in ignore_dirs.split(",") if x.strip())
    # 默认忽略一些常见的垃圾目录
    ignores.update({".git", ".idea", ".vscode", "__pycache__", "node_modules", "venv", ".venv", ".trae"})
    
    inc_exts = set(x.strip() for x in include_exts.split(",") if x.strip())
    exc_exts = set(x.strip() for x in exclude_exts.split(",") if x.strip())
    
    targets = []
    
    print("正在生成文件列表...")
    
    for dirpath, dirnames, filenames in os.walk(root):
        # 过滤目录
        dirnames[:] = [d for d in dirnames if d not in ignores]
        
        for f in filenames:
            ext = os.path.splitext(f)[1]
            
            # 过滤逻辑
            if inc_exts and ext not in inc_exts:
                continue
            if exc_exts and ext in exc_exts:
                continue
                
            full_path = Path(dirpath) / f
            rel_path = full_path.relative_to(root)
            path_str = str(rel_path).replace("\\", "/")
            
            targets.append({
                "path": path_str,
                "status": "pending",
                "tags": get_auto_tags(path_str),
                "reason": "Initial scan"
            })
            
    state = {
        "generated_at": datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "root": str(root),
        "goal": "全面安全审计",
        "stacks": list(set([os.path.splitext(t["path"])[1] for t in targets])),
        "ignored_dirs": list(ignores),
        "targets": targets
    }
    
    save_json_state(root, state)
    update_markdown_state(root, state)
    print(f"初始化完成！共发现 {len(targets)} 个文件。")

def cmd_remove(root: Path, patterns: List[str]):
    """从任务列表中移除匹配的文件"""
    state = load_json_state(root)
    if not state:
        print("错误: 尚未初始化，请先运行 init。", file=sys.stderr)
        return

    targets = state.get("targets", [])
    initial_count = len(targets)
    
    new_targets = []
    removed_count = 0
    
    for t in targets:
        path = t["path"]
        should_remove = False
        for p in patterns:
            # 简单匹配：如果 pattern 出现在路径中
            if p in path:
                should_remove = True
                break
        
        if should_remove:
            removed_count += 1
        else:
            new_targets.append(t)
            
    state["targets"] = new_targets
    
    if removed_count > 0:
        save_json_state(root, state)
        update_markdown_state(root, state)
        print(f"已移除 {removed_count} 个文件。剩余 {len(new_targets)} 个。")
    else:
        print("没有匹配到要移除的文件。")

def main():
    parser = argparse.ArgumentParser(description="安全审计循环管理器")
    subparsers = parser.add_subparsers(dest="command", help="要执行的操作")
    
    # Scan
    p_scan = subparsers.add_parser("scan", help="扫描目录结构")
    p_scan.add_argument("--max-depth", type=int, default=3, help="显示深度")
    
    # Init
    p_init = subparsers.add_parser("init", help="初始化任务列表")
    p_init.add_argument("--ignore-dirs", default="", help="要忽略的目录，逗号分隔")
    p_init.add_argument("--include-exts", default="", help="只包含这些后缀，逗号分隔")
    p_init.add_argument("--exclude-exts", default="", help="排除这些后缀，逗号分隔")
    
    # Remove
    p_remove = subparsers.add_parser("remove", help="从列表中移除文件")
    p_remove.add_argument("patterns", nargs="+", help="要移除的文件路径模式（子串匹配）")

    # Next
    p_next = subparsers.add_parser("next", help="获取下一个任务")
    
    # Done
    p_done = subparsers.add_parser("done", help="标记任务完成")
    p_done.add_argument("files", nargs="*", help="要标记为完成的文件")
    
    # Report
    p_report = subparsers.add_parser("report", help="报告漏洞")
    p_report.add_argument("--title", help="漏洞标题")
    p_report.add_argument("--severity", choices=["High", "Medium", "Low"], help="严重程度")
    p_report.add_argument("--file", help="漏洞文件路径")
    p_report.add_argument("--desc", help="详细描述")
    
    # Global args
    parser.add_argument("--root", default=".", help="代码库根目录")
    
    args = parser.parse_args()
    root = Path(args.root).resolve()
    
    if args.command == "scan":
        cmd_scan(root, args.max_depth)
    elif args.command == "init":
        cmd_init(root, args.ignore_dirs, args.include_exts, args.exclude_exts)
    elif args.command == "remove":
        cmd_remove(root, args.patterns)
    elif args.command == "next":
        cmd_next(root)
    elif args.command == "done":
        if not args.files:
            print("错误: 请指定至少一个要标记为完成的文件。", file=sys.stderr)
            return
        cmd_done(root, args.files)
    elif args.command == "report":
        if not all([args.title, args.severity, args.file]):
            print("错误: --title, --severity 和 --file 是 report 命令必填项。", file=sys.stderr)
            return
        cmd_report(root, args.title, args.severity, args.file, args.desc or "未提供描述。")

if __name__ == "__main__":
    main()
