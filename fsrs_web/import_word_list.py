
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
from datetime import datetime

import pandas as pd

# 设置环境变量以确保使用数据库
os.environ.setdefault("USE_DATABASE", "true")

# 项目内导入（确保脚本可单独运行）
from fsrs_web.models.database import (
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

# 读取命令行参数
excel_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_EXCEL_PATH
if not excel_path.exists():
    print(f"❌ Excel 文件不存在: {excel_path}")
    sys.exit(1)

print(f"📖 正在读取 Excel: {excel_path}")

df = pd.read_excel(excel_path)

# 要求至少包含这三个列名
required_cols = {"Unit", "Word", "Meaning"}
if not required_cols.issubset(set(df.columns)):
    print("❌ Excel 文件必须包含列: Unit, Word, Meaning")
    sys.exit(1)

session = get_db_session()
try:
    # 清空旧数据（如需保留旧数据可注释掉）
    print("🧹 清空现有 SystemCard 数据 …")
    session.query(UserCardState).delete()
    session.query(SystemCard).delete()
    session.commit()

    print("🚀 开始导入新单词 …")
    cards_to_add = []

    for i, row in enumerate(df.itertuples(index=False), start=1):
        unit_id = str(getattr(row, "Unit")).strip()
        front = str(getattr(row, "Word")).strip()
        back = str(getattr(row, "Meaning")).strip()

        if not unit_id or not front or not back:
            continue  # 跳过不完整行

        # 生成唯一卡片 ID，例如 Unit1_001
        id_suffix = f"{i:03d}"
        card_id = f"{unit_id}_{id_suffix}"

        card = SystemCard(
            id=card_id,
            unit_id=unit_id,
            front=front,
            back=back,
            created_at=datetime.now(),
        )
        cards_to_add.append(card)

    session.add_all(cards_to_add)
    session.commit()
    print(f"✅ 已成功导入 {len(cards_to_add)} 张系统卡片")

    # 为所有用户创建缺失的卡片状态
    users = session.query(User).all()
    print(f"👥 为 {len(users)} 个用户创建缺失卡片状态 …")

    for user in users:
        existing_card_ids = {
            state.card_id for state in session.query(UserCardState).filter_by(username=user.username)
        }
        new_states = []
        for card in cards_to_add:
            if card.id not in existing_card_ids:
                new_states.append(
                    UserCardState(
                        username=user.username,
                        card_id=card.id,
                        is_viewed=False,
                        due_date=card.created_at,
                        learning_factor=1.0,
                        is_user_card=False,
                    )
                )
        if new_states:
            session.add_all(new_states)
    session.commit()
    print("✅ 用户卡片状态创建完成！")

except Exception as e:
    session.rollback()
    print(f"❌ 导入失败: {e}")
    raise
finally:
    session.close() 