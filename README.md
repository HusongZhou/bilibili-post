# bilibili-post

**中文**

给搬运到 B 站的视频写投稿信息：标题、标签、简介、封面文案、分区、创作声明、置顶评论，外加一份合规自查。发布一段时间后还能复盘哪种标题真有效。

接在 [bilingual-sub](../bilingual-sub) 后面用：它把视频、封面、双语字幕下到一个文件夹，这个 skill 拿那个文件夹写投稿包。

一条命令串起来：

```bash
./bilingual_sub.sh "<URL>" --engine deepseek --post
```

`--post` 会在视频做好后自动生成 `bili/brief.md`，接着让模型按本 skill 的 SKILL.md 写标题、标签、简介。

## 用法

在对话里说「这条视频发 B 站，起个标题」，或者直接：

```bash
python scripts/bili_brief.py "E:\Asset Library\youtube\<视频文件夹>"
```

脚本产出 `bili/brief.md`（元数据、章节、人物、候选钩子段）和 `bili/transcript.txt`（全文双语字幕）。剩下的判断和写作由模型按 `SKILL.md` 完成，产物是 `bili/投稿包.md`。

## 为什么不直接问 AI 写标题

因为直接问会得到一堆看起来像样的空话。这里多做了三件事：

- **先读片再写**：从双语字幕里合并出完整语段，挑出带数字、反常识、冲突的段落当原料，不是对着标题瞎猜。
- **合规自查**：极限词、标题党词、站外引流、转载声明，投稿前过一遍，避免限流。
- **发布后复盘**：`发布记录.csv` 攒数据，`bili_review.py` 出中位数对比，结论写回句式库。用得越久越贴合你这个号。

## 封面

原视频封面是 16:9、常带英文大字，直接传 B 站会被裁、观众也读不懂。这个脚本以前者为底改成 16:10：

```bash
python scripts/bili_cover.py "E:\Asset Library\youtube\<视频文件夹>" \
  --hooks "它被低估了|不是爽剧" --label "《足球教练》"
```

左侧（或 `--panel` 指定的一侧）压一块深色面板，盖掉原外文标题，换上中文钩子。默认左侧；原文字在底部就用 `--panel bottom`。出图在 `bili/封面/`。

## 复盘

```bash
python scripts/bili_review.py
```

读 `profile/发布记录.csv`，产出 `profile/复盘-<月份>.md`。

## 文件

```
bilibili-post/
├── SKILL.md                        主流程
├── scripts/
│   ├── bili_brief.py               视频文件夹 → 简报
│   ├── bili_cover.py               原封面 → 16:10 B 站封面
│   └── bili_review.py              发布记录 → 复盘报告
├── references/
│   ├── platform-rules.md           字段上限、转载规则、标题红线
│   └── title-patterns.md           六类钩子、句式库、本号实测
└── profile/
    ├── 账号定位.example.md          复制成 账号定位.md 再填
    └── 发布记录.csv                 表头已建好
```

## 依赖

Python 3.9+，无第三方库。字幕和封面由 bilingual-sub 准备。

## 注意

- 搬运的稿件在 B 站必须选「转载」并填来源；自行翻译加字幕**不算自制**。
- 不编造授权、来源和数据。
- 平台字段上限会变，以投稿页当场提示为准。
- `profile/账号定位.md`、`profile/复盘-*.md`、`bili/` 都在 `.gitignore` 里，属于你本地的账号数据，不会进仓库。

## License

[MIT](LICENSE)。本许可只针对代码和文档，不涉及你搬运的视频内容。
