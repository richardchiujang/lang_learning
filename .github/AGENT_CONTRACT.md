# AGENT_CONTRACT.md

## AI Agent 不可違反協議

### 1. 輸出契約
- 所有 lesson 輸出必須為 JSON，且 schema 以 README/proj_spec.md 為唯一依據
- 不可更改 key、不可增加/刪除欄位、不可調整格式

### 2. 行為限制
- 不得更換終端機（僅能用 cmd，不可建議 powershell）
- 不得自動重構 pipeline 架構
- 不得主動調整 build/test 指令
- 不得主動更改學習邏輯

### 3. 權責邊界
- AI 不做產品設計決策
- AI 不推翻人類決定的工具鏈
- AI 不主動調整 output schema

### 這份文件所有條款皆為「鐵律」，違反即為錯誤，不接受語意解釋
