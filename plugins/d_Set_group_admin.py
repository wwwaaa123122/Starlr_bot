# SetGroupAdmin.py
# 插件：群管理设置（仅 ROOT_USER 可用）
# 用法：
# {reminder}群管设置 添加 @某人
# {reminder}群管设置 删除 @某人

TRIGGHT_KEYWORD = "群管设置"
HELP_MESSAGE = "-群管设置 添加@QQ / -群管设置 删除@QQ —> 仅 ROOT 用户可使用"

async def on_message(event, actions, Manager, Segments,
                     Super_User=None, Manage_User=None, ROOT_User=None,
                     Write_Settings=None):
    """
    说明：
    - 仅 ROOT_USER 可使用。
    - 自动识别 @段或纯 QQ 号。
    """

    # 权限验证
    if ROOT_User is None or str(event.user_id) not in ROOT_User:
        await actions.send(group_id=event.group_id,
                           message=Manager.Message(Segments.Text("权限不足：仅 ROOT 用户可使用。")))
        return True

    # 拼出纯文本命令
    raw_text = ""
    for seg in event.message:
        # 普通文本段
        if hasattr(seg, "type") and seg.type == "text":
            raw_text += seg.data.get("text", "")
        elif hasattr(seg, "type") and seg.type == "at":
            raw_text += f"@{seg.data.get('qq', '')}"
        else:
            raw_text += str(seg)

    text = raw_text.strip()
    if not text.startswith(TRIGGHT_KEYWORD):
        return False  # 非本插件命令

    # 去掉触发关键字
    payload = text[len(TRIGGHT_KEYWORD):].strip()

    # 确定是添加或删除
    is_add = any(payload.startswith(k) for k in ["添加", "add", "加入"])
    is_del = any(payload.startswith(k) for k in ["删除", "移除", "remove"])

    if not is_add and not is_del:
        await actions.send(group_id=event.group_id,
                           message=Manager.Message(Segments.Text(HELP_MESSAGE)))
        return True

    # 提取目标QQ号（兼容 @段）
    target_qq = ""
    for seg in event.message:
        if hasattr(seg, "type") and seg.type == "at":
            target_qq = seg.data.get("qq", "")
            break

    # 如果没有 @ 段，就从文本中提取
    if not target_qq:
        import re
        match = re.search(r'@?(\d{5,15})', payload)
        if match:
            target_qq = match.group(1)

    if not target_qq:
        await actions.send(group_id=event.group_id,
                           message=Manager.Message(Segments.Text("未识别到目标 QQ，请使用 @或直接填写 QQ 号。")))
        return True

    # 调用 OneBot v11 API 设置/取消管理员
    try:
        await actions.call_api("set_group_admin",
                               group_id=event.group_id,
                               user_id=int(target_qq),
                               enable=is_add)
        action_text = "设置" if is_add else "取消"
        await actions.send(group_id=event.group_id,
                           message=Manager.Message(Segments.Text(f"已{action_text} {target_qq} 为群管理员。")))
    except Exception as e:
        await actions.send(group_id=event.group_id,
                           message=Manager.Message(Segments.Text(f"执行失败：{e}")))

    return True