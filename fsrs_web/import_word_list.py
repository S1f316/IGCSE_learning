
#!/usr/bin/env python3
"""
从 Excel 文件批量导入系统单词到数据库，并为所有用户创建缺失的卡片状态。

用法：
    python import_word_list.py /path/to/Cleaned_Word_List.xlsx

如果不提供路径，脚本会使用默认路径：
    ~/Desktop/0580辅导软件/单词本/Cleaned_Word_List.xlsx

依赖：pandas、openpyxl (已在 requirements.txt 中列出)
"""
import os
import sys
from pathlib import Path
from typing import Union
import re  # 用于解析 unit 编号
from datetime import datetime

import pandas as pd

# 设置环境变量以确保使用数据库
os.environ.setdefault("USE_DATABASE", "true")

# 项目内导入（确保脚本可单独运行）
from models.database import (
    get_db_session,
    initialize_db,
    SystemCard,
    User,
    UserCardState,
)

# 确保表存在
initialize_db()

DEFAULT_EXCEL_PATH = (
    Path.home()
    / "Desktop"
    / "0580辅导软件"
    / "单词本"
    / "Cleaned_Word_List.xlsx"
)


def import_from_excel(excel_path: Union[str, Path] = DEFAULT_EXCEL_PATH, overwrite: bool = False) -> int:
    """从 Excel 文件导入系统卡片到数据库。

    参数:
        excel_path: Excel 文件路径
        overwrite  : True -> 清空旧数据后全量导入；False -> 仅增量导入缺失卡片
    返回:
        新增的 SystemCard 数量
    """

    excel_path = Path(excel_path)
    if not excel_path.exists():
        print(f"❌ Excel 文件不存在: {excel_path}")
        return 0

    print(f"📖 读取 Excel: {excel_path}")
    df = pd.read_excel(excel_path)

    required_cols = [
        "Unit",
        "Word",
        "Part_of_speech",
        "Chinese_definition",
        "English_definition",
    ]
    if not all(col in df.columns for col in required_cols):
        print(f"❌ 缺少必要列。应包含: {', '.join(required_cols)}")
        print(f"实际列名: {', '.join(df.columns)}")
        return 0

    session = get_db_session()
    new_cards_count = 0
    try:
        if overwrite:
            print("🧹 overwrite=True: 清空 SystemCard 与 UserCardState …")
            session.query(UserCardState).delete()
            session.query(SystemCard).delete()
            session.commit()

        cards_to_add: list[SystemCard] = []

        # 辅助函数：统一单元编号，兼容 "1"、"Unit 1"、"unit1" 等写法
        def normalize_unit(value: str) -> str:
            s = str(value).strip().lower()
            # 提取数字部分
            match = re.search(r"(\d+)", s)
            num = match.group(1) if match else s
            return f"unit{num}"

        for i, row in enumerate(df.itertuples(index=False), start=1):
            raw_unit = str(getattr(row, "Unit")).strip()
            unit_id = normalize_unit(raw_unit)
            word = str(getattr(row, "Word")).strip()
            pos = str(getattr(row, "Part_of_speech")).strip()
            zh = str(getattr(row, "Chinese_definition")).strip()
            en = str(getattr(row, "English_definition")).strip()

            if not unit_id or not word:
                continue

            meaning_parts: list[str] = []
            if pos:
                meaning_parts.append(f"【{pos}】")
            if zh:
                meaning_parts.append(zh)
            if en:
                meaning_parts.append(f"({en})")
            meaning = " ".join(meaning_parts)

            id_suffix = f"{i:03d}"
            card_id = f"{unit_id}_{id_suffix}"

            # 增量模式：已存在则跳过
            if not overwrite and session.get(SystemCard, card_id):
                continue

            cards_to_add.append(
                SystemCard(
                    id=card_id,
                    unit_id=unit_id,
                    front=word,
                    back=meaning,
                    created_at=datetime.now(),
                )
            )

        if cards_to_add:
            session.add_all(cards_to_add)
            session.commit()
            new_cards_count = len(cards_to_add)
            print(f"✅ 新增 {new_cards_count} 张系统卡片")
        else:
            print("ℹ️ 没有新的系统卡片需要导入")

        # 为所有用户补齐缺失的卡片状态
        users = session.query(User).all()
        for user in users:
            existing_ids = {
                s.card_id for s in session.query(UserCardState).filter_by(username=user.username)
            }
            new_states = [
                UserCardState(
                    username=user.username,
                    card_id=card.id,
                    is_viewed=False,
                    due_date=card.created_at,
                    learning_factor=1.0,
                    is_user_card=False,
                )
                for card in cards_to_add
                if card.id not in existing_ids
            ]
            if new_states:
                session.add_all(new_states)
        session.commit()
        if cards_to_add:
            print("✅ 用户卡片状态补齐完成！")
        return new_cards_count
    except Exception as e:
        session.rollback()
        print(f"❌ 导入失败: {e}")
        return 0
    finally:
        session.close()


# -------------------- CLI --------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import word list from Excel into database")
    parser.add_argument("--path", "-p", help="Excel 文件路径", default=str(DEFAULT_EXCEL_PATH))
    parser.add_argument("--overwrite", "-o", action="store_true", help="清空旧数据后全量导入")
    args = parser.parse_args()

    added = import_from_excel(args.path, args.overwrite)
    print(f"完成！新增 {added} 张卡片。") 