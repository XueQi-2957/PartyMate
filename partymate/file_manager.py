"""
PartyMate FileManager — 文件归档管理器

自动管理成员档案目录结构，实现材料文件的自动归档。
目录结构：archives/{成员姓名}_{年级}_{专业}/{阶段名称}/
"""

from __future__ import annotations

import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# 阶段名称与文件夹名称映射
STAGE_FOLDER_MAP = {
    "applicant": "01_入党申请",
    "activist": "02_积极分子",
    "candidate": "03_发展对象",
    "probationary": "04_预备党员",
    "full_member": "05_转正",
}

# 中文阶段名
STAGE_NAMES_CN = {
    "applicant": "入党申请",
    "activist": "积极分子",
    "candidate": "发展对象",
    "probationary": "预备党员",
    "full_member": "正式党员",
}


class FileManager:
    """文件归档管理器

    基于 __file__ 定位 archives 目录，确保路径不依赖 cwd。
    """

    def __init__(self, base_dir: Optional[str] = None) -> None:
        """初始化文件管理器

        Args:
            base_dir: 归档根目录，默认使用 partymate 包同级下的 archives/
        """
        if base_dir:
            self._base_dir = Path(base_dir).resolve()
        else:
            # 定位到 partymate 包父级目录下的 archives
            self._base_dir = Path(__file__).resolve().parent.parent / "archives"
        self._base_dir.mkdir(parents=True, exist_ok=True)

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _get_member_dir_name(self, member_dict: dict[str, Any]) -> str:
        """生成成员目录名: {姓名}_{年级}_{专业}"""
        name = member_dict.get("name", "未知")
        grade = member_dict.get("grade", "未知年级")
        major = member_dict.get("major", "未知专业")
        # 清理非法文件名字符
        safe = lambda s: "".join(c for c in s if c.isalnum() or c in " _-（）()").strip()
        return f"{safe(name)}_{safe(grade)}_{safe(major)}"

    def _get_stage_folder(self, stage: str) -> str:
        """根据阶段 key 获取文件夹名"""
        return STAGE_FOLDER_MAP.get(stage, f"99_{stage}")

    def get_member_folder(self, member_dict: dict[str, Any]) -> str:
        """返回成员归档根目录路径

        Args:
            member_dict: 成员信息字典

        Returns:
            str: 成员根目录路径
        """
        dir_name = self._get_member_dir_name(member_dict)
        return str(self._base_dir / dir_name)

    def ensure_member_folder(self, member_dict: dict[str, Any]) -> dict[str, str]:
        """创建成员归档目录及其阶段子目录

        Args:
            member_dict: 成员信息字典

        Returns:
            dict: {stage_key: folder_path} 映射
        """
        member_path = Path(self.get_member_folder(member_dict))
        member_path.mkdir(parents=True, exist_ok=True)

        created: dict[str, str] = {}
        for stage_key, folder_name in STAGE_FOLDER_MAP.items():
            stage_path = member_path / folder_name
            stage_path.mkdir(parents=True, exist_ok=True)
            created[stage_key] = str(stage_path)

        return created

    def archive_material(
        self,
        material_dict: dict[str, Any],
        member_dict: dict[str, Any],
        source_path: str,
    ) -> Optional[str]:
        """将材料文件从 source_path 复制到正确的阶段子目录

        自动重命名：{材料名}_{时间戳}.{原后缀}

        Args:
            material_dict: 材料信息字典（含 material_name, stage）
            member_dict: 成员信息字典
            source_path: 源文件路径

        Returns:
            str: 目标文件路径，失败返回 None
        """
        source = Path(source_path)
        if not source.exists() or not source.is_file():
            return None

        # 确定目标目录
        stage = material_dict.get("stage", "applicant")
        stage_folder = self._get_stage_folder(stage)
        member_path = Path(self.get_member_folder(member_dict))
        target_dir = member_path / stage_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        # 构造目标文件名
        material_name = material_dict.get("material_name", "未知材料")
        suffix = source.suffix or ".pdf"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 清理文件名
        safe_name = "".join(c for c in material_name if c.isalnum() or c in "_ -（）()").strip()
        target_filename = f"{safe_name}_{timestamp}{suffix}"
        target_path = target_dir / target_filename

        try:
            shutil.copy2(str(source), str(target_path))
            return str(target_path)
        except (OSError, shutil.Error) as e:
            return None

    def get_member_archive_tree(
        self, member_dict: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """获取成员归档目录的完整文件树

        Args:
            member_dict: 成员信息字典

        Returns:
            list[dict]: 每阶段一个元素，含 stage 和 files 列表
                files 中每个文件: {name, path, size, modified}
        """
        member_path = Path(self.get_member_folder(member_dict))
        if not member_path.exists():
            return []

        tree: list[dict[str, Any]] = []
        for stage_key, folder_name in STAGE_FOLDER_MAP.items():
            stage_path = member_path / folder_name
            files: list[dict[str, Any]] = []
            if stage_path.exists() and stage_path.is_dir():
                for f in sorted(stage_path.iterdir()):
                    if f.is_file():
                        stat = f.stat()
                        files.append({
                            "name": f.name,
                            "path": str(f),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        })
            tree.append({
                "stage": stage_key,
                "stage_name_cn": STAGE_NAMES_CN.get(stage_key, stage_key),
                "folder_name": folder_name,
                "files": files,
                "file_count": len(files),
            })

        return tree

    def generate_archive_report(
        self, member_dict: dict[str, Any]
    ) -> str:
        """生成成员归档情况的 Markdown 报告

        列出每个阶段已归档的文件，标注缺失情况。

        Args:
            member_dict: 成员信息字典

        Returns:
            str: Markdown 格式的报告
        """
        name = member_dict.get("name", "未知")
        grade = member_dict.get("grade", "")
        major = member_dict.get("major", "")

        lines: list[str] = []
        lines.append(f"# 📁 {name} ({grade} {major}) — 档案归档报告")
        lines.append("")
        lines.append(f"> 归档路径：`{self.get_member_folder(member_dict)}`")
        lines.append("")
        lines.append("---")
        lines.append("")

        tree = self.get_member_archive_tree(member_dict)
        total_files = sum(t["file_count"] for t in tree)

        lines.append(f"**总计：{total_files} 个文件**")
        lines.append("")

        for t in tree:
            folder = t["folder_name"]
            cn_name = t["stage_name_cn"]
            files = t["files"]
            count = t["file_count"]

            lines.append(f"## 📂 {folder} — {cn_name}")
            lines.append("")

            if count == 0:
                lines.append("> ❌ **暂无归档文件** — 该阶段材料尚未归档")
                lines.append("")
            else:
                for f in files:
                    size_kb = f["size"] / 1024
                    lines.append(f"- 📄 **{f['name']}** ({size_kb:.1f} KB, {f['modified'][:10]})")
                lines.append("")
                lines.append(f"  *已归档 {count} 个文件*")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(f"*报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}*")

        return "\n".join(lines)