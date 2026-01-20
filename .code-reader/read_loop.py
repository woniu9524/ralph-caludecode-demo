import sys
import subprocess
import time
import json
import shutil
from pathlib import Path

def _run_claude(prompt_text: str, cwd: Path):
    claude_exe = shutil.which("claude")
    if not claude_exe:
        print("错误: 找不到 'claude' 命令。请确保已安装 Claude CLI。")
        sys.exit(1)

    cmd = [claude_exe, "code", "-p", "--dangerously-skip-permissions"]
    try:
        subprocess.run(
            cmd,
            input=prompt_text,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            check=False
        )
    except Exception as e:
        print(f"Claude 执行出错: {e}")

def _is_all_done(root_dir: Path) -> bool:
    state_path = root_dir / ".code-read" / ".state.json"
    if not state_path.exists():
        return False
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        targets = data.get("targets", [])
        if not targets:
            return False
        for t in targets:
            if t.get("status") == "pending":
                return False
        return True
    except Exception:
        return False

def main():
    script_dir = Path(__file__).parent.absolute()
    manager_script = script_dir / "scripts" / "read_manager.py"
    
    if len(sys.argv) > 1:
        root_dir = Path(sys.argv[1]).absolute()
    else:
        root_dir = Path.cwd()
        
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"错误: 目标目录不存在或不是目录: {root_dir}")
        sys.exit(1)
    
    state_file = root_dir / ".code-read" / ".state.json"
    
    print(">>> 启动 Code Reader 引擎...")

    planner_prompt_path = script_dir / "prompts" / "PROMPT_planner.md"
    reader_prompt_path = script_dir / "prompts" / "PROMPT_reader.md"

    if not state_file.exists():
        print("[Phase 1] 初始化文件树...")
        if not planner_prompt_path.exists():
            print(f"错误: 找不到规划提示词文件: {planner_prompt_path}")
            sys.exit(1)
        planner_prompt = planner_prompt_path.read_text(encoding="utf-8")
        planner_prompt = planner_prompt.replace("{{MANAGER_PATH}}", str(manager_script))
        _run_claude(planner_prompt, root_dir)
    
    print("\n>>> [Phase 2] 开始循环阅读...")
    if not reader_prompt_path.exists():
        print(f"错误: 找不到阅读提示词文件: {reader_prompt_path}")
        sys.exit(1)

    reader_prompt_raw = reader_prompt_path.read_text(encoding="utf-8")
    reader_prompt = reader_prompt_raw.replace("scripts/read_manager.py", str(manager_script))

    while True:
        if _is_all_done(root_dir):
            print("所有文档生成完毕！退出循环。")
            break
        
        print("\n[Phase 2] 正在分析下一组代码...")
        
        proc = subprocess.run(
            [sys.executable, str(manager_script), "next", "--root", str(root_dir)],
            capture_output=True, text=True, encoding="utf-8"
        )

        pending_prompt = proc.stdout.strip()
        if pending_prompt:
            full_prompt = f"{reader_prompt.rstrip()}\n\n{pending_prompt}\n"
        else:
            full_prompt = reader_prompt

        _run_claude(full_prompt, root_dir)
        time.sleep(2)

if __name__ == "__main__":
    main()
