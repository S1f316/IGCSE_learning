#!/usr/bin/env python3
"""
更新卡片单元分类脚本
根据Excel文件中的单词分类更新数据库中的卡片单元
"""
import os
import sys
import pandas as pd
import re
from pathlib import Path

# 设置环境变量
os.environ['USE_DATABASE'] = 'true'
os.environ['DATABASE_URL'] = 'postgresql://chusheng_db_5djd_user:CEVrhJEIfditwICZpC4xfRwW0hXxFzJo@dpg-d1ov19ur433s73cpu850-a.singapore-postgres.render.com/chusheng_db_5djd'

try:
    from models.database import get_db_session, SystemCard, User, UserCardState
except ImportError as e:
    print(f"导入失败: {e}")
    sys.exit(1)

def extract_word_from_html(html_content):
    """从HTML内容中提取单词"""
    # 使用正则表达式提取<h3 class="word">与</h3>之间的内容
    match = re.search(r'<h3 class="word">(.*?)</h3>', html_content)
    if match:
        return match.group(1).strip()
    return None

def update_card_units():
    """根据Excel文件中的单词分类更新数据库中的卡片单元"""
    # 读取Excel文件
    excel_path = os.path.expanduser('~/Desktop/0580辅导软件/单词本/Cleaned_Word_List.xlsx')
    if not os.path.exists(excel_path):
        print(f"❌ Excel文件不存在: {excel_path}")
        return False
    
    df = pd.read_excel(excel_path)
    print(f"✅ 成功读取Excel文件，包含 {len(df)} 个单词")
    
    # 创建单词到单元的映射
    word_to_unit = {}
    for _, row in df.iterrows():
        word = str(row['Word']).strip()
        unit = f"unit{int(row['Unit'])}"
        word_to_unit[word.lower()] = unit
    
    print(f"✅ 创建了 {len(word_to_unit)} 个单词到单元的映射")
    
    # 连接到数据库
    session = get_db_session()
    try:
        # 获取所有系统卡片
        system_cards = session.query(SystemCard).all()
        print(f"✅ 从数据库中获取了 {len(system_cards)} 张系统卡片")
        
        # 统计更新前的单元分布
        unit_counts_before = {}
        for card in system_cards:
            if card.unit_id not in unit_counts_before:
                unit_counts_before[card.unit_id] = 0
            unit_counts_before[card.unit_id] += 1
        
        print("\n更新前的单元分布:")
        for unit_id, count in sorted(unit_counts_before.items()):
            print(f"{unit_id}: {count} 张卡片")
        
        # 更新卡片单元
        updated_count = 0
        not_found_count = 0
        not_found_words = []
        
        for card in system_cards:
            # 从卡片内容中提取单词
            word = extract_word_from_html(card.front)
            if word:
                # 转换为小写进行匹配
                word_lower = word.lower()
                if word_lower in word_to_unit:
                    new_unit_id = word_to_unit[word_lower]
                    # 如果单元不同，则更新
                    if card.unit_id != new_unit_id:
                        card.unit_id = new_unit_id
                        updated_count += 1
                else:
                    not_found_count += 1
                    not_found_words.append(word)
            else:
                not_found_count += 1
                not_found_words.append("无法提取单词")
        
        # 提交更改
        session.commit()
        print(f"\n✅ 成功更新了 {updated_count} 张卡片的单元")
        
        if not_found_count > 0:
            print(f"⚠️ 有 {not_found_count} 张卡片无法在Excel中找到对应单词")
            print("未找到的单词示例:")
            for word in not_found_words[:10]:
                print(f"  - {word}")
            if len(not_found_words) > 10:
                print(f"  ... 以及其他 {len(not_found_words) - 10} 个单词")
        
        # 统计更新后的单元分布
        unit_counts_after = {}
        for card in system_cards:
            if card.unit_id not in unit_counts_after:
                unit_counts_after[card.unit_id] = 0
            unit_counts_after[card.unit_id] += 1
        
        print("\n更新后的单元分布:")
        for unit_id, count in sorted(unit_counts_after.items()):
            print(f"{unit_id}: {count} 张卡片")
        
        return True
        
    except Exception as e:
        session.rollback()
        print(f"❌ 更新卡片单元失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        session.close()

def main():
    print("正在更新卡片单元分类...")
    print("-" * 50)
    
    success = update_card_units()
    if success:
        print("✅ 更新完成！")
    else:
        print("❌ 更新失败！")
        sys.exit(1)

if __name__ == '__main__':
    main() 