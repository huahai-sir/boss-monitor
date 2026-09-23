#!/usr/bin/env python3
"""
天堂2盟约 野外BOSS刷新监控脚本
通过企业微信群机器人Webhook推送BOSS刷新提醒
"""

import json
import os
import urllib.request
from datetime import datetime, timedelta

# ============ 配置 ============
BOSS_API_URL = "https://onizuka.cn/api/guild-boss-manual/public/DPXT94"
WEBHOOK_URL = os.environ.get("WECHAT_WEBHOOK_URL", "")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
# 提前提醒分钟数
ALERT_MINUTES = 5
# 分组窗口（分钟）：刷新时间相差在此范围内的BOSS合并为一条消息
GROUP_WINDOW = 10


def load_state():
    """加载已提醒过的BOSS状态"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerted": {}}


def save_state(state):
    """保存状态"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_bosses():
    """从API获取BOSS数据"""
    req = urllib.request.Request(BOSS_API_URL, headers={"User-Agent": "BossMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data.get("bosses", [])


def calc_next_time(boss):
    """计算BOSS下次刷新时间"""
    last_kill = datetime.strptime(boss["last_kill_time"], "%Y-%m-%d %H:%M:%S")
    interval = boss["interval_hours"]
    idx = boss["round"]["interval_index"]
    return last_kill + timedelta(hours=interval * idx)


def send_wechat_markdown(content):
    """通过企业微信群机器人Webhook发送markdown消息"""
    if not WEBHOOK_URL:
        print("错误: 未配置 WECHAT_WEBHOOK_URL")
        return False

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": content}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        WEBHOOK_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode") == 0:
                print("企业微信消息发送成功")
                return True
            else:
                print(f"企业微信发送失败: {result}")
                return False
    except Exception as e:
        print(f"企业微信发送异常: {e}")
        return False


def main():
    now = datetime.now()
    print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    if not WEBHOOK_URL:
        print("未配置企业微信Webhook，退出")
        return

    # 获取BOSS数据
    bosses = fetch_bosses()
    print(f"共获取 {len(bosses)} 个BOSS数据")

    state = load_state()
    alerted = state.get("alerted", {})

    # 计算每个BOSS的下次刷新时间
    upcoming = []
    for b in bosses:
        next_time = calc_next_time(b)
        diff_min = (next_time - now).total_seconds() / 60
        if diff_min > 0:
            name = b["boss_name"]
            drop = "全紫" if b["drop_color"] == "purple" else "有粉"
            # 用 BOSS名_刷新时间 作为唯一标识
            alert_key = f"{name}_{next_time.strftime('%Y%m%d%H%M')}"
            upcoming.append({
                "name": name,
                "drop": drop,
                "next_time": next_time,
                "diff_min": diff_min,
                "alert_key": alert_key,
            })

    # 按刷新时间排序
    upcoming.sort(key=lambda x: x["next_time"])

    print(f"未过期BOSS: {len(upcoming)} 个")

    # 找出需要提醒的（在ALERT_MINUTES分钟内，且未提醒过）
    to_alert = []
    for u in upcoming:
        if u["diff_min"] <= ALERT_MINUTES and u["alert_key"] not in alerted:
            to_alert.append(u)

    print(f"需要提醒的BOSS: {len(to_alert)} 个")

    if not to_alert:
        # 清理过期的alerted记录（刷新时间已过的）
        expired_keys = [k for k, v in alerted.items()
                        if datetime.strptime(v, "%Y%m%d%H%M") < now]
        for k in expired_keys:
            del alerted[k]
        save_state({"alerted": alerted})
        print("无需提醒，退出")
        return

    # 分组：从最早开始，相差<=GROUP_WINDOW分钟的合并为一组
    groups = []
    current_group = [to_alert[0]]
    base_time = to_alert[0]["next_time"]

    for u in to_alert[1:]:
        diff = (u["next_time"] - base_time).total_seconds() / 60
        if diff <= GROUP_WINDOW:
            current_group.append(u)
        else:
            groups.append(current_group)
            current_group = [u]
            base_time = u["next_time"]
    groups.append(current_group)

    # 逐组发送
    for group in groups:
        lines = ["⚠️ **BOSS紧急刷新提醒**\n"]
        for item in group:
            lines.append(
                f"🔴 **{item['name']}（{item['drop']}）"
                f"将于 {item['next_time'].strftime('%H:%M')} 刷新，"
                f"还有约{int(item['diff_min'])}分钟！**"
            )
        lines.append("\n请立即前往卡位！")

        content = "\n".join(lines)
        success = send_wechat_markdown(content)

        if success:
            # 标记为已提醒
            for item in group:
                alerted[item["alert_key"]] = item["alert_key"].split("_")[1]

    # 保存状态
    save_state({"alerted": alerted})
    print("完成")


if __name__ == "__main__":
    main()
