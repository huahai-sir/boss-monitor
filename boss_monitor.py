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
CHAT_ID = os.environ.get("WECHAT_CHAT_ID", "wrQa_gFQAAdY_Cr4nhi5b1YzvzRHzN5w")
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
ALERT_MINUTES = 5
GROUP_WINDOW = 10


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
    "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=b8ac8c68-96db-438f-b4ee-e6422dfc5091"
)


def send_wecom_cli(content):
    """通过wecom-cli发送markdown消息"""
    try:
        payload = {"chat_id": CHAT_ID, "msg_type": "markdown", "markdown": {"content": content}}
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
    """通过Webhook发送markdown消息"""
    try:
        webhook_payload = {"msgtype": "markdown", "markdown": {"content": content}}
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
    # 北京时间 UTC+8
    bj_tz = timezone(timedelta(hours=8))
    now = datetime.now(bj_tz).replace(tzinfo=None)
    print(f"当前时间: {now.strftime('%Y-%m-%d %H:%M:%S')}")

    bosses = fetch_bosses()
    print(f"共获取 {len(bosses)} 个BOSS数据")

    state = load_state()
    alerted = state.get("alerted", {})

    upcoming = []
    for b in bosses:
        next_time = calc_next_time(b, now)
        diff_min = (next_time - now).total_seconds() / 60
        if diff_min > 0:
            name = b["boss_name"]
            drop = "紫" if b["drop_color"] == "purple" else "粉"
            alert_key = f"{name}_{next_time.strftime('%Y%m%d%H%M')}"
            upcoming.append({
                "name": name,
                "drop": drop,
                "next_time": next_time,
                "diff_min": diff_min,
                "alert_key": alert_key,
            })

    upcoming.sort(key=lambda x: x["next_time"])
    print(f"未过期BOSS: {len(upcoming)} 个")

    to_alert = []
    for u in upcoming:
        if u["diff_min"] <= ALERT_MINUTES and u["alert_key"] not in alerted:
            to_alert.append(u)

    print(f"需要提醒的BOSS: {len(to_alert)} 个")

    if not to_alert:
        expired_keys = [k for k, v in alerted.items()
                        if datetime.strptime(v, "%Y%m%d%H%M") < now]
        for k in expired_keys:
            del alerted[k]
        save_state({"alerted": alerted})
        print("无需提醒，退出")
        return

    # Webhook: 所有BOSS合并成一条
    webhook_lines = []
    for i, item in enumerate(to_alert, 1):
        webhook_lines.append(
            f"{i}. {item['name']}（{item['drop']}）"
            f"{item['next_time'].strftime('%H:%M')}刷新，"
            f"还有{int(item['diff_min'])}分钟"
        )
    webhook_content = "\n".join(webhook_lines)
    send_webhook(webhook_content)

    # 记录已提醒
    for item in to_alert:
        alerted[item["alert_key"]] = item["alert_key"].split("_")[1]

    save_state({"alerted": alerted})
    print("完成")


if __name__ == "__main__":
    main()
