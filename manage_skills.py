#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Codex Analysis Skills - Skill Mount Manager (互動式技能掛載管理工具)
提供終端機 Checkbox 互動介面 (TUI) 與 網頁圖形介面 (Web UI)，
可方便勾選並將本專案的技能與 .env 設定檔以軟連結 (symlink) 掛載到 ~/.agents/skills，
並支援在取消勾選或解除掛載時同步解除 .env 軟連結。
"""

import os
import sys
import json
import curses
import argparse
import webbrowser
import http.server
import socketserver
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

# 預設掛載目標目錄 (標準 Agent Skills 目錄)
DEFAULT_TARGET_DIR = os.path.expanduser("~/.agents/skills")
REPO_DIR = os.path.dirname(os.path.abspath(__file__))

# 技能清單中繼資料（預設配置與分類，支援動態擴充）
KNOWN_SKILLS_META = {
    "mlb-analysis": {
        "name": "mlb-analysis",
        "title": "MLB 美國職棒分析",
        "category": "體育賽事 (Sports)",
        "icon": "⚾",
        "description": "分析 MLB 賽程、先發投手、打線、牛棚、傷兵、天氣球場、模型機率與盤口價值。",
        "requires_shared": True,
        "recommended": True,
    },
    "nba-analysis": {
        "name": "nba-analysis",
        "title": "NBA 美國職籃分析",
        "category": "體育賽事 (Sports)",
        "icon": "🏀",
        "description": "分析 NBA 賽程、傷兵輪替、對位節奏、模型機率、半場/首節與球員個人盤口。",
        "requires_shared": True,
        "recommended": True,
    },
    "soccer-analysis": {
        "name": "soccer-analysis",
        "title": "FIFA 足球賽事分析",
        "category": "體育賽事 (Sports)",
        "icon": "⚽",
        "description": "FIFA 世界盃決賽圈與指定資格賽分析（xG 預期進球、傷停、90分鐘與晉級盤口）。",
        "requires_shared": True,
        "recommended": True,
    },
    "lol-analysis": {
        "name": "lol-analysis",
        "title": "LoL 英雄聯盟電競分析",
        "category": "電競賽事 (Esports)",
        "icon": "⚔️",
        "description": "分析 LCK、LPL、LCP、LEC、LCS 賽程、名單、版本、BP、系列賽機率與盤口價值。",
        "requires_shared": True,
        "recommended": True,
    },
    "cs-analysis": {
        "name": "cs-analysis",
        "title": "CS2 / CS:GO 電競分析",
        "category": "電競賽事 (Esports)",
        "icon": "🎯",
        "description": "分析 CS2 賽程、陣容、地圖池 (Map Pool)、Veto 策略、槍位對戰與 BO3/BO5 盤口。",
        "requires_shared": True,
        "recommended": True,
    },
    "dota2-analysis": {
        "name": "dota2-analysis",
        "title": "Dota 2 電競分析",
        "category": "電競賽事 (Esports)",
        "icon": "🛡️",
        "description": "分析 Dota 2 國際賽事、英雄池、Draft/BP 陣容相剋、分路開局與系列賽機率。",
        "requires_shared": True,
        "recommended": True,
    },
    "valorant-analysis": {
        "name": "valorant-analysis",
        "title": "Valorant 特戰英豪分析",
        "category": "電競賽事 (Esports)",
        "icon": "🔫",
        "description": "分析 VCT 賽程、地圖選擇、特務組合 (Comp)、系列賽機率與關鍵回合決策。",
        "requires_shared": True,
        "recommended": True,
    },
    "prediction-pipeline": {
        "name": "prediction-pipeline",
        "title": "可稽核雙模型預測管線",
        "category": "預測管線 (Pipeline)",
        "icon": "🔄",
        "description": "協調 Codex 主預測 + agy 紅隊複核之雙模型互相審查，產出可稽核之賽事預測報告。",
        "requires_shared": True,
        "recommended": True,
    },
    "git-commit-push": {
        "name": "git-commit-push",
        "title": "Git 語意化提交與推送",
        "category": "工具技能 (Tools)",
        "icon": "🚀",
        "description": "檢查 Git 狀態、產製 Conventional Commits 繁體中文訊息並安全提交與推送至遠端。",
        "requires_shared": False,
        "recommended": True,
    },
    "automation": {
        "name": "automation",
        "title": "賽事自動化排程與通知",
        "category": "工具技能 (Tools)",
        "icon": "🤖",
        "description": "定時執行 MLB / LoL 賽程分析、Crontab 排程管理與 SMTP 郵件自動通知模組。",
        "requires_shared": True,
        "recommended": False,
    },
    "shared": {
        "name": "shared",
        "title": "核心共用套件與 Notion 發布工具",
        "category": "核心共用 (Shared)",
        "icon": "📦",
        "description": "共用分析架構規範、機率校驗演算法 (validate_probabilities) 與 Notion 發布器。",
        "requires_shared": False,
        "recommended": True,
    },
}


class SkillScanner:
    """掃描專案內所有可用技能與目錄中繼資料"""

    @staticmethod
    def scan_repo(repo_dir: str = REPO_DIR) -> List[Dict[str, Any]]:
        skills = []
        if not os.path.exists(repo_dir):
            return skills

        # 遍歷專案目錄下的子資料夾
        for item in sorted(os.listdir(repo_dir)):
            if item.startswith(".") or item in ["node_modules", "dist", "build", ".git", ".gemini"]:
                continue
            item_path = os.path.join(repo_dir, item)
            if not os.path.isdir(item_path):
                continue

            skill_md = os.path.join(item_path, "SKILL.md")
            readme_md = os.path.join(item_path, "README.md")
            has_skill_md = os.path.isfile(skill_md)
            has_readme_md = os.path.isfile(readme_md)

            # 只納入包含 SKILL.md、README.md 或是已知共用模組的資料夾
            if not (has_skill_md or has_readme_md or item in KNOWN_SKILLS_META):
                continue

            meta = KNOWN_SKILLS_META.get(item, {}).copy()
            if not meta:
                meta = {
                    "name": item,
                    "title": item,
                    "category": "自訂技能 (Custom)",
                    "icon": "🧩",
                    "description": "",
                    "requires_shared": False,
                    "recommended": True,
                }

            if not meta.get("description") and has_skill_md:
                try:
                    with open(skill_md, "r", encoding="utf-8") as f:
                        content = f.read()
                        if content.startswith("---"):
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                for line in parts[1].splitlines():
                                    if line.startswith("description:"):
                                        desc = line.split("description:", 1)[1].strip().strip('"').strip("'")
                                        meta["description"] = desc
                                        break
                except Exception:
                    pass

            if not meta.get("description") and has_readme_md:
                try:
                    with open(readme_md, "r", encoding="utf-8") as f:
                        for line in f:
                            cleaned = line.strip().lstrip("#").strip()
                            if cleaned:
                                meta["description"] = cleaned
                                break
                except Exception:
                    pass

            meta["source_path"] = item_path
            skills.append(meta)

        return skills


class SkillManager:
    """管理技能軟連結 (Symlink) 與 .env 環境變數檔案掛載/解除掛載"""

    def __init__(self, target_dir: str = DEFAULT_TARGET_DIR, repo_dir: str = REPO_DIR):
        self.target_dir = os.path.expanduser(target_dir)
        self.repo_dir = repo_dir
        self.skills = SkillScanner.scan_repo(self.repo_dir)

    def get_skill_status(self, skill_name: str) -> Dict[str, Any]:
        """檢測單一技能在目標資料夾中的狀態"""
        target_path = os.path.join(self.target_dir, skill_name)
        source_path = os.path.join(self.repo_dir, skill_name)

        if not os.path.exists(self.target_dir):
            return {
                "mounted": False,
                "status": "unmounted",
                "status_label": "未掛載",
                "target_path": target_path,
                "source_path": source_path,
                "is_symlink": False,
                "symlink_target": None,
            }

        if os.path.islink(target_path):
            try:
                link_dest = os.readlink(target_path)
                abs_link_dest = os.path.abspath(os.path.join(os.path.dirname(target_path), link_dest))
                if abs_link_dest == os.path.abspath(source_path):
                    return {
                        "mounted": True,
                        "status": "mounted",
                        "status_label": "已掛載 (本專案)",
                        "target_path": target_path,
                        "source_path": source_path,
                        "is_symlink": True,
                        "symlink_target": link_dest,
                    }
                else:
                    return {
                        "mounted": False,
                        "status": "foreign_symlink",
                        "status_label": f"指向其他路徑: {link_dest}",
                        "target_path": target_path,
                        "source_path": source_path,
                        "is_symlink": True,
                        "symlink_target": link_dest,
                    }
            except Exception as e:
                return {
                    "mounted": False,
                    "status": "broken_symlink",
                    "status_label": f"損壞軟連結 ({str(e)})",
                    "target_path": target_path,
                    "source_path": source_path,
                    "is_symlink": True,
                    "symlink_target": None,
                }
        elif os.path.exists(target_path):
            return {
                "mounted": False,
                "status": "real_directory",
                "status_label": "實體資料夾 (非軟連結)",
                "target_path": target_path,
                "source_path": source_path,
                "is_symlink": False,
                "symlink_target": None,
            }
        else:
            return {
                "mounted": False,
                "status": "unmounted",
                "status_label": "未掛載",
                "target_path": target_path,
                "source_path": source_path,
                "is_symlink": False,
                "symlink_target": None,
            }

    def get_env_status(self) -> Dict[str, Any]:
        """檢測 .env 檔案在目標資料夾中的狀態"""
        source_env = os.path.join(self.repo_dir, ".env")
        target_env = os.path.join(self.target_dir, ".env")

        has_source = os.path.isfile(source_env)
        is_mounted = False
        status_label = "未掛載"

        if not has_source:
            status_label = "來源專案無 .env"
        elif os.path.islink(target_env):
            try:
                link_dest = os.readlink(target_env)
                abs_link_dest = os.path.abspath(os.path.join(os.path.dirname(target_env), link_dest))
                if abs_link_dest == os.path.abspath(source_env):
                    is_mounted = True
                    status_label = "已掛載 (本專案 .env)"
                else:
                    status_label = f"指向其他 .env: {link_dest}"
            except Exception:
                status_label = "損壞的 .env 軟連結"
        elif os.path.exists(target_env):
            status_label = "目標已存在實體 .env 檔案"

        return {
            "has_source": has_source,
            "mounted": is_mounted,
            "status_label": status_label,
            "source_path": source_env,
            "target_path": target_env,
        }

    def get_all_skills_with_status(self) -> List[Dict[str, Any]]:
        """取得所有技能清單及其目前的掛載狀態"""
        result = []
        for s in self.skills:
            item = s.copy()
            status_info = self.get_skill_status(s["name"])
            item.update(status_info)
            result.append(item)
        return result

    def apply_changes(
        self,
        selected_skill_names: List[str],
        auto_include_shared: bool = True,
        sync_env: bool = True,
    ) -> Dict[str, Any]:
        """
        套用變更：
        - 被勾選的技能：建立軟連結至 ~/.agents/skills
        - 未被勾選的技能：若是指向本專案的軟連結，則安全移除
        - .env 管理：
          * 若有勾選任何技能且 sync_env=True：建立 .env 軟連結
          * 若無勾選任何技能 (全部解除掛載) 或 sync_env=False：安全解除 .env 軟連結
        """
        os.makedirs(self.target_dir, exist_ok=True)
        selected_set = set(selected_skill_names)

        # 若勾選了需要 shared 的技能，自動補上 shared
        if auto_include_shared and len(selected_set) > 0:
            needs_shared = any(
                s.get("requires_shared", False) for s in self.skills if s["name"] in selected_set
            )
            if needs_shared and "shared" not in selected_set and any(s["name"] == "shared" for s in self.skills):
                selected_set.add("shared")

        results = {
            "target_dir": self.target_dir,
            "linked": [],
            "unlinked": [],
            "skipped": [],
            "errors": [],
            "env_linked": False,
        }

        # 1. 處理技能軟連結
        for skill in self.skills:
            name = skill["name"]
            source_path = os.path.join(self.repo_dir, name)
            target_path = os.path.join(self.target_dir, name)
            is_selected = name in selected_set

            try:
                if is_selected:
                    # 需掛載
                    if os.path.islink(target_path):
                        cur_dest = os.path.abspath(
                            os.path.join(os.path.dirname(target_path), os.readlink(target_path))
                        )
                        if cur_dest == os.path.abspath(source_path):
                            results["skipped"].append(f"{name} (已正確掛載)")
                            continue
                        else:
                            os.unlink(target_path)
                    elif os.path.exists(target_path):
                        results["errors"].append(
                            f"無法掛載 {name}：{target_path} 為實體目錄或檔案，請手動備份後移除"
                        )
                        continue

                    os.symlink(source_path, target_path)
                    results["linked"].append(f"{name} -> {target_path}")
                else:
                    # 不需掛載
                    if os.path.islink(target_path):
                        cur_dest = os.path.abspath(
                            os.path.join(os.path.dirname(target_path), os.readlink(target_path))
                        )
                        if cur_dest == os.path.abspath(source_path) or not os.path.exists(target_path):
                            os.unlink(target_path)
                            results["unlinked"].append(f"{name} (已解除掛載)")
                        else:
                            results["skipped"].append(f"{name} (非本專案軟連結，保留不移除)")
                    elif os.path.exists(target_path):
                        results["skipped"].append(f"{name} (實體目錄，保留不移除)")
            except Exception as e:
                results["errors"].append(f"處理 {name} 發生錯誤: {str(e)}")

        # 2. 處理 .env 軟連結掛載 / 解除掛載
        source_env = os.path.join(self.repo_dir, ".env")
        target_env_paths = [
            os.path.join(self.target_dir, ".env"),
            os.path.join(os.path.dirname(self.target_dir), ".env"),
        ]

        # 判斷 .env 是否應掛載：必須有勾選至少一個技能且 sync_env 為 True
        should_mount_env = (len(selected_set) > 0) and sync_env and os.path.isfile(source_env)

        if should_mount_env:
            for target_env in target_env_paths:
                try:
                    os.makedirs(os.path.dirname(target_env), exist_ok=True)
                    if os.path.islink(target_env):
                        cur_dest = os.path.abspath(
                            os.path.join(os.path.dirname(target_env), os.readlink(target_env))
                        )
                        if cur_dest == os.path.abspath(source_env):
                            results["skipped"].append(f".env (已在 {target_env} 正確掛載)")
                            continue
                        else:
                            os.unlink(target_env)
                    elif os.path.exists(target_env):
                        results["skipped"].append(f".env (目標 {target_env} 已有實體檔案，保留不覆蓋)")
                        continue

                    os.symlink(source_env, target_env)
                    results["linked"].append(f".env -> {target_env}")
                    results["env_linked"] = True
                except Exception as e:
                    results["errors"].append(f"掛載 .env 至 {target_env} 失敗: {str(e)}")
        else:
            # 解除 .env 掛載：若目標為指向本專案 .env 的軟連結，則安全移除
            for target_env in target_env_paths:
                if os.path.islink(target_env):
                    try:
                        cur_dest = os.path.abspath(
                            os.path.join(os.path.dirname(target_env), os.readlink(target_env))
                        )
                        if cur_dest == os.path.abspath(source_env) or not os.path.exists(target_env):
                            os.unlink(target_env)
                            results["unlinked"].append(f".env (已從 {target_env} 解除掛載)")
                    except Exception as e:
                        results["errors"].append(f"解除 .env 軟連結失敗 ({target_env}): {str(e)}")

        return results


# ==============================================================================
# 終端機互動介面 (Terminal Checkbox TUI via curses)
# ==============================================================================

class TerminalTUI:
    """基於 curses 的終端機 Checkbox 互動選單"""

    def __init__(self, manager: SkillManager):
        self.manager = manager
        self.skills = manager.get_all_skills_with_status()
        # 初始化勾選狀態（預設帶入目前已掛載者；若全部未掛載，預設勾選 recommended 者）
        has_any_mounted = any(s["mounted"] for s in self.skills)
        if has_any_mounted:
            self.selected = {s["name"]: s["mounted"] for s in self.skills}
        else:
            self.selected = {s["name"]: s.get("recommended", True) for s in self.skills}

        self.current_idx = 0
        self.auto_shared = True
        self.sync_env = True

    def run(self) -> Optional[Dict[str, Any]]:
        """啟動 curses 互動視窗"""
        try:
            return curses.wrapper(self._main_loop)
        except KeyboardInterrupt:
            return None

    def _main_loop(self, stdscr) -> Optional[Dict[str, Any]]:
        curses.curs_set(0)
        stdscr.clear()

        # 初始化色彩
        if curses.has_colors():
            curses.start_color()
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_CYAN, -1)     # 標題與重點
            curses.init_pair(2, curses.COLOR_GREEN, -1)    # 勾選與成功
            curses.init_pair(3, curses.COLOR_YELLOW, -1)   # 警告與變更
            curses.init_pair(4, curses.COLOR_WHITE, curses.COLOR_BLUE)  # 選中反白
            curses.init_pair(5, curses.COLOR_BLACK, curses.COLOR_CYAN)  # 按鈕高亮
            curses.init_pair(6, curses.COLOR_MAGENTA, -1)  # 分類標籤

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # 1. 繪製頂部標題與說明
            title = "🚀 Codex Analysis Skills - 技能與環境掛載管理器"
            stdscr.attron(curses.A_BOLD | curses.color_pair(1))
            stdscr.addstr(0, 2, title[: width - 4])
            stdscr.attroff(curses.A_BOLD | curses.color_pair(1))

            env_status = self.manager.get_env_status()
            sel_count = sum(1 for v in self.selected.values() if v)
            if sel_count == 0:
                env_badge = "⚪ 將隨技能解除"
            elif env_status["mounted"]:
                env_badge = "🟢 已掛載"
            elif self.sync_env:
                env_badge = "🟡 待掛載"
            else:
                env_badge = "⚪ 未啟用"

            target_info = f"📍 目標目錄: {self.manager.target_dir}  | 🔑 .env 掛載: [{env_badge}] (按 [E] 切換)"
            stdscr.addstr(1, 2, target_info[: width - 4], curses.color_pair(3))

            help_bar = "[↑/↓] 移動  [Space] 勾選/取消  [A] 全選  [N] 全清  [I] 反選  [E] .env開關  [Enter] 套用  [Q] 離開"
            stdscr.addstr(2, 2, help_bar[: width - 4], curses.A_DIM)
            stdscr.addstr(3, 0, "─" * (width - 1), curses.A_DIM)

            # 2. 繪製技能列表
            start_row = 4
            visible_rows = height - 12
            if visible_rows < 3:
                visible_rows = 3

            top_offset = 0
            if self.current_idx >= visible_rows:
                top_offset = self.current_idx - visible_rows + 1

            for i in range(visible_rows):
                idx = top_offset + i
                if idx >= len(self.skills):
                    break
                skill = self.skills[idx]
                name = skill["name"]
                icon = skill.get("icon", "🧩")
                title_name = skill.get("title", name)
                category = skill.get("category", "General")
                is_checked = self.selected.get(name, False)
                is_active = idx == self.current_idx

                status_info = self.manager.get_skill_status(name)
                is_currently_mounted = status_info["mounted"]

                cb_symbol = "[✔]" if is_checked else "[ ]"
                status_badge = "🟢 (已掛載)" if is_currently_mounted else "⚪ (未掛載)"
                if status_info["status"] == "foreign_symlink":
                    status_badge = "🟡 (外來連結)"

                row_text = f" {cb_symbol} {icon} {name:<20} {title_name:<18} [{category}] {status_badge}"

                row_pos = start_row + i
                if is_active:
                    stdscr.attron(curses.color_pair(4) | curses.A_BOLD)
                    stdscr.addstr(row_pos, 2, f"▶ {row_text}"[: width - 4])
                    stdscr.attroff(curses.color_pair(4) | curses.A_BOLD)
                else:
                    if is_checked:
                        stdscr.attron(curses.color_pair(2))
                        stdscr.addstr(row_pos, 2, f"  {row_text}"[: width - 4])
                        stdscr.attroff(curses.color_pair(2))
                    else:
                        stdscr.addstr(row_pos, 2, f"  {row_text}"[: width - 4])

            # 3. 繪製選中項目的詳細資訊面板
            info_row = height - 7
            if info_row > start_row + 2:
                stdscr.addstr(info_row, 0, "─" * (width - 1), curses.A_DIM)
                cur_skill = self.skills[self.current_idx]
                cur_name = cur_skill["name"]
                cur_desc = cur_skill.get("description", "無描述")
                cur_status = self.manager.get_skill_status(cur_name)

                stdscr.attron(curses.A_BOLD | curses.color_pair(1))
                stdscr.addstr(info_row + 1, 2, f"📌 技能詳情: {cur_skill.get('title', cur_name)} ({cur_name})"[: width - 4])
                stdscr.attroff(curses.A_BOLD | curses.color_pair(1))

                stdscr.addstr(info_row + 2, 2, f"說明: {cur_desc}"[: width - 4])
                stdscr.addstr(info_row + 3, 2, f"來源: {cur_status['source_path']}"[: width - 4], curses.A_DIM)
                stdscr.addstr(info_row + 4, 2, f"現狀: {cur_status['status_label']}"[: width - 4], curses.color_pair(3))

            # 4. 底部統計
            env_note = "[✔] 同步掛載" if (self.sync_env and sel_count > 0) else "[✖] 同步解除"
            summary_str = f"📊 目前勾選: {sel_count} / {len(self.skills)} 個技能 | .env: {env_note} | 按 [Enter] 套用變更"
            stdscr.attron(curses.color_pair(5) | curses.A_BOLD)
            stdscr.addstr(height - 1, 2, f" {summary_str} "[: width - 4])
            stdscr.attroff(curses.color_pair(5) | curses.A_BOLD)

            stdscr.refresh()

            try:
                key = stdscr.getch()
            except KeyboardInterrupt:
                return None

            if key in [ord("q"), ord("Q"), 27]:  # Q 或 ESC
                return None
            elif key in [curses.KEY_UP, ord("k"), ord("K")]:
                self.current_idx = (self.current_idx - 1) % len(self.skills)
            elif key in [curses.KEY_DOWN, ord("j"), ord("J")]:
                self.current_idx = (self.current_idx + 1) % len(self.skills)
            elif key in [ord(" "), ord("x"), ord("X")]:  # Space / X 切換勾選
                cur_name = self.skills[self.current_idx]["name"]
                self.selected[cur_name] = not self.selected.get(cur_name, False)
            elif key in [ord("a"), ord("A")]:  # 全選
                for s in self.skills:
                    self.selected[s["name"]] = True
            elif key in [ord("n"), ord("N")]:  # 全清
                for s in self.skills:
                    self.selected[s["name"]] = False
            elif key in [ord("i"), ord("I")]:  # 反選
                for s in self.skills:
                    self.selected[s["name"]] = not self.selected.get(s["name"], False)
            elif key in [ord("e"), ord("E")]:  # 切換 .env 掛載
                self.sync_env = not self.sync_env
            elif key in [ord("1")]:  # 僅選體育賽事
                for s in self.skills:
                    self.selected[s["name"]] = "Sports" in s.get("category", "")
            elif key in [ord("2")]:  # 僅選電競賽事
                for s in self.skills:
                    self.selected[s["name"]] = "Esports" in s.get("category", "")
            elif key in [10, 13, curses.KEY_ENTER]:  # Enter 套用變更
                chosen_names = [name for name, checked in self.selected.items() if checked]
                return self._confirm_and_apply(stdscr, chosen_names)

    def _confirm_and_apply(self, stdscr, chosen_names: List[str]) -> Dict[str, Any]:
        """顯示確認畫面並執行掛載"""
        stdscr.clear()
        height, width = stdscr.getmaxyx()

        stdscr.attron(curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(1, 2, "⚡ 確認套用變更 (Apply Symlinks Confirmation)")
        stdscr.attroff(curses.A_BOLD | curses.color_pair(1))

        stdscr.addstr(3, 2, f"目標目錄: {self.manager.target_dir}")
        env_action = "同步掛載至目標目錄" if (self.sync_env and len(chosen_names) > 0) else "解除掛載 (移除軟連結)"
        stdscr.addstr(4, 2, f".env 設定檔: {env_action}")
        stdscr.addstr(5, 2, f"共勾選 {len(chosen_names)} 個技能: {', '.join(chosen_names) if chosen_names else '(無，將解除所有掛載)'}")

        stdscr.addstr(7, 2, "確定要套用變更？ (按 [Y] 或 [Enter] 確定 / 按 [任意其他鍵] 返回)")
        stdscr.refresh()

        key = stdscr.getch()
        if key in [ord("y"), ord("Y"), 10, 13]:
            res = self.manager.apply_changes(
                selected_skill_names=chosen_names,
                auto_include_shared=self.auto_shared,
                sync_env=self.sync_env,
            )
            return res
        return None


# ==============================================================================
# 網頁圖形介面 (Web UI Dashboard via built-in HTTP Server)
# ==============================================================================

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Codex Analysis Skills - 技能掛載管理器</title>
  <style>
    :root {
      --bg-primary: #0f172a;
      --bg-surface: #1e293b;
      --bg-card: #273549;
      --bg-card-hover: #2f4058;
      --border-color: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0ea5e9;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Noto Sans TC", sans-serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-primary);
      color: var(--text-main);
      font-family: var(--font-family);
      line-height: 1.5;
      padding: 24px;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .container {
      max-width: 1100px;
      margin: 0 auto;
      width: 100%;
      flex: 1;
    }

    header {
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border-color);
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 16px;
    }

    .header-title h1 {
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .header-title p {
      color: var(--text-muted);
      font-size: 0.9rem;
      margin-top: 4px;
    }

    .config-card {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      padding: 16px 20px;
      margin-bottom: 20px;
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
    }

    .config-group {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }

    .config-group label {
      font-size: 0.88rem;
      font-weight: 600;
      color: var(--text-muted);
    }

    input[type="text"] {
      background-color: var(--bg-card);
      border: 1px solid var(--border-color);
      color: var(--text-main);
      padding: 8px 12px;
      border-radius: 6px;
      font-size: 0.9rem;
      outline: none;
      min-width: 280px;
    }

    input[type="text"]:focus {
      border-color: var(--accent);
    }

    .filter-bar {
      display: flex;
      gap: 10px;
      margin-bottom: 16px;
      flex-wrap: wrap;
      align-items: center;
    }

    .filter-btn {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-color);
      color: var(--text-muted);
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
    }

    .filter-btn:hover, .filter-btn.active {
      background-color: var(--accent);
      color: #000;
      border-color: var(--accent);
      font-weight: 600;
    }

    .action-tools {
      margin-left: auto;
      display: flex;
      gap: 8px;
    }

    .btn {
      background-color: var(--bg-surface);
      color: var(--text-main);
      border: 1px solid var(--border-color);
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 0.88rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.15s ease-in-out;
    }

    .btn:hover {
      background-color: var(--border-color);
    }

    .btn-primary {
      background-color: var(--accent);
      color: #000;
      border-color: var(--accent);
    }

    .btn-primary:hover {
      background-color: var(--accent-hover);
    }

    .skills-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 16px;
      margin-bottom: 80px;
    }

    .skill-card {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px;
      transition: all 0.2s;
      cursor: pointer;
      position: relative;
      display: flex;
      flex-direction: column;
    }

    .skill-card:hover {
      border-color: var(--accent);
      background-color: var(--bg-card-hover);
    }

    .skill-card.selected {
      border-color: var(--accent);
      background-color: var(--bg-card);
    }

    .card-header {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      margin-bottom: 8px;
    }

    .skill-title-area {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .skill-icon {
      font-size: 1.5rem;
      line-height: 1;
    }

    .skill-name {
      font-weight: 700;
      font-size: 1.05rem;
      color: var(--text-main);
    }

    .skill-slug {
      font-size: 0.75rem;
      color: var(--text-muted);
      font-family: monospace;
    }

    .checkbox-custom {
      width: 20px;
      height: 20px;
      cursor: pointer;
      accent-color: var(--accent);
    }

    .skill-desc {
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 12px;
      flex: 1;
    }

    .card-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 0.75rem;
      border-top: 1px solid var(--border-color);
      padding-top: 10px;
      margin-top: auto;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 0.75rem;
      font-weight: 500;
    }

    .badge-mounted {
      background-color: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid var(--success);
    }

    .badge-unmounted {
      background-color: rgba(148, 163, 184, 0.1);
      color: var(--text-muted);
      border: 1px solid var(--border-color);
    }

    .badge-category {
      background-color: var(--bg-primary);
      color: var(--accent);
      padding: 2px 6px;
      border-radius: 4px;
    }

    .bottom-bar {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      background-color: var(--bg-surface);
      border-top: 1px solid var(--border-color);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      z-index: 100;
      box-shadow: 0 -4px 12px rgba(0,0,0,0.3);
    }

    .bottom-info {
      font-size: 0.95rem;
      font-weight: 600;
    }

    .modal {
      display: none;
      position: fixed;
      inset: 0;
      background: rgba(0, 0, 0, 0.75);
      z-index: 1000;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }

    .modal-content {
      background-color: var(--bg-surface);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      max-width: 600px;
      width: 100%;
      padding: 24px;
      max-height: 80vh;
      overflow-y: auto;
    }

    .modal-header {
      font-size: 1.2rem;
      font-weight: 700;
      margin-bottom: 12px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .log-entry {
      font-family: monospace;
      font-size: 0.85rem;
      padding: 4px 0;
    }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-title">
        <h1><span>🧩</span> Codex Analysis Skills 管理器</h1>
        <p>勾選欲掛載至本地 ~/.agents/skills 之賽事分析技能與 .env 設定檔</p>
      </div>
      <div>
        <button class="btn" onclick="fetchSkills()">🔄 重新整理</button>
      </div>
    </header>

    <div class="config-card">
      <div class="config-group">
        <label for="targetDir">📍 目標掛載目錄：</label>
        <input type="text" id="targetDir" value="~/.agents/skills" onchange="fetchSkills()">
      </div>
      <div class="config-group">
        <label style="cursor: pointer;">
          <input type="checkbox" id="syncEnv" checked> 同步掛載 .env 設定檔 (全取消時同步解除)
        </label>
        <label style="cursor: pointer; margin-left: 12px;">
          <input type="checkbox" id="autoShared" checked> 自動引入共用核心 (shared)
        </label>
      </div>
    </div>

    <div class="filter-bar">
      <button class="filter-btn active" onclick="setCategoryFilter('all', this)">全部技能</button>
      <button class="filter-btn" onclick="setCategoryFilter('Sports', this)">⚾ 體育賽事</button>
      <button class="filter-btn" onclick="setCategoryFilter('Esports', this)">⚔️ 電競賽事</button>
      <button class="filter-btn" onclick="setCategoryFilter('Pipeline', this)">🔄 預測管線</button>
      <button class="filter-btn" onclick="setCategoryFilter('Tools', this)">🛠️ 工具與自動化</button>

      <div class="action-tools">
        <button class="btn" onclick="selectAll(true)">全選</button>
        <button class="btn" onclick="selectAll(false)">全清 (解除全部)</button>
        <button class="btn" onclick="invertSelection()">反選</button>
      </div>
    </div>

    <div class="skills-grid" id="skillsGrid">
      <!-- 技能卡片將由 JS 動態渲染 -->
    </div>
  </div>

  <div class="bottom-bar">
    <div class="bottom-info" id="selectionSummary">
      已選取 0 / 0 個技能
    </div>
    <div>
      <button class="btn btn-primary" onclick="applyChanges()">
        🚀 套用變更至 ~/.agents/skills
      </button>
    </div>
  </div>

  <!-- 結果 Modal -->
  <div class="modal" id="resultModal">
    <div class="modal-content">
      <div class="modal-header">
        <span id="modalTitle">執行結果</span>
        <button class="btn" onclick="closeModal()">關閉</button>
      </div>
      <div id="modalBody"></div>
    </div>
  </div>

  <script>
    let allSkills = [];
    let selectedSkills = new Set();
    let currentCategory = 'all';

    async function fetchSkills() {
      const targetDir = document.getElementById('targetDir').value;
      try {
        const res = await fetch(`/api/skills?target_dir=${encodeURIComponent(targetDir)}`);
        const data = await res.json();
        allSkills = data.skills;

        selectedSkills.clear();
        const hasMounted = allSkills.some(s => s.mounted);
        allSkills.forEach(s => {
          if (hasMounted ? s.mounted : s.recommended) {
            selectedSkills.add(s.name);
          }
        });

        render();
      } catch (err) {
        alert('載入技能清單失敗: ' + err.message);
      }
    }

    function setCategoryFilter(cat, btn) {
      currentCategory = cat;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      render();
    }

    function toggleSkill(name, e) {
      if (e && e.target.tagName === 'INPUT') {
        if (e.target.checked) {
          selectedSkills.add(name);
        } else {
          selectedSkills.delete(name);
        }
      } else {
        if (selectedSkills.has(name)) {
          selectedSkills.delete(name);
        } else {
          selectedSkills.add(name);
        }
      }
      render();
    }

    function selectAll(check) {
      allSkills.forEach(s => {
        if (currentCategory === 'all' || (s.category && s.category.includes(currentCategory))) {
          if (check) selectedSkills.add(s.name);
          else selectedSkills.delete(s.name);
        }
      });
      render();
    }

    function invertSelection() {
      allSkills.forEach(s => {
        if (currentCategory === 'all' || (s.category && s.category.includes(currentCategory))) {
          if (selectedSkills.has(s.name)) selectedSkills.delete(s.name);
          else selectedSkills.add(s.name);
        }
      });
      render();
    }

    function render() {
      const grid = document.getElementById('skillsGrid');
      grid.innerHTML = '';

      const filtered = allSkills.filter(s => {
        if (currentCategory === 'all') return true;
        return s.category && s.category.includes(currentCategory);
      });

      filtered.forEach(skill => {
        const isChecked = selectedSkills.has(skill.name);
        const card = document.createElement('div');
        card.className = `skill-card ${isChecked ? 'selected' : ''}`;
        card.onclick = (e) => toggleSkill(skill.name, e);

        const statusBadge = skill.mounted
          ? '<span class="badge badge-mounted">🟢 已掛載</span>'
          : '<span class="badge badge-unmounted">⚪ 未掛載</span>';

        card.innerHTML = `
          <div class="card-header">
            <div class="skill-title-area">
              <span class="skill-icon">${skill.icon || '🧩'}</span>
              <div>
                <div class="skill-name">${skill.title || skill.name}</div>
                <div class="skill-slug">${skill.name}</div>
              </div>
            </div>
            <input type="checkbox" class="checkbox-custom" ${isChecked ? 'checked' : ''} onclick="event.stopPropagation(); toggleSkill('${skill.name}', event)">
          </div>
          <div class="skill-desc">${skill.description || '無描述'}</div>
          <div class="card-footer">
            <span class="badge badge-category">${skill.category || 'General'}</span>
            ${statusBadge}
          </div>
        `;
        grid.appendChild(card);
      });

      document.getElementById('selectionSummary').textContent =
        `已選取 ${selectedSkills.size} / ${allSkills.length} 個技能` + (selectedSkills.size === 0 ? ' (套用將解除所有掛載與 .env)' : '');
    }

    async function applyChanges() {
      const targetDir = document.getElementById('targetDir').value;
      const autoShared = document.getElementById('autoShared').checked;
      const syncEnv = document.getElementById('syncEnv').checked;

      const payload = {
        target_dir: targetDir,
        selected_skills: Array.from(selectedSkills),
        auto_shared: autoShared,
        sync_env: syncEnv,
      };

      try {
        const res = await fetch('/api/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const data = await res.json();

        let html = `<div style="margin-bottom: 12px;"><strong>目標路徑：</strong> ${data.target_dir}</div>`;
        if (data.linked && data.linked.length) {
          html += `<div style="color: var(--success); margin-bottom: 8px;"><strong>➕ 新增軟連結 (${data.linked.length})：</strong></div>`;
          data.linked.forEach(item => { html += `<div class="log-entry" style="color: var(--success)">✔ ${item}</div>`; });
        }
        if (data.unlinked && data.unlinked.length) {
          html += `<div style="color: var(--warning); margin-top: 12px; margin-bottom: 8px;"><strong>➖ 移除軟連結 (${data.unlinked.length})：</strong></div>`;
          data.unlinked.forEach(item => { html += `<div class="log-entry" style="color: var(--warning)">✖ ${item}</div>`; });
        }
        if (data.errors && data.errors.length) {
          html += `<div style="color: var(--danger); margin-top: 12px; margin-bottom: 8px;"><strong>⚠️ 錯誤 (${data.errors.length})：</strong></div>`;
          data.errors.forEach(item => { html += `<div class="log-entry" style="color: var(--danger)">❌ ${item}</div>`; });
        }
        if ((!data.linked || !data.linked.length) && (!data.unlinked || !data.unlinked.length)) {
          html += `<div style="color: var(--text-muted); margin-top: 8px;">沒有任何變更，目前配置已是最新狀態。</div>`;
        }

        document.getElementById('modalBody').innerHTML = html;
        document.getElementById('resultModal').style.display = 'flex';

        fetchSkills();
      } catch (err) {
        alert('套用變更失敗: ' + err.message);
      }
    }

    function closeModal() {
      document.getElementById('resultModal').style.display = 'none';
    }

    fetchSkills();
  </script>
</body>
</html>
"""


class WebUIServer:
    """輕量化本機 HTTP 伺服器，提供 Web Checkbox 管理介面"""

    def __init__(self, port: int = 8765, host: str = "127.0.0.1", repo_dir: str = REPO_DIR):
        self.port = port
        self.host = host
        self.repo_dir = repo_dir

    def start(self, auto_open: bool = True):
        repo_dir = self.repo_dir

        class RequestHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/" or self.path == "/index.html":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(HTML_TEMPLATE.encode("utf-8"))
                elif self.path.startswith("/api/skills"):
                    target_dir = DEFAULT_TARGET_DIR
                    if "?" in self.path:
                        query = self.path.split("?", 1)[1]
                        for part in query.split("&"):
                            if part.startswith("target_dir="):
                                import urllib.parse
                                target_dir = urllib.parse.unquote(part.split("=", 1)[1])

                    mgr = SkillManager(target_dir=target_dir, repo_dir=repo_dir)
                    skills_data = mgr.get_all_skills_with_status()
                    env_info = mgr.get_env_status()

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    resp = json.dumps({"skills": skills_data, "env": env_info, "target_dir": mgr.target_dir})
                    self.wfile.write(resp.encode("utf-8"))
                else:
                    self.send_error(404, "Not Found")

            def do_POST(self):
                if self.path == "/api/apply":
                    content_length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(content_length)
                    data = json.loads(body.decode("utf-8"))

                    target_dir = data.get("target_dir", DEFAULT_TARGET_DIR)
                    selected_skills = data.get("selected_skills", [])
                    auto_shared = data.get("auto_shared", True)
                    sync_env = data.get("sync_env", True)

                    mgr = SkillManager(target_dir=target_dir, repo_dir=repo_dir)
                    results = mgr.apply_changes(
                        selected_skill_names=selected_skills,
                        auto_include_shared=auto_shared,
                        sync_env=sync_env,
                    )

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(json.dumps(results).encode("utf-8"))
                else:
                    self.send_error(404, "Not Found")

            def log_message(self, format, *args):
                pass

        port = self.port
        while port < self.port + 50:
            try:
                server = socketserver.TCPServer((self.host, port), RequestHandler)
                break
            except OSError:
                port += 1

        url = f"http://{self.host}:{port}"
        print(f"\n🌐 Web 管理介面已啟動: {url}")
        print("按 Ctrl+C 可停止伺服器\n")

        if auto_open:
            try:
                webbrowser.open(url)
            except Exception:
                pass

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n伺服器已停止。")
            server.server_close()


# ==============================================================================
# CLI 命令列模式 (Non-interactive flags)
# ==============================================================================

def run_cli_list(manager: SkillManager):
    skills = manager.get_all_skills_with_status()
    env_info = manager.get_env_status()
    print(f"\n📍 目標資料夾: {manager.target_dir}")
    print(f"🔑 .env 狀態:  {env_info['status_label']}\n")
    print(f"{'狀態':<10} {'技能名稱':<22} {'分類':<18} {'說明'}")
    print("─" * 80)
    for s in skills:
        status_tag = "🟢 已掛載" if s["mounted"] else "⚪ 未掛載"
        if s["status"] == "foreign_symlink":
            status_tag = "🟡 其他路徑"
        name = s["name"]
        cat = s.get("category", "")
        desc = s.get("description", "")
        if len(desc) > 30:
            desc = desc[:28] + "..."
        print(f"{status_tag:<10} {name:<22} {cat:<18} {desc}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Codex Analysis Skills 技能掛載管理器 (支援 Checkbox 互動 TUI、Web UI 與 CLI)"
    )
    parser.add_argument(
        "-w", "--web", action="store_true", help="啟動網頁瀏覽器圖形介面 (Web UI)"
    )
    parser.add_argument(
        "-t", "--target", default=DEFAULT_TARGET_DIR, help=f"指定目標目錄 (預設: {DEFAULT_TARGET_DIR})"
    )
    parser.add_argument(
        "-l", "--list", action="store_true", help="列出所有技能與目前的掛載狀態"
    )
    parser.add_argument(
        "--all", action="store_true", help="非互動模式：直接掛載全部技能與 .env 至目標目錄"
    )
    parser.add_argument(
        "--link", nargs="+", help="非互動模式：指定要掛載的技能名稱"
    )
    parser.add_argument(
        "--unlink", nargs="+", help="非互動模式：指定要解除掛載的技能名稱"
    )
    parser.add_argument(
        "--unlink-all", action="store_true", help="非互動模式：解除所有已掛載技能與 .env"
    )
    parser.add_argument(
        "--no-env", action="store_true", help="掛載時不包含 .env 軟連結"
    )

    args = parser.parse_args()
    manager = SkillManager(target_dir=args.target)

    # 1. 網頁介面模式
    if args.web:
        server = WebUIServer(repo_dir=REPO_DIR)
        server.start()
        return

    # 2. 列出清單
    if args.list:
        run_cli_list(manager)
        return

    # 3. 非互動命令列操作
    if args.all:
        all_names = [s["name"] for s in manager.skills]
        res = manager.apply_changes(all_names, sync_env=not args.no_env)
        print(f"✅ 已掛載全部技能至 {manager.target_dir}:", res["linked"])
        return

    if args.unlink_all:
        res = manager.apply_changes([], sync_env=False)
        print(f"✅ 已解除所有技能與 .env 掛載: {res['unlinked']}")
        return

    if args.link:
        res = manager.apply_changes(args.link, sync_env=not args.no_env)
        print(f"✅ 新增掛載至 {manager.target_dir}:", res["linked"])
        if res["errors"]:
            print("⚠️ 錯誤:", res["errors"])
        return

    if args.unlink:
        current_mounted = [s["name"] for s in manager.get_all_skills_with_status() if s["mounted"]]
        remain = [name for name in current_mounted if name not in args.unlink]
        res = manager.apply_changes(remain, sync_env=(len(remain) > 0 and not args.no_env))
        print(f"✅ 解除掛載從 {manager.target_dir}:", res["unlinked"])
        return

    # 4. 預設：啟動終端機 Checkbox TUI 互動介面
    tui = TerminalTUI(manager)
    res = tui.run()

    if res:
        print("\n🎉 掛載變更已成功套用！")
        print(f"📍 目標目錄: {res['target_dir']}")
        if res["linked"]:
            print(f"➕ 新增掛載 ({len(res['linked'])}):")
            for item in res["linked"]:
                print(f"   ✔ {item}")
        if res["unlinked"]:
            print(f"➖ 解除掛載 ({len(res['unlinked'])}):")
            for item in res["unlinked"]:
                print(f"   ✖ {item}")
        if res["skipped"]:
            print(f"ℹ️ 保留未變動 ({len(res['skipped'])}):")
            for item in res["skipped"]:
                print(f"   • {item}")
        if res["errors"]:
            print(f"⚠️ 錯誤 ({len(res['errors'])}):")
            for item in res["errors"]:
                print(f"   ❌ {item}")
        print()


if __name__ == "__main__":
    main()
