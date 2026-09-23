# 数字孪生论文 → Zotero

每天从以下期刊中筛选所有明确涉及数字孪生的论文并写入 Zotero，不再限定车辆领域：

- IEEE Transactions on Intelligent Vehicles
- IEEE Transactions on Intelligent Transportation Systems
- Mechanical Systems and Signal Processing
- Journal of Manufacturing Systems

默认首次回溯 8 个月、最多 6 篇；之后每天回看最近 7 天、按 DOI 和 OpenAlex ID 去重，最多导入 5 篇。回看 7 天是为了容忍出版数据库的收录延迟，不会导致重复导入。每篇入选论文在写入前还会通过 Crossref 核验 DOI 与题名一致性。

Zotero 目录结构：

```text
数字孪生_每日追踪
└── YYYY-MM-DD
```

## 下载与运行要求

本项目面向 Windows 10/11，使用 Python 3 标准库，无需安装额外 Python 包。

1. 在 GitHub 仓库页面点击 **Code → Download ZIP**。
2. 解压 ZIP，不要直接在压缩包内运行。
3. 安装 [Python 3](https://www.python.org/downloads/windows/)，安装时勾选将 Python 加入 PATH。
4. 准备自己的 Zotero API Key 和 OpenAlex API Key。
5. 双击 `一键完成配置.cmd`，按提示分别粘贴两枚密钥。

项目不会附带作者的密钥。每位使用者的密钥只会通过 Windows DPAPI 加密保存在自己的电脑上，不会写入项目配置或上传到 GitHub。

## 一次性配置

1. 在 Zotero 的 API Keys 页面创建一个专用密钥，仅授予个人文库的读写权限。
2. 在 [OpenAlex API 设置](https://openalex.org/settings/api)免费创建检索密钥。当前脚本每天仅发出 4 次搜索请求，处于免费额度内。
3. 双击 `一键完成配置.cmd`，依次粘贴两个密钥。它会自动完成首次导入，并安装每天 08:30 的计划任务。

也可以在本目录打开 PowerShell 分步执行：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\setup.ps1
```

两个密钥均通过 Windows DPAPI 加密，只能由当前 Windows 用户在当前电脑上解密。不要把密钥发到聊天、邮件或提交到 Git。

## 首次运行

可以先进行不写入 Zotero 的预览：

```powershell
.\run.ps1 -Initial -DryRun -VerboseOutput
```

确认结果后执行首次导入：

```powershell
.\run.ps1 -Initial -VerboseOutput
```

## 安装每天 08:30 的计划任务

```powershell
.\install_task.ps1 -At '08:30'
```

计划任务仅在当前用户登录 Windows 时运行；如果 08:30 时电脑未开机或尚未登录，Windows 会在随后登录且可运行时补跑。无需打开 GPT 或 Zotero 桌面端，但需要联网。日志位于 `logs` 目录。

## 自动相关性优先级评分

该分数不是 GPT 的估计，而是用于排序的固定规则分：题名或摘要明确出现“digital twin(s)”得基础 7 分；题名直接命中再加 5 分；有摘要加 1 分；综述加 2 分；相关方法词按 1–2 分累加；OpenAlex 引用量每 10 次加 1 分、最多加 3 分。当前最低入选分为 8 分。分数只表示自动阅读优先级，不等于论文质量、创新性或可信度。

## 内容与版权边界

- Zotero 中保存论文元数据、摘要、DOI 和出版商页面。
- OpenAlex 提供合法开放获取 PDF 地址时，添加“开放获取 PDF”链接附件。
- 不下载或绕过付费墙；订阅论文保留元数据和 DOI，全文可通过学校机构权限打开。
- 当天没有达到相关性阈值的论文时，不创建低相关文献凑数。

## 调整设置

编辑 `config.json` 可以修改每日数量、首次数量、回溯窗口和相关性阈值。降低 `minimum_score` 会增加数量，也会增加噪声。

## 许可证

本项目使用 MIT License。
