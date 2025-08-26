# PDF 生成ガイド（サクセッション手順書）

本リポジトリの手順書は以下のファイルで提供しています。

- HTML: `docs/succession_user_guide.html`（印刷スタイル付き）
- Markdown: `docs/succession_user_guide.md`

PDF を作成する方法は、環境に応じて次のいずれかを推奨します。

## 1) ブラウザから印刷（最も簡単）
1. `docs/succession_user_guide.html` をブラウザで開く
2. 印刷（Ctrl+P / Cmd+P）を開く
3. 送信先「PDF に保存」を選択
4. 余白: 既定、ヘッダー/フッター: オフ、背景のグラフィック: オン
5. 保存

> HTML は A4 向けの印刷スタイル（@page, 印刷用フォントサイズ）を適用済みです。

## 2) Google Chrome Headless（CLI）
Chrome/Chromium がインストール済みの場合は、以下で自動生成可能です。

```bash
# macOS の例（Chrome パスは環境に応じて変更）
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --headless \
  --disable-gpu \
  --print-to-pdf=docs/succession_user_guide.pdf \
  docs/succession_user_guide.html
```

## 3) wkhtmltopdf / pandoc（任意）
- wkhtmltopdf:
  ```bash
  wkhtmltopdf docs/succession_user_guide.html docs/succession_user_guide.pdf
  ```
- pandoc（簡易変換）:
  ```bash
  pandoc docs/succession_user_guide.md -o docs/succession_user_guide.pdf
  ```

> 環境依存のため、CI 化は別途検討してください（GitHub Actions での自動ビルドなど）。

## 画像差し替え
- `docs/capture_system_select.png` / `docs/capture_layout.png` はダミー名です。実画面キャプチャが準備でき次第、同名で配置してください。

