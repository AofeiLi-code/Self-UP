# CLAUDE.md · Self-UP 开发规范

## 首要原则

本项目有世界观文档 LORE.md，所有开发必须与其保持一致。
每次实现新功能前，先查阅 LORE.md 相关章节。

## 术语规范

所有变量名、字段名、API返回字段，严格遵循 LORE.md 第六章术语对照表：

| 禁止使用              | 必须使用           |
| --------------------- | ------------------ |
| user                  | cultivator         |
| xp / exp / experience | spiritual_energy   |
| level                 | realm_level        |
| task                  | technique          |
| checkin               | cultivation_record |
| notification          | system_message     |
| review / summary      | enlightenment      |
| guild                 | sect               |

## 境界与灵气

- 境界阈值以 LORE.md 第二章境界表为准，不得自行修改数值
- 走火入魔惩罚逻辑以 LORE.md 第2.3节为准
- 灵气加成规则以 LORE.md 第3.2节为准

## AI Prompt 规范

- 所有 system prompt 必须称呼用户为「宿主」
- 场景对应语气参考 LORE.md 第4.5节
- 突破大境界时必须触发专属文案，参考 LORE.md 第2.2节

## 新增功能检查清单

实现任何新功能后，自我检查：

- [ ] 变量名是否符合术语对照表
- [ ] 涉及灵气/境界的数值是否与 LORE.md 一致
- [ ] 涉及 AI 对话的场景语气是否符合第4.5节
- [ ] 新增的数据库字段是否需要更新 LORE.md 术语表
