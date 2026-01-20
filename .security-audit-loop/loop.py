import sys
import subprocess
import time
import json
import shutil
from pathlib import Path

def _run_claude(prompt_text: str, cwd: Path):
    """直接调用 claude code 执行任务"""
    # 检查 claude 是否存在
    claude_exe = shutil.which("claude")
    if not claude_exe:
        print("错误: 找不到 'claude' 命令。请确保已安装 Claude CLI。")
        sys.exit(1)

    cmd = [claude_exe, "code", "-p", "--dangerously-skip-permissions"]
    try:
        # 将 prompt 通过 stdin 传入
        subprocess.run(
            cmd,
            input=prompt_text,
            text=True,
            encoding="utf-8",
            cwd=cwd,
            check=False # 不抛出异常，让循环继续或由调用者判断
        )
    except Exception as e:
        print(f"Claude 执行出错: {e}")

def _is_all_done(root_dir: Path) -> bool:
    """检查是否所有任务都已完成"""
    json_path = root_dir / ".security-audit" / "SECURITY_FILETREE_TODO.json"
    if not json_path.exists():
        return False
    
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        targets = data.get("targets", [])
        if not targets:
            return False
            
        # 只要有一个 pending 就没做完
        for t in targets:
            if t.get("status") == "pending":
                return False
        return True
    except Exception:
        return False

def main():
    # 1. 设置路径
    script_dir = Path(__file__).parent.absolute()
    audit_manager_path = str(script_dir / "scripts/audit_manager.py")
    
    # 处理命令行参数，允许用户指定目标目录
    if len(sys.argv) > 1:
        root_dir = Path(sys.argv[1]).absolute()
    else:
        root_dir = Path.cwd()
        
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"错误: 目标目录不存在或不是目录: {root_dir}")
        sys.exit(1)
    
    planner_prompt_path = script_dir / "prompts/PROMPT_planner.md"
    audit_prompt_path = script_dir / "prompts/PROMPT_audit.md"
    todo_json_path = root_dir / ".security-audit" / "SECURITY_FILETREE_TODO.json"

    print("=" * 60)
    print("      RALPH 安全审计循环")
    print("=" * 60)
    print(f"目标目录: {root_dir}")

    # 2. 规划阶段 (如果清单不存在)
    if not todo_json_path.exists():
        print("\n>>> [规划阶段] 未检测到任务清单，正在启动规划...")
        if not planner_prompt_path.exists():
            print(f"错误: 找不到规划提示词文件: {planner_prompt_path}")
            sys.exit(1)
            
        planner_prompt = planner_prompt_path.read_text(encoding="utf-8")
        # 注入 scripts/audit_manager.py 的绝对路径
        planner_prompt = planner_prompt.replace("{{AUDIT_MANAGER}}", audit_manager_path)
        
        _run_claude(planner_prompt, root_dir)
        
        # 规划完成后检查
        if not todo_json_path.exists():
            print("错误: 规划阶段结束，但仍未生成 SECURITY_FILETREE_TODO.json。退出。")
            sys.exit(1)
    else:
        print("\n>>> [规划阶段] 检测到现有任务清单，跳过规划。")

    # 3. 审计循环
    print("\n>>> [审计阶段] 开始循环审计...")
    if not audit_prompt_path.exists():
        print(f"错误: 找不到审计提示词文件: {audit_prompt_path}")
        sys.exit(1)

    audit_prompt_raw = audit_prompt_path.read_text(encoding="utf-8")
    # 注入 scripts/audit_manager.py 的绝对路径
    audit_prompt = audit_prompt_raw.replace("{{AUDIT_MANAGER}}", audit_manager_path)
    
    loop_count = 0

    try:
        while True:
            loop_count += 1
            
            # 检查是否全部完成
            if _is_all_done(root_dir):
                print(f"\n🎉 所有任务已完成！循环结束。")
                break
            
            print(f"\n[第 #{loop_count} 轮] 启动 Agent 进行审计...")
            
            # 将审计 Prompt 给 Claude，让它自己选任务
            _run_claude(audit_prompt, root_dir)
            
            # 简单的防死循环/速率限制
            time.sleep(2)
            
    except KeyboardInterrupt:
        print("\n用户停止循环。")
        sys.exit(0)

if __name__ == "__main__":
    main()
