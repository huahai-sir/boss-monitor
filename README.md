# 天堂2盟约 BOSS刷新监控

通过企业微信群机器人Webhook自动推送BOSS刷新提醒，不依赖豆包额度。

## 部署步骤

### 1. 在企业微信群添加群机器人
- 打开企业微信群 → 右上角设置 → 群机器人 → 添加机器人
- 复制Webhook地址

### 2. Fork或使用本仓库
- 将代码推送到你的GitHub仓库

### 3. 配置Secrets
- 仓库 → Settings → Secrets and variables → Actions → New repository secret
- Name: `WECHAT_WEBHOOK_URL`
- Value: 你的企业微信群机器人Webhook地址

### 4. 启用GitHub Actions
- 仓库 → Actions → 启用
- 每5分钟自动运行一次，检测到BOSS即将刷新时自动推送

## 工作原理
- 每5分钟调用BOSS看板API获取刷新时间
- 提前5分钟推送提醒
- 刷新时间相差10分钟内的BOSS合并为一条消息
- 通过state.json记录已提醒的BOSS，避免重复推送
