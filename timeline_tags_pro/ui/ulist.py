"""UIList for tag entries - matches original TimelineTagsPro.py V45.0 layout."""
import bpy
from bpy.types import UIList


class TTAG_UL_List(UIList):
    """原 V45.0 UIList 布局：颜色 | 帧数 | 标签名 | 留白安全区。"""

    def draw_item(self, context, layout, data, item, icon, active_data,
                  active_propname, index):
        # 1. 整体划分为: 左(12%给颜色) | 右(88%给其他)
        split_main = layout.split(factor=0.12)
        split_main.prop(item, "color", text="", icon_only=True)

        # 2. 将刚才的右侧(88%)，再划分为: 左(35%给帧数) | 右(65%给剩余)
        split_right = split_main.split(factor=0.35)
        split_right.prop(item, "frame", text="")

        # 3. 将最后的剩余部分(65%)，再划分为: 左(85%给标签名) | 右(15%给纯留白安全区)
        split_summary = split_right.split(factor=0.85)
        split_summary.prop(item, "summary", text="")

        # 【收缩逻辑的关键】放入空的 column 防止被拉伸
        split_summary.column()
