#!/usr/bin/env python3
"""
天堂2盟约 野外BOSS刷新监控脚本
通过wecom-cli向企业微信群推送BOSS刷新提醒
在GitHub Actions中运行，复用已授权的wecom-cli凭证
"""

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta

# ============ 配置 ============
BOSS_API_URL = "https://onizuka.cn/api/guild-boss-manual/public/DPXT94"
CHAT_ID = os.environ.get("WECHAT_CHAT_ID", "wrQa_gFQAAoiH2AthDJoiIAQVAfD7ohw")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
ALERT_MINUTES = 5
REFRESH_INTERVAL_HOURS = 6

# 固定活动提醒（每周几：0=周一, 6=周日）
FIXED_EVENTS = [
    {"name": "世界Boss", "days": [0,1,2,3,4,5,6], "hour": 12, "minute": 0},
    {"name": "世界Boss", "days": [0,1,2,3,4,5,6], "hour": 20, "minute": 0},
    {"name": "异教徒地下墓穴（个人战）", "days": [0,2,4], "hour": 12, "minute": 0},
    {"name": "异教徒地下墓穴（个人战）", "days": [0,2,4], "hour": 20, "minute": 30},
    {"name": "异教徒地下墓穴（战盟战）", "days": [5,6], "hour": 20, "minute": 40},
    {"name": "异教徒地下墓穴（战盟战）", "days": [5,6], "hour": 21, "minute": 10},
    {"name": "黄昏藏身处（4人）", "days": [1,3,5,6], "hour": 19, "minute": 30},
]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"alerted": {}}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def fetch_bosses():
    req = urllib.request.Request(BOSS_API_URL, headers={"User-Agent": "BossMonitor/1.0"})
    last_err = None
    for i in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data.get("bosses", [])
        except Exception as e:
            last_err = e
            print(f"第{i+1}次请求失败: {e}")
    raise last_err


def calc_next_time(boss, now):
    """计算BOSS下一次刷新时间（从现在起的下一次）"""
    # API返回的last_kill_time是UTC时间，转换为北京时间UTC+8
    last_kill = datetime.strptime(boss["last_kill_time"], "%Y-%m-%d %H:%M:%S") + timedelta(hours=8)
    interval = boss["interval_hours"]
    idx = boss["round"]["interval_index"]
    # 当前轮次的刷新时间
    current_round_time = last_kill + timedelta(hours=interval * idx)
    # 如果当前轮次刷新时间已过（overdue），继续往后推一个间隔
    next_time = current_round_time
    while next_time <= now:
        next_time += timedelta(hours=interval)
    return next_time


WEBHOOK_URL = os.environ.get(
    "WECHAT_WEBHOOK_URL",
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=cef13279-9a11-436a-ab26-ed0d2bc60240"
)


def send_wecom_cli(content):
    """通过wecom-cli发送text消息"""
    try:
        payload = {"chat_id": CHAT_ID, "msg_type": "text", "text": {"content": content}}
        result = subprocess.run(
            ["wecom-cli", "message", "aibot", "send", "--json", json.dumps(payload)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("wecom-cli发送成功")
            return True
        else:
            print(f"wecom-cli发送失败: {result.stderr}")
            return False
    except Exception as e:
        print(f"wecom-cli发送异常: {e}")
        return False


def send_webhook(content):
    """通过Webhook发送text消息"""
    try:
        webhook_payload = {"msgtype": "text", "text": {"content": content}}
        req = urllib.request.Request(
            WEBHOOK_URL,
            data=json.dumps(webhook_payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            print("Webhook发送成功")
            return True
    except Exception as e:
        print(f"Webhook发送异常: {e}")
        return False


def main():
    from datetime import timezone
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).replace(tzinfo=None)
    print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    state = load_state()
    alerted = state.get("alerted", {})
    last_fetch_time_str = state.get("last_fetch_time")
    boss_schedule = state.get("boss_schedule", [])

    # ===== 检查固定活动提醒 =====
    weekday = now.weekday()  # 0=周一, 6=周日
    event_alerts = []
    for event in FIXED_EVENTS:
        if weekday not in event["days"]:
            continue
        # 计算今天这个活动的开始时间
        event_time = now.replace(hour=event["hour"], minute=event["minute"], second=0, microsecond=0)
        diff_min = (event_time - now).total_seconds() / 60
        event_key = f"event_{event['name']}_{event_time.strftime('%Y%m%d%H%M')}"
        if 0 < diff_min <= ALERT_MINUTES and event_key not in alerted:
            event_alerts.append((event["name"], event_time, event_key))

    if event_alerts:
        for name, event_time, event_key in event_alerts:
            content = f"固定活动提醒：{name} {event_time.strftime('%H:%M')}开始，还有{int((event_time - now).total_seconds() / 60)}分钟"
            send_webhook(content)
            alerted[event_key] = event_time.strftime('%Y%m%d%H%M')
            print(f"固定活动提醒: {name}")

    # 判断是否需要重新检测网站（每隔6小时）
    need_refresh = True
    if last_fetch_time_str:
        last_fetch_time = datetime.strptime(last_fetch_time_str, "%Y-%m-%d %H:%M:%S")
        hours_since_fetch = (now - last_fetch_time).total_seconds() / 3600
        if hours_since_fetch < REFRESH_INTERVAL_HOURS:
            need_refresh = False
            print(f"距上次检测仅{hours_since_fetch:.1f}小时，使用缓存时间表")

    # 需要重新检测，获取最新BOSS数据
    if need_refresh:
        print("重新检测网站BOSS数据...")
        bosses = fetch_bosses()
        print(f"共获取 {len(bosses)} 个BOSS数据")

        boss_schedule = []
        for b in bosses:
            next_time = calc_next_time(b, now)
            name = b["boss_name"]
            drop = "紫" if b["drop_color"] == "purple" else "粉"
            boss_schedule.append({
                "name": name,
                "drop": drop,
                "next_time": next_time.strftime("%Y-%m-%d %H:%M:%S"),
            })
        boss_schedule.sort(key=lambda x: x["next_time"])
        state["last_fetch_time"] = now.strftime("%Y-%m-%d %H:%M:%S")
        state["boss_schedule"] = boss_schedule

    # 解析时间表
    upcoming = []
    for item in boss_schedule:
        next_time = datetime.strptime(item["next_time"], "%Y-%m-%d %H:%M:%S")
        diff_min = (next_time - now).total_seconds() / 60
        if diff_min > 0:
            upcoming.append({
                "name": item["name"],
                "drop": item["drop"],
                "next_time": next_time,
                "diff_min": diff_min,
            })

    upcoming.sort(key=lambda x: x["next_time"])
    print(f"未过期BOSS: {len(upcoming)} 个")

    # 分组：从最早的开始，5分钟窗口内的归为一组
    groups = []
    if upcoming:
        current_group = [upcoming[0]]
        base_time = upcoming[0]["next_time"]
        for u in upcoming[1:]:
            diff = (u["next_time"] - base_time).total_seconds() / 60
            if diff <= 5:
                current_group.append(u)
            else:
                groups.append(current_group)
                current_group = [u]
                base_time = u["next_time"]
        groups.append(current_group)

    print(f"分组数: {len(groups)}")

    # 先找出所有距离刷新<=5分钟、且未提醒过的BOSS
    to_alert_bosses = []
    for group in groups:
        for item in group:
            boss_key = f"{item['name']}_{item['next_time'].strftime('%Y%m%d%H%M')}"
            diff_min = (item['next_time'] - now).total_seconds() / 60
            if 0 < diff_min <= ALERT_MINUTES and boss_key not in alerted:
                to_alert_bosses.append(item)

    print(f"需要提醒的BOSS: {len(to_alert_bosses)} 个")

    if not to_alert_bosses:
        # 清理过期的提醒记录
        expired_keys = [k for k, v in alerted.items()
                        if datetime.strptime(v, "%Y%m%d%H%M") < now]
        for k in expired_keys:
            del alerted[k]
        state["alerted"] = alerted
        save_state(state)
        print("无需提醒，退出")
        return

    # 把需要提醒的BOSS再分组（5分钟窗口内）
    to_alert_bosses.sort(key=lambda x: x["next_time"])
    alert_groups = []
    current_group = [to_alert_bosses[0]]
    base_time = to_alert_bosses[0]["next_time"]
    for item in to_alert_bosses[1:]:
        diff = (item["next_time"] - base_time).total_seconds() / 60
        if diff <= 5:
            current_group.append(item)
        else:
            alert_groups.append(current_group)
            current_group = [item]
            base_time = item["next_time"]
    alert_groups.append(current_group)

    # 每组推送一条消息
    for group in alert_groups:
        webhook_lines = [f"{len(group)}只BOSS即将刷新："]
        for i, item in enumerate(group, 1):
            short_name = item['name'][:2]  # 名字只取前两个字
            webhook_lines.append(
                f"{i}. {short_name}（{item['drop']}）"
                f"{item['next_time'].strftime('%H:%M')}刷新"
            )
        webhook_content = "\n".join(webhook_lines)
        send_webhook(webhook_content)
        # 记录每个BOSS已提醒
        for item in group:
            boss_key = f"{item['name']}_{item['next_time'].strftime('%Y%m%d%H%M')}"
            alerted[boss_key] = item['next_time'].strftime('%Y%m%d%H%M')

    state["alerted"] = alerted
    save_state(state)
    print("完成")


if __name__ == "__main__":
    main()
